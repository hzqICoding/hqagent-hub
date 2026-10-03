use std::{
    collections::HashMap,
    io::Write,
    path::PathBuf,
    process::{Child, Command, Stdio},
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc, Mutex, RwLock,
    },
    thread::{self, JoinHandle},
    time::{Duration, Instant},
};

use chrono::{DateTime, Utc};
use serde::Serialize;
use uuid::Uuid;

use crate::runtime_descriptor::{descriptor_identity, existing_instance_id};

const POLL_INTERVAL: Duration = Duration::from_millis(200);
const GRACEFUL_SHUTDOWN_TIMEOUT: Duration = Duration::from_secs(15);
const STABLE_PROCESS_WINDOW: Duration = Duration::from_secs(30);

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum Component {
    Core,
    UpdateAgent,
}

impl Component {
    pub const fn display_name(self) -> &'static str {
        match self {
            Self::Core => "hqagent-core",
            Self::UpdateAgent => "hqagent-update-agent",
        }
    }
}

#[derive(Debug, Clone)]
pub struct ProcessSpec {
    pub component: Component,
    pub executable: PathBuf,
    pub args: Vec<String>,
    pub runtime_dir: PathBuf,
    pub descriptor_path: Option<PathBuf>,
}

#[derive(Debug, Clone)]
pub struct ProcessIdentity {
    pub pid: u32,
    pub instance_id: Option<String>,
    pub launched_at: DateTime<Utc>,
    pub executable: PathBuf,
}

#[derive(Debug, Clone, Serialize)]
#[serde(tag = "state", rename_all = "snake_case")]
pub enum ProcessStatus {
    Missing {
        component: Component,
        path: String,
        message: String,
    },
    Starting {
        component: Component,
        path: String,
    },
    WaitingDescriptor {
        component: Component,
        path: String,
        pid: u32,
        launched_at: DateTime<Utc>,
    },
    Running {
        component: Component,
        path: String,
        pid: u32,
        instance_id: Option<String>,
        launched_at: DateTime<Utc>,
    },
    Backoff {
        component: Component,
        path: String,
        restart_in_ms: u64,
        message: String,
    },
    Stopped {
        component: Component,
        path: String,
        forced: bool,
    },
}

#[derive(Debug, Clone)]
struct ProcessRecord {
    status: ProcessStatus,
    identity: Option<ProcessIdentity>,
}

struct ManagedWorker {
    component: Component,
    stop: Arc<AtomicBool>,
    join: Mutex<Option<JoinHandle<()>>>,
}

pub struct ProcessSupervisor {
    records: Arc<RwLock<HashMap<Component, ProcessRecord>>>,
    workers: Vec<ManagedWorker>,
    shutdown_started: AtomicBool,
}

impl ProcessSupervisor {
    pub fn start(specs: Vec<ProcessSpec>) -> Arc<Self> {
        let records = Arc::new(RwLock::new(HashMap::new()));
        let mut workers = Vec::with_capacity(specs.len());
        for spec in specs {
            set_record(
                &records,
                spec.component,
                ProcessStatus::Starting {
                    component: spec.component,
                    path: spec.executable.display().to_string(),
                },
                None,
            );
            let stop = Arc::new(AtomicBool::new(false));
            let worker_records = Arc::clone(&records);
            let worker_stop = Arc::clone(&stop);
            let component = spec.component;
            let join = thread::Builder::new()
                .name(format!("{}-supervisor", component.display_name()))
                .spawn(move || supervise(spec, worker_records, worker_stop))
                .expect("failed to start process supervisor thread");
            workers.push(ManagedWorker {
                component,
                stop,
                join: Mutex::new(Some(join)),
            });
        }
        Arc::new(Self {
            records,
            workers,
            shutdown_started: AtomicBool::new(false),
        })
    }

    pub fn identity(&self, component: Component) -> Option<ProcessIdentity> {
        self.records
            .read()
            .expect("process records poisoned")
            .get(&component)
            .and_then(|record| record.identity.clone())
    }

    pub fn statuses(&self) -> Vec<ProcessStatus> {
        let records = self.records.read().expect("process records poisoned");
        [Component::Core, Component::UpdateAgent]
            .into_iter()
            .filter_map(|component| records.get(&component).map(|record| record.status.clone()))
            .collect()
    }

    pub fn shutdown(&self) {
        if self.shutdown_started.swap(true, Ordering::SeqCst) {
            return;
        }

        for component in [Component::Core, Component::UpdateAgent] {
            if let Some(worker) = self.workers.iter().find(|worker| worker.component == component) {
                worker.stop.store(true, Ordering::SeqCst);
                if let Some(join) = worker.join.lock().expect("worker join poisoned").take() {
                    let _ = join.join();
                }
            }
        }
    }
}

impl Drop for ProcessSupervisor {
    fn drop(&mut self) {
        self.shutdown();
    }
}

