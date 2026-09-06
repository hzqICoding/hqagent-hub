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
    default_name: &str,
) -> Result<PathBuf, ShellError> {
    if let Some(value) = env::var_os(environment_key).filter(|value| !value.is_empty()) {
        return Ok(PathBuf::from(value));
    }
    if let Some(path) = configured {
        return Ok(path.to_path_buf());
    }
    let current = env::current_exe()
        .map_err(|error| ShellError::InvalidConfig(format!("无法定位桌面程序: {error}")))?;
    let parent = current
        .parent()
        .ok_or_else(|| ShellError::InvalidConfig("桌面程序路径没有父目录".into()))?;
    Ok(parent.join(default_name))
}

#[cfg(test)]
mod tests {
    use super::{ShellConfig, ShellConfigStore};

    #[test]
    fn config_defaults_to_autostart_enabled() {
        assert!(ShellConfig::default().autostart);
    }

    #[test]
    fn config_store_persists_autostart_choice() {
        let dir = tempfile::tempdir().expect("tempdir");
        let path = dir.path().join("desktop-shell.json");
        let store = ShellConfigStore::load(path.clone()).expect("load");
        store.set_autostart(false).expect("save");
        assert!(!ShellConfigStore::load(path).expect("reload").get().autostart);
    }
}
