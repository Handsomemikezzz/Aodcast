#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod commands;
mod errors;
mod python_bridge;

fn main() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![
            commands::list_projects,
            commands::create_session,
            commands::start_interview,
            commands::submit_reply,
            commands::request_finish,
            commands::generate_script,
            commands::save_edited_script,
            commands::render_audio,
            commands::show_local_tts_capability,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
