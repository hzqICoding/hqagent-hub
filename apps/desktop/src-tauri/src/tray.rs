use tauri::{
    image::Image,
    menu::{Menu, MenuItem, PredefinedMenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    AppHandle, Manager, Runtime,
};

pub const TRAY_ID: &str = "hqagent-main-tray";
const SHOW_ID: &str = "show-main-window";
const QUIT_ID: &str = "quit-hqagent";
const STATUS_ID: &str = "hub-process-status";

struct TrayStatus<R: Runtime>(MenuItem<R>);

pub fn create<R: Runtime>(app: &AppHandle<R>) -> tauri::Result<()> {
    let show = MenuItem::with_id(app, SHOW_ID, "打开 HQAgent-Hub", true, None::<&str>)?;
    let status = MenuItem::with_id(app, STATUS_ID, "Hub：启动中", false, None::<&str>)?;
    let separator = PredefinedMenuItem::separator(app)?;
    let quit = MenuItem::with_id(app, QUIT_ID, "退出", true, None::<&str>)?;
    let menu = Menu::with_items(app, &[&status, &show, &separator, &quit])?;
    app.manage(TrayStatus(status));

    TrayIconBuilder::with_id(TRAY_ID)
        .icon(generated_icon())
        .tooltip("HQAgent-Hub")
        .show_menu_on_left_click(false)
        .menu(&menu)
        .on_menu_event(|app, event| match event.id().as_ref() {
            SHOW_ID => show_main_window(app),
            QUIT_ID => app.exit(0),
            _ => {}
        })
        .on_tray_icon_event(|tray, event| {
            if matches!(
                event,
                TrayIconEvent::Click {
                    button: MouseButton::Left,
                    button_state: MouseButtonState::Up,
                    ..
                } | TrayIconEvent::DoubleClick {
                    button: MouseButton::Left,
                    ..
                }
            ) {
                show_main_window(tray.app_handle());
            }
        })
        .build(app)?;
    Ok(())
}

fn hub_status_label(statuses: &[crate::process_supervisor::ProcessStatus]) -> &'static str {
    use crate::process_supervisor::{Component, ProcessStatus};
    for status in statuses {
        match status {
            ProcessStatus::Running { component: Component::Core, .. } => return "运行中",
            ProcessStatus::Missing { component: Component::Core, .. }
            | ProcessStatus::Stopped { component: Component::Core, .. } => return "已停止",
            _ => {}
        }
    }
    "启动中"
}

pub fn update_status<R: Runtime>(app: &AppHandle<R>, statuses: &[crate::process_supervisor::ProcessStatus]) {
    let label = hub_status_label(statuses);
    if let Some(status) = app.try_state::<TrayStatus<R>>() {
        let _ = status.0.set_text(format!("Hub：{label}"));
    }
    if let Some(tray) = app.tray_by_id(TRAY_ID) {
        let _ = tray.set_tooltip(Some(format!("HQAgent-Hub — {label}")));
    }
}

pub fn show_main_window<R: Runtime>(app: &AppHandle<R>) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.unminimize();
        let _ = window.show();
        let _ = window.set_focus();
    }
}

fn generated_icon() -> Image<'static> {
    const SIZE: u32 = 32;
    let mut rgba = vec![0_u8; (SIZE * SIZE * 4) as usize];
    for y in 0..SIZE {
        for x in 0..SIZE {
            let index = ((y * SIZE + x) * 4) as usize;
            let inside = (3..=28).contains(&x) && (3..=28).contains(&y);
            let h_stroke = (8..=11).contains(&x)
                || (20..=23).contains(&x)
                || ((8..=23).contains(&x) && (14..=17).contains(&y));
            let color = if inside && h_stroke {
                [255, 255, 255, 255]
            } else if inside {
                [37, 99, 235, 255]
            } else {
                [0, 0, 0, 0]
            };
            rgba[index..index + 4].copy_from_slice(&color);
        }
    }
    Image::new_owned(rgba, SIZE, SIZE)
}

#[cfg(test)]
mod tests {
    use super::generated_icon;

    #[test]
    fn generated_tray_icon_has_expected_dimensions() {
        let icon = generated_icon();
        assert_eq!(icon.width(), 32);
        assert_eq!(icon.height(), 32);
    }
}
