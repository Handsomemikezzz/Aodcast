#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod commands;
mod errors;

use tauri::Manager;

fn main() {
    tauri::Builder::default()
        .manage(commands::DesktopRuntimeState::default())
        .invoke_handler(tauri::generate_handler![
            commands::ensure_http_runtime,
            commands::reveal_in_finder,
            commands::open_external_url,
        ])
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app, event| {
            if let tauri::RunEvent::Exit = event {
                app.state::<commands::DesktopRuntimeState>().stop();
            }
        });
}
