use serde::Serialize;

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
        .invoke_handler(tauri::generate_handler![runtime_info])
        .run(tauri::generate_context!())
        .expect("error while running Coordination Engine");
}

#[cfg(test)]
mod tests {
    #[test]
    fn build_target_has_known_architecture() {
        assert!(!std::env::consts::ARCH.is_empty());
        assert!(!std::env::consts::OS.is_empty());
    }
}
