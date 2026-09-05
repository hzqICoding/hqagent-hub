use std::{fs, path::Path};

use serde::{Deserialize, Serialize};
use tauri::{
    dpi::{PhysicalPosition, PhysicalSize},
    Position, Size, WebviewWindow,
};

use crate::{error::ShellError, fs_util::atomic_write};

const MIN_WIDTH: u32 = 960;
const MIN_HEIGHT: u32 = 640;
const MAX_REASONABLE_SIZE: u32 = 16_384;

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct WindowState {
    x: i32,
    y: i32,
    width: u32,
    height: u32,
    maximized: bool,
}

pub fn restore(window: &WebviewWindow, path: &Path) -> Result<(), ShellError> {
    if !path.exists() {
        return Ok(());
    }
    let bytes = fs::read(path).map_err(|error| ShellError::WindowState(error.to_string()))?;
    let state: WindowState = serde_json::from_slice(&bytes)
        .map_err(|error| ShellError::WindowState(error.to_string()))?;
    if !valid_size(state.width, state.height) {
        return Err(ShellError::WindowState(
            "忽略超出合理范围的窗口尺寸".into(),
        ));
    }
    window
        .set_size(Size::Physical(PhysicalSize::new(state.width, state.height)))
        .map_err(|error| ShellError::WindowState(error.to_string()))?;
    window
        .set_position(Position::Physical(PhysicalPosition::new(state.x, state.y)))
        .map_err(|error| ShellError::WindowState(error.to_string()))?;
    if state.maximized {
        window
            .maximize()
            .map_err(|error| ShellError::WindowState(error.to_string()))?;
    }
    Ok(())
}

pub fn save(window: &WebviewWindow, path: &Path) -> Result<(), ShellError> {
    if window
        .is_minimized()
        .map_err(|error| ShellError::WindowState(error.to_string()))?
    {
        return Ok(());
    }
    let position = window
        .outer_position()
        .map_err(|error| ShellError::WindowState(error.to_string()))?;
    let size = window
        .inner_size()
        .map_err(|error| ShellError::WindowState(error.to_string()))?;
    if !valid_size(size.width, size.height) {
        return Ok(());
    }
    let state = WindowState {
        x: position.x,
        y: position.y,
        width: size.width,
        height: size.height,
        maximized: window
            .is_maximized()
            .map_err(|error| ShellError::WindowState(error.to_string()))?,
    };
    let bytes = serde_json::to_vec_pretty(&state)
        .map_err(|error| ShellError::WindowState(error.to_string()))?;
    atomic_write(path, &bytes).map_err(|error| ShellError::WindowState(error.to_string()))
}

fn valid_size(width: u32, height: u32) -> bool {
    (MIN_WIDTH..=MAX_REASONABLE_SIZE).contains(&width)
        && (MIN_HEIGHT..=MAX_REASONABLE_SIZE).contains(&height)
}

#[cfg(test)]
mod tests {
    use super::valid_size;

    #[test]
    fn persisted_window_size_is_bounded() {
        assert!(valid_size(1280, 800));
        assert!(!valid_size(100, 100));
        assert!(!valid_size(50_000, 800));
    }
}
