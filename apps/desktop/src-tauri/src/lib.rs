mod autostart;
mod commands;
mod config;
mod credentials;
mod diagnostics;
mod error;
mod fs_util;
mod platform;
pub mod process_supervisor;
mod runtime_descriptor;
mod security;
mod state;
mod tray;
mod window_state;

use std::sync::{
    atomic::{AtomicBool, Ordering},
    Arc,
};

use config::AppPaths;
use state::ShellState;
use tauri::{Manager, RunEvent, WebviewUrl, WebviewWindow, WebviewWindowBuilder, WindowEvent};

pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _argv, _cwd| {
            tray::show_main_window(app);
        }))
        .setup(|app| {
            // Plugin single-instance detection must run before launching managed children.
            let paths = AppPaths::discover()?;
            app.manage(ShellState::new(paths, app.path().resource_dir()?)?);
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

    let exit_started = AtomicBool::new(false);
    let exit_ready = Arc::new(AtomicBool::new(false));
    app.run(move |app_handle, event| {
        if let RunEvent::ExitRequested { api, .. } = &event {
            if !exit_ready.load(Ordering::SeqCst) {
                api.prevent_exit();
                if !exit_started.swap(true, Ordering::SeqCst) {
                    let app = app_handle.clone();
                    let ready = Arc::clone(&exit_ready);
                    // Keep the UI event loop alive while joining the monitor: it may be
                    // waiting for a tray/window update on the main thread.
                    std::thread::spawn(move || {
                        app.state::<ShellState>().shutdown();
                        ready.store(true, Ordering::SeqCst);
                        app.exit(0);
                    });
                }
            }
        }
        if matches!(event, RunEvent::Exit) {
            let state = app_handle.state::<ShellState>();
            if let Some(window) = app_handle.get_webview_window("main") {
                let _ = window_state::save(&window, &state.paths.window_state);
            }
            state.shutdown();
            diagnostics::event("INFO", "shell_exit completed");
            diagnostics::flush();
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
        .data_directory(app.state::<ShellState>().paths.root.join("webview"))
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
            diagnostics::event("INFO", "window_close action=hide_to_tray");
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
