use serde_json::Value;

use crate::errors::BridgeError;
use crate::python_bridge::{run_python_bridge, run_python_bridge_stream};

#[tauri::command]
pub fn list_projects(search: Option<String>, include_deleted: Option<bool>) -> Result<Value, BridgeError> {
    let mut args = vec!["--list-projects".to_string()];
    if let Some(value) = search.filter(|value| !value.trim().is_empty()) {
        args.push("--search".to_string());
        args.push(value);
    }
    if include_deleted.unwrap_or(false) {
        args.push("--include-deleted".to_string());
    }
    run_python_bridge(&args)
}

#[tauri::command]
pub fn create_session(topic: String, creation_intent: String) -> Result<Value, BridgeError> {
    run_python_bridge(&[
        "--create-session".to_string(),
        "--topic".to_string(),
        topic,
        "--intent".to_string(),
        creation_intent,
    ])
}

#[tauri::command]
pub fn show_session(session_id: String, include_deleted: Option<bool>) -> Result<Value, BridgeError> {
    let mut args = vec!["--show-session".to_string(), session_id];
    if include_deleted.unwrap_or(false) {
        args.push("--include-deleted".to_string());
    }
    run_python_bridge(&args)
}

#[tauri::command]
pub fn rename_session(session_id: String, topic: String) -> Result<Value, BridgeError> {
    run_python_bridge(&[
        "--rename-session".to_string(),
        session_id,
        "--session-topic".to_string(),
        topic,
    ])
}

#[tauri::command]
pub fn delete_session(session_id: String) -> Result<Value, BridgeError> {
    run_python_bridge(&["--delete-session".to_string(), session_id])
}

#[tauri::command]
pub fn restore_session(session_id: String) -> Result<Value, BridgeError> {
    run_python_bridge(&["--restore-session".to_string(), session_id])
}

#[tauri::command]
pub fn start_interview(session_id: String) -> Result<Value, BridgeError> {
    run_python_bridge(&["--start-interview".to_string(), session_id])
}

#[tauri::command]
pub fn submit_reply(
    session_id: String,
    message: String,
    user_requested_finish: bool,
) -> Result<Value, BridgeError> {
    let mut args = vec![
        "--reply-session".to_string(),
        session_id,
        "--message".to_string(),
        message,
    ];
    if user_requested_finish {
        args.push("--user-requested-finish".to_string());
    }
    run_python_bridge(&args)
}

#[tauri::command]
pub async fn submit_reply_stream(
    session_id: String,
    message: String,
    user_requested_finish: bool,
    channel: tauri::ipc::Channel<Value>,
) -> Result<Value, BridgeError> {
    let mut args = vec![
        "--reply-session".to_string(),
        session_id,
        "--message".to_string(),
        message,
    ];
    if user_requested_finish {
        args.push("--user-requested-finish".to_string());
    }

    tauri::async_runtime::spawn_blocking(move || {
        run_python_bridge_stream(&args, |line| {
            let trimmed = line.trim();
            if trimmed.starts_with("AOD_STREAM_CHUNK: ") {
                let json_part = &trimmed[18..];
                if let Ok(chunk_val) = serde_json::from_str::<Value>(json_part) {
                    let _ = channel.send(chunk_val);
                }
            }
            Ok(())
        })
    })
    .await
    .map_err(|e| BridgeError::new("spawn_blocking_error", e.to_string()))?
}

#[tauri::command]
pub fn request_finish(session_id: String) -> Result<Value, BridgeError> {
    run_python_bridge(&["--finish-session".to_string(), session_id])
}

#[tauri::command]
pub fn generate_script(session_id: String) -> Result<Value, BridgeError> {
    run_python_bridge(&["--generate-script".to_string(), session_id])
}

#[tauri::command]
pub fn save_edited_script(session_id: String, final_text: String) -> Result<Value, BridgeError> {
    run_python_bridge(&[
        "--save-script".to_string(),
        session_id,
        "--script-final-text".to_string(),
        final_text,
    ])
}

