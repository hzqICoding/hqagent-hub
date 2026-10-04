use std::{
    fs,
    io::Read,
    path::{Path, PathBuf},
    sync::{Arc, Mutex},
    time::{Duration, Instant},
};

use chrono::{DateTime, Utc};
use reqwest::{blocking::Client, redirect::Policy};
use serde::{Deserialize, Serialize};
use url::Url;

use crate::{
    error::ShellError,
    platform::{process_matches_executable, verify_private_file_acl},
    process_supervisor::{Component, ProcessIdentity, ProcessSupervisor},
};

const MAX_DESCRIPTOR_BYTES: u64 = 64 * 1024;
const MAX_RESPONSE_BYTES: usize = 256 * 1024;
pub(crate) const HEALTH_TIMEOUT: Duration = Duration::from_secs(2);
const READINESS_TIMEOUT: Duration = Duration::from_secs(15);
const COLD_READINESS_TIMEOUT: Duration = Duration::from_secs(30);
pub(crate) const COLD_START_WINDOW: Duration = Duration::from_secs(90);
const PROBE_CACHE_TTL: Duration = Duration::from_secs(2);
pub const TAURI_PRODUCTION_ORIGIN: &str = "http://tauri.localhost";
// Must match src/shared/api/client-features.ts: shell and frontend share a Bearer
// token. Bootstrap re-registers that token's projection capabilities; omitting
// pi-v1 here invalidates the frontend's subsequent event cursors.
const HUB_CLIENT_FEATURES: &str = "pi-v1";

#[derive(Clone, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct HubRuntimeDescriptor {
    schema_version: u32,
    instance_id: String,
    port: u16,
    token: String,
    pid: u32,
    base_url: String,
    app_version: String,
    protocol_version: String,
    started_at: DateTime<Utc>,
}

#[derive(Clone, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct UpdateAgentRuntimeDescriptor {
    schema_version: u32,
    instance_id: String,
    port: u16,
    token: String,
    pid: u32,
    base_url: String,
    agent_version: String,
    started_at: DateTime<Utc>,
}

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct HubEndpoint {
    base_url: String,
    token: String,
}

impl HubEndpoint {
    pub fn new(base_url: String, token: String) -> Self {
        Self { base_url, token }
    }
}

