use serde::Serialize;
use std::sync::Mutex;
use tauri::{Emitter, Manager, PhysicalPosition, WebviewUrl, WebviewWindow, WebviewWindowBuilder};
use tauri_plugin_global_shortcut::{GlobalShortcutExt, Shortcut, ShortcutState};

#[derive(Default)]
struct AssistantShortcut(Mutex<Option<Shortcut>>);

fn assistant_overlay(app: &tauri::AppHandle) -> Result<WebviewWindow, String> {
    if let Some(window) = app.get_webview_window("assistant-overlay") {
        return Ok(window);
    }
    WebviewWindowBuilder::new(
        app,
        "assistant-overlay",
        WebviewUrl::App("index.html#/assistant/overlay".into()),
    )
    .title("ALTO assistant")
    .inner_size(680.0, 180.0)
    .min_inner_size(440.0, 140.0)
    .decorations(false)
    .resizable(false)
    .always_on_top(true)
    .skip_taskbar(true)
    .visible(false)
    .build()
    .map_err(|_| "The assistant window could not be opened.".to_string())
}

fn reveal_overlay(app: &tauri::AppHandle) -> Result<(), String> {
    let window = assistant_overlay(app)?;
    let cursor = app
        .cursor_position()
        .map_err(|_| "Current monitor is unavailable.")?;
    let monitor = app
        .monitor_from_point(cursor.x, cursor.y)
        .map_err(|_| "Current monitor is unavailable.")?
        .or(app
            .primary_monitor()
            .map_err(|_| "Primary monitor is unavailable.")?);
    if let Some(monitor) = monitor {
        let size = window
            .outer_size()
            .map_err(|_| "Assistant size is unavailable.")?;
        let position = monitor.position();
        let margin = (48.0 * monitor.scale_factor()) as i32;
        let x = position.x + (monitor.size().width as i32 - size.width as i32).max(0) / 2;
        let y = position.y + (monitor.size().height as i32 - size.height as i32 - margin).max(0);
        window
            .set_position(PhysicalPosition::new(x, y))
            .map_err(|_| "Assistant position failed.")?;
    }
    window.show().map_err(|_| "Assistant could not be shown.")?;
    window
        .set_focus()
        .map_err(|_| "Assistant focus could not be acquired.")?;
    let _ = window.emit("alto:overlay-shown", ());
    Ok(())
}

fn trusted_window(window: &WebviewWindow) -> Result<(), String> {
    if matches!(window.label(), "main" | "assistant-overlay") {
        Ok(())
    } else {
        Err("This window cannot control the assistant.".into())
    }
}

#[tauri::command]
fn show_assistant_overlay(app: tauri::AppHandle, window: WebviewWindow) -> Result<(), String> {
    trusted_window(&window)?;
    reveal_overlay(&app)
}

#[tauri::command]
fn hide_assistant_overlay(app: tauri::AppHandle, window: WebviewWindow) -> Result<(), String> {
    trusted_window(&window)?;
    if let Some(overlay) = app.get_webview_window("assistant-overlay") {
        let _ = overlay.emit("alto:overlay-hidden", ());
        overlay
            .hide()
            .map_err(|_| "Assistant could not be hidden.")?;
    }
    Ok(())
}

#[tauri::command]
fn set_assistant_shortcut(
    app: tauri::AppHandle,
    window: WebviewWindow,
    state: tauri::State<'_, AssistantShortcut>,
    enabled: bool,
    shortcut: String,
) -> Result<(), String> {
    if window.label() != "main" {
        return Err("Only Settings can change the shortcut.".into());
    }
    let mut current = state
        .0
        .lock()
        .map_err(|_| "Shortcut state is unavailable.")?;
    if !enabled {
        if let Some(previous) = current.as_ref() {
            app.global_shortcut()
                .unregister(*previous)
                .map_err(|_| "Shortcut could not be released.")?;
        }
        *current = None;
        return hide_assistant_overlay(app, window);
    }
    if shortcut.len() > 80 {
        return Err("Shortcut is too long.".into());
    }
    let proposed: Shortcut = shortcut
        .parse()
        .map_err(|_| "Shortcut format is invalid.")?;
    if current.as_ref() == Some(&proposed) {
        return Ok(());
    }
    // Register first: a conflict must not silently remove the working shortcut.
    app.global_shortcut()
        .register(proposed)
        .map_err(|_| "Shortcut is already in use or unavailable.")?;
    if let Some(previous) = current.as_ref() {
        if app.global_shortcut().unregister(*previous).is_err() {
            let _ = app.global_shortcut().unregister(proposed);
            return Err("Previous shortcut could not be released.".into());
        }
    }
    *current = Some(proposed);
    Ok(())
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct RuntimeInfo {
    app_version: String,
    architecture: &'static str,
    operating_system: &'static str,
}

#[tauri::command]
fn runtime_info(app: tauri::AppHandle) -> RuntimeInfo {
    RuntimeInfo {
        app_version: app.package_info().version.to_string(),
        architecture: std::env::consts::ARCH,
        operating_system: std::env::consts::OS,
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(AssistantShortcut::default())
        .plugin(
            tauri_plugin_global_shortcut::Builder::new()
                .with_handler(|app, _, event| {
                    if event.state() == ShortcutState::Pressed {
                        if let Some(window) = app.get_webview_window("assistant-overlay") {
                            if window.is_visible().unwrap_or(false) {
                                let _ = window.emit("alto:overlay-hidden", ());
                                let _ = window.hide();
                                return;
                            }
                        }
                        let _ = reveal_overlay(app);
                    }
                })
                .build(),
        )
        .invoke_handler(tauri::generate_handler![
            runtime_info,
            show_assistant_overlay,
            hide_assistant_overlay,
            set_assistant_shortcut,
        ])
        .run(tauri::generate_context!())
        .expect("error while running ALTO");
}

#[cfg(test)]
mod tests {
    #[test]
    fn build_target_has_known_architecture() {
        assert!(!std::env::consts::ARCH.is_empty());
        assert!(!std::env::consts::OS.is_empty());
    }
}