#[tauri::command]
pub fn delete_script(session_id: String) -> Result<Value, BridgeError> {
    run_python_bridge(&["--delete-script".to_string(), session_id])
}

#[tauri::command]
pub fn restore_script(session_id: String) -> Result<Value, BridgeError> {
    run_python_bridge(&["--restore-script".to_string(), session_id])
}

#[tauri::command]
pub fn list_script_revisions(session_id: String) -> Result<Value, BridgeError> {
    run_python_bridge(&["--list-script-revisions".to_string(), session_id])
}

#[tauri::command]
pub fn rollback_script_revision(session_id: String, revision_id: String) -> Result<Value, BridgeError> {
    run_python_bridge(&[
        "--rollback-script-revision".to_string(),
        session_id,
        "--revision-id".to_string(),
        revision_id,
    ])
}

#[tauri::command]
pub fn render_audio(session_id: String) -> Result<Value, BridgeError> {
    run_python_bridge(&["--render-audio".to_string(), session_id])
}

#[tauri::command]
pub fn show_local_tts_capability() -> Result<Value, BridgeError> {
    run_python_bridge(&["--show-local-tts-capability".to_string()])
}

#[tauri::command]
pub fn show_llm_config() -> Result<Value, BridgeError> {
    run_python_bridge(&["--show-llm-config".to_string()])
}

#[tauri::command]
pub fn configure_llm_provider(
    provider: String,
    model: String,
    base_url: String,
    api_key: String,
) -> Result<Value, BridgeError> {
    run_python_bridge(&[
        "--configure-llm-provider".to_string(),
        provider,
        "--llm-model".to_string(),
        model,
        "--llm-base-url".to_string(),
        base_url,
        "--llm-api-key".to_string(),
        api_key,
    ])
}

#[tauri::command]
pub fn show_tts_config() -> Result<Value, BridgeError> {
    run_python_bridge(&["--show-tts-config".to_string()])
}

#[tauri::command]
pub fn configure_tts_provider(
    provider: String,
    model: Option<String>,
    base_url: Option<String>,
    api_key: Option<String>,
    voice: Option<String>,
    audio_format: Option<String>,
    local_runtime: Option<String>,
    local_model_path: Option<String>,
    clear_local_model_path: bool,
) -> Result<Value, BridgeError> {
    let mut args = vec!["--configure-tts-provider".to_string(), provider];
    if let Some(value) = model {
        args.push("--tts-model".to_string());
        args.push(value);
    }
    if let Some(value) = base_url {
        args.push("--tts-base-url".to_string());
        args.push(value);
    }
    if let Some(value) = api_key {
        args.push("--tts-api-key".to_string());
        args.push(value);
    }
    if let Some(value) = voice {
        args.push("--tts-voice".to_string());
        args.push(value);
    }
    if let Some(value) = audio_format {
        args.push("--tts-audio-format".to_string());
        args.push(value);
    }
    if let Some(value) = local_runtime {
        args.push("--tts-local-runtime".to_string());
        args.push(value);
    }
    if clear_local_model_path {
        args.push("--clear-tts-local-model-path".to_string());
    }
    if let Some(value) = local_model_path {
        args.push("--tts-local-model-path".to_string());
        args.push(value);
    }
    run_python_bridge(&args)
}

#[tauri::command]
pub fn list_models_status() -> Result<Value, BridgeError> {
    run_python_bridge(&["--list-models-status".to_string()])
}

#[tauri::command]
pub fn download_model(model_name: String) -> Result<Value, BridgeError> {
    run_python_bridge(&["--download-model".to_string(), model_name])
}

#[tauri::command]
pub fn delete_model(model_name: String) -> Result<Value, BridgeError> {
    run_python_bridge(&["--delete-model".to_string(), model_name])
}

#[tauri::command]
pub fn show_task_state(task_id: String) -> Result<Value, BridgeError> {
    run_python_bridge(&["--show-task-state".to_string(), task_id])
}

#[tauri::command]
pub fn cancel_task(task_id: String) -> Result<Value, BridgeError> {
    run_python_bridge(&["--cancel-task".to_string(), task_id])
}