#[derive(Debug, Clone)]
pub struct HubProbeResult {
    pub maintenance: bool,
    pub instance_id: String,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct HealthResponse {
    status: String,
    app_version: String,
    protocol_version: String,
    pid: u32,
    started_at: DateTime<Utc>,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct BootstrapProbe {
    maintenance: bool,
    instance_id: Option<String>,
}

#[derive(Deserialize)]
struct ApiEnvelope<T> {
    success: bool,
    data: Option<T>,
}

pub struct HubEndpointProvider {
    descriptor_path: PathBuf,
    supervisor: Arc<ProcessSupervisor>,
    health_client: Client,
    readiness_client: Client,
    // Single flight across the UI and monitor. Cache results, never endpoint/token.
    readiness: Mutex<Option<ReadinessCache>>,
}

struct ReadinessCache {
    instance_id: String,
    pid: u32,
    checked_at: Instant,
    result: Result<HubProbeResult, ShellError>,
}

pub(crate) fn health_client() -> Result<Client, ShellError> {
    probe_client(HEALTH_TIMEOUT)
}

fn probe_client(timeout: Duration) -> Result<Client, ShellError> {
    Client::builder()
        .no_proxy()
        .connect_timeout(HEALTH_TIMEOUT)
        .timeout(timeout)
        .redirect(Policy::none())
        .build()
        .map_err(|error| ShellError::Internal(format!("无法创建本机 HTTP 客户端: {error}")))
}

fn readiness_timeout(age: Duration) -> Duration {
    if age < COLD_START_WINDOW { COLD_READINESS_TIMEOUT } else { READINESS_TIMEOUT }
}

fn trusted_descriptor(path: &Path, identity: &ProcessIdentity) -> Result<HubRuntimeDescriptor, ShellError> {
    let descriptor = read_descriptor(path)?;
    verify_private_file_acl(path)?;
    validate_hub_descriptor(&descriptor, identity)?;
    if !process_matches_executable(descriptor.pid, &identity.executable) {
        return Err(ShellError::InvalidDescriptor("Descriptor PID 不属于当前受管的核心进程".into()));
    }
    Ok(descriptor)
}

pub(crate) fn check_hub_liveness(client: &Client, path: &Path, identity: &ProcessIdentity) -> Result<(), ShellError> {
    let descriptor = trusted_descriptor(path, identity)?;
    probe_health(client, &descriptor)
}

fn probe_health(client: &Client, descriptor: &HubRuntimeDescriptor) -> Result<(), ShellError> {
    let response = client.get(format!("{}/healthz", descriptor.base_url)).send()
        .map_err(|error| ShellError::HubUnavailable(if error.is_timeout() {
            "存活探测 healthz 超时（2 秒）".into()
        } else { "存活探测 healthz 连接失败".into() }))?;
    if !response.status().is_success() {
        return Err(ShellError::HubUnavailable(format!("存活探测 healthz 返回 {}", response.status())));
    }
    validate_health(descriptor, &read_json_response(response)?)
}

impl HubEndpointProvider {
    pub fn new(
        descriptor_path: PathBuf,
        supervisor: Arc<ProcessSupervisor>,
    ) -> Result<Self, ShellError> {
        Ok(Self {
            descriptor_path,
            supervisor,
            health_client: health_client()?,
            readiness_client: probe_client(READINESS_TIMEOUT)?,
            readiness: Mutex::new(None),
        })
    }

    pub fn get_endpoint(&self) -> Result<(HubEndpoint, HubProbeResult), ShellError> {
        let identity = self
            .supervisor
            .identity(Component::Core)
            .ok_or_else(|| ShellError::HubUnavailable("核心进程尚未启动".into()))?;
        let descriptor = trusted_descriptor(&self.descriptor_path, &identity)?;
        probe_health(&self.health_client, &descriptor)?;
        let age = (Utc::now() - identity.launched_at).to_std().unwrap_or_default();
        let mut cache = self.readiness.lock().expect("readiness cache poisoned");
        let probe = if let Some(entry) = cache.as_ref().filter(|entry| {
            entry.pid == descriptor.pid && entry.instance_id == descriptor.instance_id
                && entry.checked_at.elapsed() < PROBE_CACHE_TTL
        }) {
            entry.result.clone()
        } else {
            let result = self.probe_readiness(&descriptor, readiness_timeout(age));
            *cache = Some(ReadinessCache {
                pid: descriptor.pid, instance_id: descriptor.instance_id.clone(),
                checked_at: Instant::now(), result: result.clone(),
            });
            result
        }?;
        // A health watchdog can restart the process while bootstrap is in flight.
        let current = self.supervisor.identity(Component::Core)
            .ok_or_else(|| ShellError::HubUnavailable("核心进程正在重新启动".into()))?;
        if current.pid != identity.pid || current.launched_at != identity.launched_at
            || current.instance_id != identity.instance_id {
            return Err(ShellError::HubUnavailable("核心进程已重新启动，正在重新获取连接".into()));
        }
        Ok((
            HubEndpoint::new(descriptor.base_url, descriptor.token),
            probe,
        ))
    }

    fn probe_readiness(&self, descriptor: &HubRuntimeDescriptor, timeout: Duration) -> Result<HubProbeResult, ShellError> {
        let bootstrap_url = format!("{}/api/v1/bootstrap", descriptor.base_url);
        let bootstrap_response = self
            .readiness_client
            .get(bootstrap_url)
            .timeout(timeout)
            .bearer_auth(&descriptor.token)
            .header("X-HQ-Client-Features", HUB_CLIENT_FEATURES)
            .header("Origin", TAURI_PRODUCTION_ORIGIN)
            .header("X-Client-Id", "hqagent-desktop-shell")
            .send()
            .map_err(|error| ShellError::HubUnavailable(if error.is_timeout() {
                format!("就绪探测 bootstrap 超时（{} 秒），Agent 检测可能仍在进行，将自动重试", timeout.as_secs())
            } else { "就绪探测 bootstrap 连接中断，将自动重试".into() }))?;
        if !bootstrap_response.status().is_success() {
            return Err(ShellError::HubUnavailable(format!(
                "bootstrap 探测返回 {}",
                bootstrap_response.status()
            )));
        }
        let envelope: ApiEnvelope<BootstrapProbe> = read_json_response(bootstrap_response)
            .map_err(|error| ShellError::HubUnavailable(format!("就绪探测 bootstrap 响应未完成或无效: {error}")))?;
        if !envelope.success {
            return Err(ShellError::HubUnavailable("bootstrap 探测返回失败包络".into()));
        }
        let bootstrap = envelope
            .data
            .ok_or_else(|| ShellError::HubUnavailable("bootstrap 探测缺少 data".into()))?;
        let instance_id = bootstrap.instance_id.ok_or_else(|| {
            ShellError::HubUnavailable("bootstrap 缺少用于防陈旧连接的 instanceId".into())
        })?;
        if instance_id != descriptor.instance_id {
            return Err(ShellError::HubUnavailable(
                "bootstrap instanceId 与 Descriptor 不匹配".into(),
            ));
        }
        Ok(HubProbeResult {
            maintenance: bootstrap.maintenance,
            instance_id,
        })
    }
}

fn read_json_response<T: for<'de> Deserialize<'de>>(
    response: reqwest::blocking::Response,
) -> Result<T, ShellError> {
    let mut bytes = Vec::new();
    response
        .take(MAX_RESPONSE_BYTES as u64 + 1)
        .read_to_end(&mut bytes)
        .map_err(|error| ShellError::HubUnavailable(format!("读取本机响应失败: {error}")))?;
    if bytes.len() > MAX_RESPONSE_BYTES {
        return Err(ShellError::HubUnavailable("本机响应体超出限制".into()));
    }
    serde_json::from_slice(&bytes)
        .map_err(|error| ShellError::HubUnavailable(format!("本机响应不是有效 JSON: {error}")))
}

pub fn read_descriptor<T: for<'de> Deserialize<'de>>(path: &Path) -> Result<T, ShellError> {
    let metadata = fs::symlink_metadata(path).map_err(|error| {
        ShellError::HubUnavailable(format!("无法读取 {}: {error}", path.display()))
    })?;
    if !metadata.file_type().is_file() || metadata.file_type().is_symlink() {
        return Err(ShellError::InvalidDescriptor(
            "运行时描述符必须是普通文件".into(),
        ));
    }
    if metadata.len() > MAX_DESCRIPTOR_BYTES {
        return Err(ShellError::InvalidDescriptor(
            "运行时描述符超过 64 KiB".into(),
        ));
    }
    let bytes = fs::read(path).map_err(|error| {
        ShellError::HubUnavailable(format!("无法读取 {}: {error}", path.display()))
    })?;
    serde_json::from_slice(&bytes)
        .map_err(|error| ShellError::InvalidDescriptor(format!("JSON 校验失败: {error}")))
}

pub fn validate_hub_descriptor(
    descriptor: &HubRuntimeDescriptor,
    identity: &ProcessIdentity,
) -> Result<(), ShellError> {
    validate_common(
        descriptor.schema_version,
        &descriptor.instance_id,
        descriptor.port,
        &descriptor.token,
        descriptor.pid,
        &descriptor.base_url,
        descriptor.started_at,
        identity,
    )?;
    if !is_protocol_version(&descriptor.protocol_version) {
        return Err(ShellError::InvalidDescriptor(
            "protocolVersion 必须是三段数字版本".into(),
        ));
    }
    if descriptor.app_version.trim().is_empty() {
        return Err(ShellError::InvalidDescriptor("appVersion 不能为空".into()));
    }
    Ok(())
}

pub fn validate_update_agent_descriptor(
    descriptor: &UpdateAgentRuntimeDescriptor,
    identity: &ProcessIdentity,
) -> Result<(), ShellError> {
    validate_common(
        descriptor.schema_version,
        &descriptor.instance_id,
        descriptor.port,
        &descriptor.token,
        descriptor.pid,
        &descriptor.base_url,
        descriptor.started_at,
        identity,
    )?;
    if descriptor.agent_version.trim().is_empty() {
        return Err(ShellError::InvalidDescriptor("agentVersion 不能为空".into()));
    }
    Ok(())
}

fn validate_common(
    schema_version: u32,
    instance_id: &str,
    port: u16,
    token: &str,
    pid: u32,
    base_url: &str,
    started_at: DateTime<Utc>,
    identity: &ProcessIdentity,
) -> Result<(), ShellError> {
    if schema_version != 1 {
        return Err(ShellError::InvalidDescriptor(
            "schemaVersion 必须为 1".into(),
        ));
    }
    if instance_id.len() < 8 || instance_id.chars().any(char::is_whitespace) {
        return Err(ShellError::InvalidDescriptor("instanceId 无效".into()));
    }
    if identity.instance_id.as_deref() != Some(instance_id) {
        return Err(ShellError::InvalidDescriptor(
            "instanceId 与当前受管进程不匹配".into(),
        ));
    }
    if pid == 0 || pid != identity.pid {
        return Err(ShellError::InvalidDescriptor(
            "pid 与当前受管进程不匹配".into(),
        ));
    }
    if !(1024..=65535).contains(&(port as u32)) {
        return Err(ShellError::InvalidDescriptor("port 不在允许范围".into()));
    }
    if !valid_secret(token) {
        return Err(ShellError::InvalidDescriptor(
            "token 不是至少 32 字节的 base64url 材料".into(),
        ));
    }
    let url = Url::parse(base_url)
        .map_err(|_| ShellError::InvalidDescriptor("baseUrl 不是有效 URL".into()))?;
    if url.scheme() != "http"
        || url.host_str() != Some("127.0.0.1")
        || url.port() != Some(port)
        || url.path() != "/"
        || url.query().is_some()
        || url.fragment().is_some()
        || !url.username().is_empty()
        || url.password().is_some()
    {
        return Err(ShellError::InvalidDescriptor(
            "baseUrl 必须精确指向 http://127.0.0.1:<port>".into(),
        ));
    }
    let earliest = identity.launched_at - chrono::Duration::seconds(5);
    let latest = Utc::now() + chrono::Duration::seconds(30);
    if started_at < earliest || started_at > latest {
        return Err(ShellError::InvalidDescriptor(
            "startedAt 不属于当前进程启动窗口".into(),
        ));
    }
    Ok(())
}

fn validate_health(
    descriptor: &HubRuntimeDescriptor,
    health: &HealthResponse,
) -> Result<(), ShellError> {
    if !matches!(
        health.status.as_str(),
        "ok" | "starting" | "maintenance" | "degraded"
    ) {
        return Err(ShellError::HubUnavailable("healthz status 无效".into()));
    }
    if health.pid != descriptor.pid
        || health.app_version != descriptor.app_version
        || health.protocol_version != descriptor.protocol_version
        || health.started_at != descriptor.started_at
    {
        return Err(ShellError::HubUnavailable(
            "healthz 身份信息与 Descriptor 不匹配".into(),
        ));
    }
    Ok(())
}

fn valid_secret(value: &str) -> bool {
    value.len() >= 43
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || byte == b'-' || byte == b'_')
}

fn is_protocol_version(value: &str) -> bool {
    let mut parts = value.split('.');
    let valid = (0..3).all(|_| {
        parts
            .next()
            .is_some_and(|part| !part.is_empty() && part.bytes().all(|b| b.is_ascii_digit()))
    });
    valid && parts.next().is_none()
}

pub fn descriptor_identity(
    component: Component,
    path: &Path,
    expected_pid: u32,
    launched_at: DateTime<Utc>,
    previous_instance_id: Option<&str>,
) -> Option<String> {
    match component {
        Component::Core => {
            let descriptor = read_descriptor::<HubRuntimeDescriptor>(path).ok()?;
            accept_identity(
                descriptor.pid,
                &descriptor.instance_id,
                descriptor.started_at,
                expected_pid,
                launched_at,
                previous_instance_id,
            )
        }
        Component::UpdateAgent => {
            let descriptor = read_descriptor::<UpdateAgentRuntimeDescriptor>(path).ok()?;
            accept_identity(
                descriptor.pid,
                &descriptor.instance_id,
                descriptor.started_at,
                expected_pid,
                launched_at,
                previous_instance_id,
            )
        }
    }
}

pub fn existing_instance_id(component: Component, path: &Path) -> Option<String> {
    match component {
        Component::Core => read_descriptor::<HubRuntimeDescriptor>(path)
            .ok()
            .map(|descriptor| descriptor.instance_id),
        Component::UpdateAgent => read_descriptor::<UpdateAgentRuntimeDescriptor>(path)
            .ok()
            .map(|descriptor| descriptor.instance_id),
    }
}

fn accept_identity(
    descriptor_pid: u32,
    descriptor_instance_id: &str,
    descriptor_started_at: DateTime<Utc>,
    expected_pid: u32,
    launched_at: DateTime<Utc>,
    previous_instance_id: Option<&str>,
) -> Option<String> {
    if descriptor_pid != expected_pid
        || descriptor_instance_id.len() < 8
        || previous_instance_id == Some(descriptor_instance_id)
        || descriptor_started_at < launched_at - chrono::Duration::seconds(5)
        || descriptor_started_at > Utc::now() + chrono::Duration::seconds(30)
    {
        return None;
    }
    Some(descriptor_instance_id.to_owned())
}

#[cfg(test)]
mod tests {
    use std::path::PathBuf;

