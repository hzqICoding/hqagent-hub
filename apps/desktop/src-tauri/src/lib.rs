mod autostart;
mod commands;
mod config;
mod credentials;
mod error;
mod fs_util;
mod platform;
pub mod process_supervisor;
mod runtime_descriptor;
mod security;
mod state;
mod tray;
mod window_state;

use std::sync::Arc;

use config::AppPaths;
use state::ShellState;
use tauri::{Manager, RunEvent, WebviewUrl, WebviewWindow, WebviewWindowBuilder, WindowEvent};

pub fn run() {
    let paths = AppPaths::discover().expect("HQAgent-Hub data directory is unavailable");
    let state = ShellState::new(paths).expect("failed to initialize HQAgent-Hub shell state");

    let app = tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _argv, _cwd| {
            tray::show_main_window(app);
        }))
        .manage(state)
        .setup(|app| {
            let state = app.state::<ShellState>();
            let window = create_main_window(app.handle())?;
            if let Err(error) = window_state::restore(&window, &state.paths.window_state) {
                eprintln!("window state restore skipped: {error}");
            }
            setup_window_events(&window, state.paths.window_state.clone());
            tray::create(app.handle())?;
            state.configure_autostart();
            state.start_monitor(app.handle().clone());

            let minimized = std::env::args().any(|arg| arg == "--minimized");
            if !minimized {
                window.show()?;
                window.set_focus()?;
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            commands::get_hub_endpoint,
            commands::get_shell_status,
            commands::store_secure_credential,
            commands::read_secure_credential,
            commands::delete_secure_credential,
            commands::get_autostart_enabled,
            commands::set_autostart_enabled,
        ])
        .build(tauri::generate_context!())
        .expect("failed to build HQAgent-Hub desktop shell");

    app.run(|app_handle, event| {
        if matches!(event, RunEvent::Exit) {
            if let Some(window) = app_handle.get_webview_window("main") {
                let state = app_handle.state::<ShellState>();
                let _ = window_state::save(&window, &state.paths.window_state);
                state.shutdown();
            }
        }
    });
}

fn create_main_window(app: &tauri::AppHandle) -> tauri::Result<WebviewWindow> {
    let url = if cfg!(debug_assertions) {
        app.config()
            .build
            .dev_url
            .clone()
            .map(WebviewUrl::External)
            .unwrap_or_else(|| WebviewUrl::App("index.html".into()))
    } else {
        WebviewUrl::App("index.html".into())
    };
    WebviewWindowBuilder::new(app, "main", url)
        .title("HQAgent-Hub")
        .inner_size(1280.0, 800.0)
        .min_inner_size(960.0, 640.0)
        .resizable(true)
        .decorations(true)
        .visible(false)
        .on_navigation(|url| security::navigation_allowed(url, cfg!(debug_assertions)))
        .build()
}

fn setup_window_events(window: &WebviewWindow, state_path: std::path::PathBuf) {
    let window_handle = window.clone();
    window.on_window_event(move |event| match event {
        WindowEvent::CloseRequested { api, .. } => {
            let _ = window_state::save(&window_handle, &state_path);
            api.prevent_close();
            let _ = window_handle.hide();
        }
        WindowEvent::Moved(_) | WindowEvent::Resized(_) => {
            let _ = window_state::save(&window_handle, &state_path);
        }
        _ => {}
    });
}
