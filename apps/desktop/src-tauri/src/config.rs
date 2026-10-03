use std::{
    env, fs,
    path::{Path, PathBuf},
    sync::RwLock,
};

use serde::{Deserialize, Serialize};

use crate::{error::ShellError, fs_util::atomic_write};

#[derive(Debug, Clone)]
pub struct AppPaths {
    pub root: PathBuf,
    pub config_dir: PathBuf,
    pub runtime_dir: PathBuf,
    pub shell_config: PathBuf,
    pub window_state: PathBuf,
}

impl AppPaths {
    pub fn discover() -> Result<Self, ShellError> {
        let local_app_data = env::var_os("LOCALAPPDATA")
            .filter(|value| !value.is_empty())
            .ok_or(ShellError::DataDirectoryUnavailable)?;
        Ok(Self::under(PathBuf::from(local_app_data).join("HQAgent-Hub")))
    }

    pub fn under(root: PathBuf) -> Self {
        let config_dir = root.join("config");
        let runtime_dir = root.join("runtime");
        Self {
            shell_config: config_dir.join("desktop-shell.json"),
            window_state: config_dir.join("window-state.json"),
            root,
            config_dir,
            runtime_dir,
        }
    }

    pub fn ensure_directories(&self) -> Result<(), ShellError> {
        for path in [
            &self.config_dir,
            &self.runtime_dir,
            &self.root.join("data"),
            &self.root.join("logs"),
            &self.root.join("updates"),
            &self.root.join("diagnostics"),
        ] {
            fs::create_dir_all(path).map_err(|error| {
                ShellError::Internal(format!("无法创建 {}: {error}", path.display()))
            })?;
        }
        Ok(())
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct ShellConfig {
    #[serde(default)]
    pub core_executable: Option<PathBuf>,
    #[serde(default)]
    pub core_args: Vec<String>,
    #[serde(default)]
    pub update_agent_executable: Option<PathBuf>,
    #[serde(default)]
    pub update_agent_args: Vec<String>,
    #[serde(default = "default_true")]
    pub autostart: bool,
}

const fn default_true() -> bool {
    true
}

impl Default for ShellConfig {
    fn default() -> Self {
        Self {
            core_executable: None,
            core_args: Vec::new(),
            update_agent_executable: None,
            update_agent_args: Vec::new(),
            autostart: true,
        }
    }
}

pub struct ShellConfigStore {
    path: PathBuf,
    value: RwLock<ShellConfig>,
}

impl ShellConfigStore {
    pub fn load(path: PathBuf) -> Result<Self, ShellError> {
        let value = if path.exists() {
            let bytes = fs::read(&path).map_err(|error| {
                ShellError::InvalidConfig(format!("无法读取 {}: {error}", path.display()))
            })?;
            serde_json::from_slice(&bytes).map_err(|error| {
                ShellError::InvalidConfig(format!("{}: {error}", path.display()))
            })?
        } else {
            ShellConfig::default()
        };
        Ok(Self {
            path,
            value: RwLock::new(value),
        })
    }

    pub fn get(&self) -> ShellConfig {
        self.value.read().expect("shell config poisoned").clone()
    }

    pub fn set_autostart(&self, enabled: bool) -> Result<(), ShellError> {
        let mut guard = self.value.write().expect("shell config poisoned");
        guard.autostart = enabled;
        self.save(&guard)
    }

    fn save(&self, value: &ShellConfig) -> Result<(), ShellError> {
        let bytes = serde_json::to_vec_pretty(value)
            .map_err(|error| ShellError::InvalidConfig(error.to_string()))?;
        atomic_write(&self.path, &bytes).map_err(|error| {
            ShellError::InvalidConfig(format!("无法保存 {}: {error}", self.path.display()))
        })
    }
}

pub fn configured_executable(
    configured: Option<&Path>,
    environment_key: &str,
    resource_dir: &Path,
    default_name: &str,
) -> Result<PathBuf, ShellError> {
    resolve_executable(
        configured,
        env::var_os(environment_key),
        resource_dir,
        default_name,
    )
}

fn resolve_executable(
    configured: Option<&Path>,
    environment: Option<std::ffi::OsString>,
    resource_dir: &Path,
    default_name: &str,
) -> Result<PathBuf, ShellError> {
    let path = environment
        .filter(|value| !value.is_empty())
        .map(PathBuf::from)
        .or_else(|| configured.map(Path::to_path_buf))
        .unwrap_or_else(|| resource_dir.join(default_name));
    if !path.is_absolute() {
        return Err(ShellError::InvalidConfig("进程路径必须为绝对路径".into()));
    }
    Ok(path)
}

#[cfg(test)]
mod tests {
    use super::{ShellConfig, ShellConfigStore};

    #[test]
    fn config_defaults_to_autostart_enabled() {
        assert!(ShellConfig::default().autostart);
    }

    #[test]
    fn bundle_maps_full_onedir_and_limits_connections_to_loopback() {
        let config: serde_json::Value = serde_json::from_str(include_str!("../tauri.conf.json")).unwrap();
        assert_eq!(config["bundle"]["resources"]["../../../dist/hqagent-core/"], "core/");
        assert_eq!(config["bundle"]["resources"]["../dist/"], "web/");
        assert_eq!(config["bundle"]["windows"]["nsis"]["installMode"], "currentUser");
        let connect = config["app"]["security"]["csp"]["connect-src"].as_array().unwrap();
        assert!(connect.contains(&serde_json::json!("http://127.0.0.1:*")));
        assert!(connect.contains(&serde_json::json!("ws://127.0.0.1:*")));
        assert!(!connect.iter().any(|v| matches!(v.as_str(), Some("*" | "http:" | "https:" | "https://*"))));
    }

    #[test]
    fn config_store_persists_autostart_choice() {
        let dir = tempfile::tempdir().expect("tempdir");
        let path = dir.path().join("desktop-shell.json");
        let store = ShellConfigStore::load(path.clone()).expect("load");
        store.set_autostart(false).expect("save");
        assert!(!ShellConfigStore::load(path).expect("reload").get().autostart);
    }

    #[test]
    fn resource_paths_and_overrides_are_independent_of_working_directory() {
        let root = tempfile::tempdir().unwrap();
        let packaged = root.path().join("core/hqagent-core.exe");
        let configured = root.path().join("custom.exe");
        let environment = root.path().join("override.exe");
        assert_eq!(super::resolve_executable(None, None, root.path(), "core/hqagent-core.exe").unwrap(), packaged);
        assert_eq!(super::resolve_executable(Some(&configured), None, root.path(), "core/hqagent-core.exe").unwrap(), configured);
        assert_eq!(super::resolve_executable(Some(&configured), Some(environment.clone().into_os_string()), root.path(), "core/hqagent-core.exe").unwrap(), environment);
        assert!(super::resolve_executable(Some(std::path::Path::new("relative.exe")), None, root.path(), "core/hqagent-core.exe").is_err());
    }
}
