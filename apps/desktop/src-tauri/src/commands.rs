use tauri::{AppHandle, State};

use crate::{
    error::CommandError,
    runtime_descriptor::HubEndpoint,
    state::{ShellState, ShellStatus},
};

#[tauri::command]
pub fn get_hub_endpoint(
    app: AppHandle,
    state: State<'_, ShellState>,
) -> Result<HubEndpoint, CommandError> {
    state.hub_endpoint(Some(&app)).map_err(CommandError::from)
}

#[tauri::command]
pub fn get_shell_status(state: State<'_, ShellState>) -> ShellStatus {
    state.status()
}

#[tauri::command]
pub fn store_secure_credential(
    name: String,
    secret: String,
    state: State<'_, ShellState>,
) -> Result<(), CommandError> {
    state
        .credentials
        .set(&name, &secret)
        .map_err(CommandError::from)
}

#[tauri::command]
pub fn read_secure_credential(
    name: String,
    state: State<'_, ShellState>,
) -> Result<Option<String>, CommandError> {
    state.credentials.get(&name).map_err(CommandError::from)
}

#[tauri::command]
pub fn delete_secure_credential(
    name: String,
    state: State<'_, ShellState>,
) -> Result<(), CommandError> {
    state.credentials.delete(&name).map_err(CommandError::from)
}

#[tauri::command]
pub fn get_autostart_enabled(state: State<'_, ShellState>) -> Result<bool, CommandError> {
    state.autostart.is_enabled().map_err(CommandError::from)
}

#[tauri::command]
pub fn set_autostart_enabled(
    enabled: bool,
    state: State<'_, ShellState>,
) -> Result<(), CommandError> {
    state.set_autostart(enabled).map_err(CommandError::from)
}

