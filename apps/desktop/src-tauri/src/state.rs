use std::{
    env,
    path::PathBuf,
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc, Mutex,
    },
    thread::{self, JoinHandle},
    time::Duration,
};

use serde::Serialize;
use tauri::{AppHandle, Emitter, Manager, Runtime};

use crate::{
    autostart::AutostartManager,
    config::{configured_executable, AppPaths, ShellConfigStore},
    credentials::CredentialStore,
    error::ShellError,
    process_supervisor::{Component, ProcessSpec, ProcessStatus, ProcessSupervisor},
    runtime_descriptor::{HubEndpoint, HubEndpointProvider},
    tray,
};

const MAINTENANCE_POLL_INTERVAL: Duration = Duration::from_secs(2);

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct MaintenanceState {
    pub maintenance: bool,
    pub hub_instance_id: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ShellStatus {
    pub maintenance: bool,
    pub hub_instance_id: Option<String>,
    pub child_processes: Vec<ProcessStatus>,
    pub warnings: Vec<String>,
}

pub struct ShellState {
    pub paths: AppPaths,
    pub config: Arc<ShellConfigStore>,
    pub credentials: CredentialStore,
    pub autostart: AutostartManager,
    pub supervisor: Arc<ProcessSupervisor>,
    hub: Arc<HubEndpointProvider>,
    maintenance: Arc<AtomicBool>,
    hub_instance_id: Arc<Mutex<Option<String>>>,
    warnings: Arc<Mutex<Vec<String>>>,
    monitor_stop: Arc<AtomicBool>,
    monitor: Mutex<Option<JoinHandle<()>>>,
}

impl ShellState {
    pub fn new(paths: AppPaths, resource_dir: PathBuf) -> Result<Self, ShellError> {
        paths.ensure_directories()?;
        let config = Arc::new(ShellConfigStore::load(paths.shell_config.clone())?);
        let settings = config.get();
        let mut core_args = settings.core_args.clone();
        if !core_args
            .iter()
            .any(|arg| arg == "--web-dir" || arg.starts_with("--web-dir="))
            && resource_dir.join("web/index.html").is_file()
        {
            core_args.extend([
                "--web-dir".into(),
                resource_dir.join("web").to_string_lossy().into_owned(),
            ]);
        }
        let core_executable = configured_executable(
            settings.core_executable.as_deref(),
            "HQAGENT_CORE_PATH",
            &resource_dir,
            "core/hqagent-core.exe",
        )?;
        let update_agent_executable = configured_executable(
            settings.update_agent_executable.as_deref(),
            "HQAGENT_UPDATE_AGENT_PATH",
            &resource_dir,
            "hqagent-update-agent.exe",
        )?;
        let supervisor = ProcessSupervisor::start(vec![
            ProcessSpec {
                component: Component::Core,
                executable: core_executable,
                args: core_args,
                runtime_dir: paths.runtime_dir.clone(),
                descriptor_path: Some(paths.runtime_dir.join("hub.json")),
            },
            ProcessSpec {
                component: Component::UpdateAgent,
                executable: update_agent_executable,
                args: settings.update_agent_args,
                runtime_dir: paths.runtime_dir.clone(),
                descriptor_path: Some(paths.runtime_dir.join("update-agent.json")),
            },
        ]);
        let hub = Arc::new(HubEndpointProvider::new(
            paths.runtime_dir.join("hub.json"),
            Arc::clone(&supervisor),
        )?);
        Ok(Self {
            paths,
            config,
            credentials: CredentialStore::new(),
            autostart: AutostartManager::new(),
            supervisor,
            hub,
            maintenance: Arc::new(AtomicBool::new(false)),
            hub_instance_id: Arc::new(Mutex::new(None)),
            warnings: Arc::new(Mutex::new(Vec::new())),
            monitor_stop: Arc::new(AtomicBool::new(false)),
            monitor: Mutex::new(None),
        })
    }

    pub fn hub_endpoint<R: Runtime>(
        &self,
        app: Option<&AppHandle<R>>,
    ) -> Result<HubEndpoint, ShellError> {
        let (endpoint, probe) = self.hub.get_endpoint()?;
        self.apply_maintenance(app, probe.maintenance, Some(probe.instance_id));
        Ok(endpoint)
    }

    pub fn status(&self) -> ShellStatus {
        ShellStatus {
            maintenance: self.maintenance.load(Ordering::SeqCst),
            hub_instance_id: self
                .hub_instance_id
                .lock()
                .expect("hub instance poisoned")
                .clone(),
            child_processes: self.supervisor.statuses(),
            warnings: self.warnings.lock().expect("warnings poisoned").clone(),
        }
    }

    pub fn configure_autostart(&self) {
        let enabled = self.config.get().autostart;
        match env::current_exe()
            .map_err(|error| ShellError::Autostart(error.to_string()))
            .and_then(|executable| self.autostart.set_enabled(&executable, enabled))
        {
            Ok(()) => {}
            Err(error) => self.push_warning(error.to_string()),
        }
    }

    pub fn set_autostart(&self, enabled: bool) -> Result<(), ShellError> {
        let executable = env::current_exe()
            .map_err(|error| ShellError::Autostart(error.to_string()))?;
        self.autostart.set_enabled(&executable, enabled)?;
        self.config.set_autostart(enabled)
    }

    pub fn start_monitor<R: Runtime>(&self, app: AppHandle<R>) {
        let hub = Arc::clone(&self.hub);
        let maintenance = Arc::clone(&self.maintenance);
        let hub_instance_id = Arc::clone(&self.hub_instance_id);
        let stop = Arc::clone(&self.monitor_stop);
        let warnings = Arc::clone(&self.warnings);
        let supervisor = Arc::clone(&self.supervisor);
        let handle = thread::Builder::new()
            .name("hub-maintenance-monitor".into())
            .spawn(move || {
                while !stop.load(Ordering::SeqCst) {
                    match hub.get_endpoint() {
                        Ok((_endpoint, probe)) => apply_maintenance_shared(
                            &app,
                            &maintenance,
                            &hub_instance_id,
                            probe.maintenance,
                            Some(probe.instance_id),
                        ),
                        Err(error) => {
                            let mut guard = warnings.lock().expect("warnings poisoned");
                            let message = error.to_string();
                            if guard.last() != Some(&message) {
                                guard.push(message);
                                if guard.len() > 20 {
                                    guard.remove(0);
                                }
                            }
                        }
                    }
                    tray::update_status(&app, &supervisor.statuses());
                    wait_monitor(&stop, MAINTENANCE_POLL_INTERVAL);
                }
            })
            .expect("failed to start maintenance monitor");
        *self.monitor.lock().expect("monitor poisoned") = Some(handle);
    }

    pub fn shutdown(&self) {
        self.monitor_stop.store(true, Ordering::SeqCst);
        // Do not wait up to a cold bootstrap timeout before signalling the child.
        self.supervisor.shutdown();
        if let Some(handle) = self.monitor.lock().expect("monitor poisoned").take() {
            let _ = handle.join();
        }
    }

    fn apply_maintenance<R: Runtime>(
        &self,
        app: Option<&AppHandle<R>>,
        value: bool,
        instance_id: Option<String>,
    ) {
        if let Some(app) = app {
            apply_maintenance_shared(
                app,
                &self.maintenance,
                &self.hub_instance_id,
                value,
                instance_id,
            );
        } else {
            self.maintenance.store(value, Ordering::SeqCst);
            *self
                .hub_instance_id
                .lock()
                .expect("hub instance poisoned") = instance_id;
        }
    }

    fn push_warning(&self, warning: String) {
        self.warnings
            .lock()
            .expect("warnings poisoned")
            .push(warning);
    }
}

fn apply_maintenance_shared<R: Runtime>(
    app: &AppHandle<R>,
    maintenance: &AtomicBool,
    hub_instance_id: &Mutex<Option<String>>,
    value: bool,
    instance_id: Option<String>,
) {
    let previous = maintenance.swap(value, Ordering::SeqCst);
    let mut instance_guard = hub_instance_id.lock().expect("hub instance poisoned");
    let instance_changed = *instance_guard != instance_id;
    *instance_guard = instance_id.clone();
    drop(instance_guard);
    if previous == value && !instance_changed {
        return;
    }

    let snapshot = MaintenanceState {
        maintenance: value,
        hub_instance_id: instance_id,
    };
    let _ = app.emit("shell://maintenance-changed", &snapshot);
    let title = if value {
        "HQAgent-Hub — 维护模式"
    } else {
        "HQAgent-Hub"
    };
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.set_title(title);
    }
}

fn wait_monitor(stop: &AtomicBool, duration: Duration) {
    let steps = duration.as_millis() / 100;
    for _ in 0..steps {
        if stop.load(Ordering::SeqCst) {
            return;
        }
        thread::sleep(Duration::from_millis(100));
    }
}

pub fn config_process_paths(statuses: &[ProcessStatus]) -> Vec<PathBuf> {
    statuses
        .iter()
        .filter_map(|status| match status {
            ProcessStatus::Missing { path, .. }
            | ProcessStatus::Starting { path, .. }
            | ProcessStatus::WaitingDescriptor { path, .. }
            | ProcessStatus::Running { path, .. }
            | ProcessStatus::Backoff { path, .. }
            | ProcessStatus::Stopped { path, .. } => Some(PathBuf::from(path)),
        })
        .collect()
}