    use chrono::Utc;

    use super::{validate_hub_descriptor, HubRuntimeDescriptor};
    use crate::process_supervisor::ProcessIdentity;

    #[test]
    fn health_and_readiness_have_independent_cold_start_deadlines() {
        use super::*;
        assert_eq!(HEALTH_TIMEOUT, Duration::from_secs(2));
        assert_eq!(READINESS_TIMEOUT, Duration::from_secs(15));
        assert_eq!(COLD_START_WINDOW, Duration::from_secs(90));
        assert_eq!(readiness_timeout(Duration::ZERO), Duration::from_secs(30));
        assert_eq!(readiness_timeout(Duration::from_secs(89)), Duration::from_secs(30));
        assert_eq!(readiness_timeout(Duration::from_secs(90)), Duration::from_secs(15));
    }

    fn identity(instance_id: &str) -> ProcessIdentity {
        ProcessIdentity {
            pid: 4321,
            instance_id: Some(instance_id.to_owned()),
            launched_at: Utc::now(),
            executable: PathBuf::from("hqagent-core.exe"),
        }
    }

    fn descriptor(instance_id: &str) -> HubRuntimeDescriptor {
        HubRuntimeDescriptor {
            schema_version: 1,
            instance_id: instance_id.to_owned(),
            port: 49210,
            token: "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQ".into(),
            pid: 4321,
            base_url: "http://127.0.0.1:49210".into(),
            app_version: "0.1.0".into(),
            protocol_version: "0.1.0".into(),
            started_at: Utc::now(),
        }
    }

    #[test]
    fn descriptor_rejects_stale_instance_id() {
        let error = validate_hub_descriptor(&descriptor("instance-new"), &identity("instance-old"))
            .expect_err("stale descriptor must fail");
        assert!(error.to_string().contains("instanceId"));
    }

    #[test]
    fn descriptor_rejects_non_loopback_url() {
        let mut value = descriptor("instance-current");
        value.base_url = "http://0.0.0.0:49210".into();
        assert!(validate_hub_descriptor(&value, &identity("instance-current")).is_err());
    }

    #[test]
    fn endpoint_serialization_only_contains_hub_url_and_token() {
        let endpoint = super::HubEndpoint::new(
            "http://127.0.0.1:49210".into(),
            "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQ".into(),
        );
        let value = serde_json::to_value(endpoint).expect("serialize");
        let object = value.as_object().expect("object");
        assert_eq!(object.len(), 2);
        assert!(object.contains_key("baseUrl"));
        assert!(object.contains_key("token"));
        assert!(!object.contains_key("pid"));
        assert!(!object.contains_key("updateAgent"));
    }
}
