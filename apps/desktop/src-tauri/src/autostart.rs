use std::path::Path;

use crate::error::ShellError;

const RUN_VALUE_NAME: &str = "HQAgent-Hub";

pub struct AutostartManager;

impl AutostartManager {
    pub const fn new() -> Self {
        Self
    }

    pub fn set_enabled(&self, executable: &Path, enabled: bool) -> Result<(), ShellError> {
        set_platform_autostart(executable, enabled)
    }

    pub fn is_enabled(&self) -> Result<bool, ShellError> {
        platform_autostart_enabled()
    }
}

fn autostart_command(executable: &Path) -> Result<String, ShellError> {
    let executable = executable.as_os_str().to_string_lossy();
    if executable.contains('"') || executable.trim().is_empty() {
        return Err(ShellError::Autostart("桌面程序路径无效".into()));
    }
    Ok(format!("\"{executable}\" --minimized"))
}

#[cfg(windows)]
fn set_platform_autostart(executable: &Path, enabled: bool) -> Result<(), ShellError> {
    use winreg::{enums::HKEY_CURRENT_USER, RegKey};

    let current_user = RegKey::predef(HKEY_CURRENT_USER);
    let (run, _) = current_user
        .create_subkey("Software\\Microsoft\\Windows\\CurrentVersion\\Run")
        .map_err(|error| ShellError::Autostart(error.to_string()))?;
    if enabled {
        run.set_value(RUN_VALUE_NAME, &autostart_command(executable)?)
            .map_err(|error| ShellError::Autostart(error.to_string()))?;
    } else {
        match run.delete_value(RUN_VALUE_NAME) {
            Ok(()) => {}
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
            Err(error) => return Err(ShellError::Autostart(error.to_string())),
        }
    }
    Ok(())
}

#[cfg(windows)]
fn platform_autostart_enabled() -> Result<bool, ShellError> {
    use winreg::{enums::HKEY_CURRENT_USER, RegKey};

    let current_user = RegKey::predef(HKEY_CURRENT_USER);
    let run = match current_user.open_subkey("Software\\Microsoft\\Windows\\CurrentVersion\\Run") {
        Ok(key) => key,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(false),
        Err(error) => return Err(ShellError::Autostart(error.to_string())),
    };
    match run.get_value::<String, _>(RUN_VALUE_NAME) {
        Ok(_) => Ok(true),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(false),
        Err(error) => Err(ShellError::Autostart(error.to_string())),
    }
}

#[cfg(not(windows))]
fn set_platform_autostart(_executable: &Path, _enabled: bool) -> Result<(), ShellError> {
    Err(ShellError::Autostart(
        "Phase 1 仅支持 Windows 开机自启".into(),
    ))
}

#[cfg(not(windows))]
fn platform_autostart_enabled() -> Result<bool, ShellError> {
    Ok(false)
}

#[cfg(test)]
mod tests {
    use std::path::Path;

    use super::autostart_command;

    #[test]
    fn autostart_command_quotes_path_and_starts_minimized() {
        let command = autostart_command(Path::new("C:/Program Files/HQAgent/hqagent-desktop.exe"))
            .expect("command");
        assert_eq!(
            command,
            "\"C:/Program Files/HQAgent/hqagent-desktop.exe\" --minimized"
        );
    }
}