fn supervise(
    spec: ProcessSpec,
    records: Arc<RwLock<HashMap<Component, ProcessRecord>>>,
    stop: Arc<AtomicBool>,
) {
    let path = spec.executable.display().to_string();
    let mut failures = 0_u32;

    loop {
        if stop.load(Ordering::SeqCst) {
            set_record(
                &records,
                spec.component,
                ProcessStatus::Stopped {
                    component: spec.component,
                    path: path.clone(),
                    forced: false,
                },
                None,
            );
            return;
        }
        if !spec.executable.is_file() {
            set_record(
                &records,
                spec.component,
                ProcessStatus::Missing {
                    component: spec.component,
                    path: path.clone(),
                    message: format!(
                        "未找到可执行文件；可通过 desktop-shell.json 或 {} 配置",
                        executable_environment_key(spec.component)
                    ),
                },
                None,
            );
            if !wait_interruptible(&stop, Duration::from_secs(1)) {
                return;
            }
            continue;
        }

        set_record(
            &records,
            spec.component,
            ProcessStatus::Starting {
                component: spec.component,
                path: path.clone(),
            },
            None,
        );

        let launch_nonce = Uuid::new_v4().to_string();
        let prior_instance_id = spec
            .descriptor_path
            .as_deref()
            .and_then(|descriptor| existing_instance_id(spec.component, descriptor));
        let launched_at = Utc::now();
        let mut command = Command::new(&spec.executable);
        command.args(&spec.args)
            .env("HQAGENT_INSTANCE_ID", &launch_nonce)
            .env("HQAGENT_RUNTIME_DIR", &spec.runtime_dir)
            .env("HQAGENT_PARENT_CONTROL", "stdio-v1")
            .stdin(Stdio::piped())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            // Relative files from children must never be written into the install directory.
            .current_dir(&spec.runtime_dir);
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            command.creation_flags(0x08000000); // CREATE_NO_WINDOW, stdin pipe remains available.
        }
        let spawn_result = command.spawn();

        let mut child = match spawn_result {
            Ok(child) => child,
            Err(error) => {
                failures = failures.saturating_add(1);
                let delay = restart_delay(failures);
                set_record(
                    &records,
                    spec.component,
                    ProcessStatus::Backoff {
                        component: spec.component,
                        path: path.clone(),
                        restart_in_ms: delay.as_millis() as u64,
                        message: format!("启动失败: {error}"),
                    },
                    None,
                );
                if !wait_interruptible(&stop, delay) {
                    return;
                }
                continue;
            }
        };

        let pid = child.id();
        let mut identity = ProcessIdentity {
            pid,
            instance_id: None,
            launched_at,
            executable: spec.executable.clone(),
        };
        let descriptor_expected = spec.descriptor_path.is_some();
        let initial_status = if descriptor_expected {
            ProcessStatus::WaitingDescriptor {
                component: spec.component,
                path: path.clone(),
                pid,
                launched_at,
            }
        } else {
            ProcessStatus::Running {
                component: spec.component,
                path: path.clone(),
                pid,
                instance_id: None,
                launched_at,
            }
        };
        set_record(
            &records,
            spec.component,
            initial_status,
            Some(identity.clone()),
        );

        let process_started = Instant::now();
        let exit = loop {
            if stop.load(Ordering::SeqCst) {
                let forced = stop_child(&mut child);
                set_record(
                    &records,
                    spec.component,
                    ProcessStatus::Stopped {
                        component: spec.component,
                        path: path.clone(),
                        forced,
                    },
                    None,
                );
                return;
            }

            match child.try_wait() {
                Ok(Some(status)) => break format!("进程退出: {status}"),
                Ok(None) => {}
                Err(error) => break format!("读取进程状态失败: {error}"),
            }

            if identity.instance_id.is_none() {
                if let Some(descriptor_path) = spec.descriptor_path.as_deref() {
                    if let Some(instance_id) = descriptor_identity(
                        spec.component,
                        descriptor_path,
                        pid,
                        launched_at,
                        prior_instance_id.as_deref(),
                    ) {
                        identity.instance_id = Some(instance_id.clone());
                        set_record(
                            &records,
                            spec.component,
                            ProcessStatus::Running {
                                component: spec.component,
                                path: path.clone(),
                                pid,
                                instance_id: Some(instance_id),
                                launched_at,
                            },
                            Some(identity.clone()),
                        );
                    }
                }
            }

            thread::sleep(POLL_INTERVAL);
        };

        if process_started.elapsed() >= STABLE_PROCESS_WINDOW {
            failures = 0;
        }
        failures = failures.saturating_add(1);
        let delay = restart_delay(failures);
        set_record(
            &records,
            spec.component,
            ProcessStatus::Backoff {
                component: spec.component,
                path: path.clone(),
                restart_in_ms: delay.as_millis() as u64,
                message: exit,
            },
            None,
        );
        if !wait_interruptible(&stop, delay) {
            return;
        }
    }
}

