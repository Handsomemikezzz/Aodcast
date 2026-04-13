#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod commands;
mod errors;

fn main() {
    tauri::Builder::default()
        .manage(commands::DesktopRuntimeState::default())
        .invoke_handler(tauri::generate_handler![
            commands::ensure_http_runtime,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