fn set_record(
    records: &RwLock<HashMap<Component, ProcessRecord>>,
    component: Component,
    status: ProcessStatus,
    identity: Option<ProcessIdentity>,
) {
    records
        .write()
        .expect("process records poisoned")
        .insert(component, ProcessRecord { status, identity });
}

fn stop_child(child: &mut Child) -> bool {
    stop_child_with_timeout(child, GRACEFUL_SHUTDOWN_TIMEOUT)
}

fn stop_child_with_timeout(child: &mut Child, timeout: Duration) -> bool {
    if let Some(mut stdin) = child.stdin.take() {
        let _ = stdin.write_all(b"shutdown\n");
        let _ = stdin.flush();
    }
    let deadline = Instant::now() + timeout;
    while Instant::now() < deadline {
        match child.try_wait() {
            Ok(Some(_)) => return false,
            Ok(None) => thread::sleep(POLL_INTERVAL),
            Err(_) => break,
        }
    }
    let _ = child.kill();
    let _ = child.wait();
    true
}

fn restart_delay(failures: u32) -> Duration {
    let exponent = failures.saturating_sub(1).min(3);
    Duration::from_secs(1_u64 << exponent)
}

fn wait_interruptible(stop: &AtomicBool, duration: Duration) -> bool {
    let deadline = Instant::now() + duration;
    while Instant::now() < deadline {
        if stop.load(Ordering::SeqCst) {
            return false;
        }
        thread::sleep(POLL_INTERVAL.min(deadline.saturating_duration_since(Instant::now())));
    }
    !stop.load(Ordering::SeqCst)
}

const fn executable_environment_key(component: Component) -> &'static str {
    match component {
        Component::Core => "HQAGENT_CORE_PATH",
        Component::UpdateAgent => "HQAGENT_UPDATE_AGENT_PATH",
    }
}

#[cfg(test)]
mod tests {
    use std::{io::Read, path::PathBuf, process::Command, thread, time::{Duration, Instant}};

    use super::{restart_delay, Component, ProcessSpec, ProcessStatus, ProcessSupervisor};

    #[test]
    fn restart_backoff_is_bounded_below_ten_seconds() {
        assert_eq!(restart_delay(1), Duration::from_secs(1));
        assert_eq!(restart_delay(2), Duration::from_secs(2));
        assert_eq!(restart_delay(3), Duration::from_secs(4));
        assert_eq!(restart_delay(4), Duration::from_secs(8));
        assert_eq!(restart_delay(20), Duration::from_secs(8));
    }

    #[test]
    fn missing_executable_has_explicit_status() {
        let supervisor = ProcessSupervisor::start(vec![ProcessSpec {
            component: Component::Core,
            executable: PathBuf::from("Z:/definitely-missing/hqagent-core.exe"),
            args: Vec::new(),
            runtime_dir: PathBuf::from("Z:/definitely-missing/runtime"),
            descriptor_path: None,
        }]);
        thread::sleep(Duration::from_millis(300));
        assert!(matches!(
            supervisor.statuses().first(),
            Some(ProcessStatus::Missing { .. })
        ));
        supervisor.shutdown();
    }

    #[cfg(windows)]
    #[test]
    fn abnormal_child_exit_restarts_within_ten_seconds() {
        let dir = tempfile::tempdir().unwrap();
        let supervisor = ProcessSupervisor::start(vec![fixture_spec(dir.path())]);

        let first_pid = wait_for_pid(&supervisor, None);
        // Ask the fixture to crash, rather than depending on taskkill privileges.
        // It exits abnormally without going through the supervisor shutdown path.
        std::fs::write(dir.path().join("terminate"), "").unwrap();
        let started = std::time::Instant::now();
        let second_pid = wait_for_pid(&supervisor, Some(first_pid));
        assert_ne!(first_pid, second_pid);
        assert!(started.elapsed() < Duration::from_secs(10));
        supervisor.shutdown();
    }

    // The test binary doubles as a real managed child, so no machine-specific Python is needed.
    #[test]
    fn managed_child_fixture() {
        if std::env::var("HQAGENT_PARENT_CONTROL").as_deref() != Ok("stdio-v1") { return; }
        let runtime = PathBuf::from(std::env::var_os("HQAGENT_RUNTIME_DIR").unwrap());
        assert_eq!(std::env::current_dir().unwrap(), runtime);
        assert!(!std::env::var("HQAGENT_INSTANCE_ID").unwrap().is_empty());
        if runtime.join("crash").exists() { std::process::exit(17); }
        let crash_signal = runtime.join("terminate");
        thread::spawn(move || loop {
            if crash_signal.exists() {
                std::fs::remove_file(&crash_signal).unwrap();
                std::process::exit(17);
            }
            thread::sleep(Duration::from_millis(25));
        });
        std::fs::write(runtime.join("ready"), "ready").unwrap();
        let mut input = String::new();
        std::io::stdin().read_to_string(&mut input).unwrap(); // Must receive shutdown THEN EOF.
        std::fs::write(runtime.join("stdin.txt"), input).unwrap();
        if runtime.join("ignore-shutdown").exists() { thread::sleep(Duration::from_secs(60)); }
        std::process::exit(0);
    }

    fn fixture_spec(runtime: &std::path::Path) -> ProcessSpec {
        ProcessSpec {
            component: Component::Core,
            executable: std::env::current_exe().unwrap(),
            args: vec!["--exact".into(), "process_supervisor::tests::managed_child_fixture".into(), "--nocapture".into()],
            runtime_dir: runtime.to_path_buf(),
            descriptor_path: None,
        }
    }

    fn wait_until(mut condition: impl FnMut() -> bool) {
        let deadline = Instant::now() + Duration::from_secs(10);
        while !condition() {
            assert!(Instant::now() < deadline, "managed child condition timed out");
            thread::sleep(Duration::from_millis(25));
        }
    }

    #[test]
    fn shutdown_writes_command_then_eof_and_missing_update_agent_does_not_block_core() {
        let dir = tempfile::tempdir().unwrap();
        let mut missing = fixture_spec(dir.path());
        missing.component = Component::UpdateAgent;
        missing.executable = dir.path().join("missing-update-agent.exe");
        let supervisor = ProcessSupervisor::start(vec![fixture_spec(dir.path()), missing]);
        wait_until(|| dir.path().join("ready").exists() && supervisor.statuses().iter().any(|s| matches!(s, ProcessStatus::Missing { component: Component::UpdateAgent, .. })));
        assert!(supervisor.identity(Component::Core).is_some());
        let started = Instant::now();
        supervisor.shutdown();
        assert!(started.elapsed() < Duration::from_secs(5));
        assert_eq!(std::fs::read_to_string(dir.path().join("stdin.txt")).unwrap(), "shutdown\n");
        assert!(matches!(supervisor.statuses()[0], ProcessStatus::Stopped { forced: false, .. }));
    }

    #[test]
    fn crashing_child_restarts_with_increasing_backoff_and_stop_interrupts_wait() {
        let dir = tempfile::tempdir().unwrap();
        std::fs::write(dir.path().join("crash"), "").unwrap();
        let supervisor = ProcessSupervisor::start(vec![fixture_spec(dir.path())]);
        wait_until(|| matches!(supervisor.statuses()[0], ProcessStatus::Backoff { restart_in_ms: 1000, .. }));
        let first = Instant::now();
        wait_until(|| matches!(supervisor.statuses()[0], ProcessStatus::Backoff { restart_in_ms: 2000, .. }));
        assert!(first.elapsed() >= Duration::from_millis(900));
        let stop = Instant::now();
        supervisor.shutdown();
        assert!(stop.elapsed() < Duration::from_secs(1));
    }

    #[test]
    fn force_termination_only_after_grace_period() {
        assert_eq!(super::GRACEFUL_SHUTDOWN_TIMEOUT, Duration::from_secs(15));
        let dir = tempfile::tempdir().unwrap();
        std::fs::write(dir.path().join("ignore-shutdown"), "").unwrap();
        let spec = fixture_spec(dir.path());
        let mut child = Command::new(spec.executable).args(spec.args)
            .current_dir(dir.path()).env("HQAGENT_RUNTIME_DIR", dir.path())
            .env("HQAGENT_INSTANCE_ID", "test-instance").env("HQAGENT_PARENT_CONTROL", "stdio-v1")
            .stdin(std::process::Stdio::piped()).stdout(std::process::Stdio::null())
            .spawn().unwrap();
        wait_until(|| dir.path().join("ready").exists());
        let start = Instant::now();
        assert!(super::stop_child_with_timeout(&mut child, Duration::from_millis(500)));
        assert!(start.elapsed() >= Duration::from_millis(500));
        assert_eq!(std::fs::read_to_string(dir.path().join("stdin.txt")).unwrap(), "shutdown\n");
        assert!(child.try_wait().unwrap().is_some());
    }

    #[cfg(windows)]
    fn wait_for_pid(supervisor: &ProcessSupervisor, excluding: Option<u32>) -> u32 {
        let deadline = std::time::Instant::now() + Duration::from_secs(10);
        while std::time::Instant::now() < deadline {
            if let Some(identity) = supervisor.identity(Component::Core) {
                if Some(identity.pid) != excluding {
                    return identity.pid;
                }
            }
            thread::sleep(Duration::from_millis(100));
        }
        panic!("child did not start within ten seconds")
    }
}
