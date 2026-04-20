use std::io::{Read, Write};
use std::net::TcpStream;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::thread::sleep;
use std::time::{Duration, Instant};

use serde_json::{json, Value};
use tauri::State;

use crate::errors::BridgeError;

const DEFAULT_HOST: &str = "127.0.0.1";
const DEFAULT_PORT: u16 = 8765;
const READY_TIMEOUT: Duration = Duration::from_secs(20);
const READY_POLL_INTERVAL: Duration = Duration::from_millis(200);

#[derive(Default)]
pub struct DesktopRuntimeState {
    child: Mutex<Option<Child>>,
}

fn repo_root() -> Result<PathBuf, BridgeError> {
    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    manifest_dir
        .ancestors()
        .nth(3)
        .map(Path::to_path_buf)
        .ok_or_else(|| BridgeError::new("repo_root_not_found", "Failed to locate repository root."))
}

fn runner_script(repo_root: &Path) -> PathBuf {
    repo_root.join("scripts/dev/run-python-core.sh")
}

fn base_url() -> String {
    format!("http://{DEFAULT_HOST}:{DEFAULT_PORT}")
}

fn healthz_ready() -> bool {
    let address = format!("{DEFAULT_HOST}:{DEFAULT_PORT}");
    let mut stream = match TcpStream::connect(address) {
        Ok(stream) => stream,
        Err(_) => return false,
    };
    let _ = stream.set_read_timeout(Some(Duration::from_secs(1)));
    let _ = stream.set_write_timeout(Some(Duration::from_secs(1)));

    let request = format!(
        "GET /healthz HTTP/1.1\r\nHost: {DEFAULT_HOST}:{DEFAULT_PORT}\r\nConnection: close\r\n\r\n"
    );
    if stream.write_all(request.as_bytes()).is_err() {
        return false;
    }

    let mut response = String::new();
    if stream.read_to_string(&mut response).is_err() {
        return false;
    }
    response.starts_with("HTTP/1.1 200") || response.starts_with("HTTP/1.0 200")
}

fn spawn_runtime_process(repo_root: &Path) -> Result<Child, BridgeError> {
    let script_path = runner_script(repo_root);
    if !script_path.exists() {
        return Err(BridgeError::new(
            "python_runtime_script_missing",
            format!("Python runner script was not found at {}", script_path.display()),
        ));
    }

    Command::new(&script_path)
        .args([
            "--serve-http",
            "--host",
            DEFAULT_HOST,
            "--port",
            &DEFAULT_PORT.to_string(),
        ])
        .current_dir(repo_root)
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|error| {
            BridgeError::with_details(
                "python_runtime_spawn_failed",
                format!("Failed to spawn HTTP runtime: {error}"),
                json!({
                    "script_path": script_path.display().to_string(),
                }),
            )
        })
}

fn wait_for_runtime_ready(child: &mut Child) -> Result<(), BridgeError> {
    let started = Instant::now();
    while started.elapsed() < READY_TIMEOUT {
      if healthz_ready() {
          return Ok(());
      }
      if let Ok(Some(status)) = child.try_wait() {
          return Err(BridgeError::with_details(
              "python_runtime_exited_early",
              format!("HTTP runtime exited before becoming ready: {status}"),
              json!({
                  "status": status.code(),
              }),
          ));
      }
      sleep(READY_POLL_INTERVAL);
    }

    Err(BridgeError::new(
        "python_runtime_ready_timeout",
        "Timed out waiting for the localhost HTTP runtime to become ready.",
    ))
}

impl Drop for DesktopRuntimeState {
    fn drop(&mut self) {
        if let Ok(mut guard) = self.child.lock() {
            if let Some(child) = guard.as_mut() {
                let _ = child.kill();
                let _ = child.wait();
            }
            *guard = None;
        }
    }
}

#[tauri::command]
pub fn ensure_http_runtime(state: State<'_, DesktopRuntimeState>) -> Result<Value, BridgeError> {
    if healthz_ready() {
        return Ok(json!({ "base_url": base_url() }));
    }

    let repo_root = repo_root()?;
    let mut guard = state
        .child
        .lock()
        .map_err(|_| BridgeError::new("python_runtime_lock_failed", "Failed to lock runtime state."))?;

    if let Some(existing_child) = guard.as_mut() {
        match existing_child.try_wait() {
            Ok(None) => {
                wait_for_runtime_ready(existing_child)?;
                return Ok(json!({ "base_url": base_url() }));
            }
            Ok(Some(_)) | Err(_) => {
                *guard = None;
            }
        }
    }

    let mut child = spawn_runtime_process(&repo_root)?;
    wait_for_runtime_ready(&mut child)?;
    *guard = Some(child);

    Ok(json!({ "base_url": base_url() }))
}

#[tauri::command]
pub fn reveal_in_finder(path: String) -> Result<Value, BridgeError> {
    let trimmed = path.trim();
    if trimmed.is_empty() {
        return Err(BridgeError::new(
            "reveal_path_empty",
            "Cannot reveal an empty path.",
        ));
    }

    let target = PathBuf::from(trimmed);
    if !target.exists() {
        return Err(BridgeError::with_details(
            "reveal_path_missing",
            format!("Path does not exist on disk: {}", target.display()),
            json!({ "path": target.display().to_string() }),
        ));
    }

    #[cfg(target_os = "macos")]
    let status = Command::new("open")
        .arg("-R")
        .arg(&target)
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status();

    #[cfg(target_os = "windows")]
    let status = Command::new("explorer")
        .arg(format!("/select,{}", target.display()))
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status();

    #[cfg(all(not(target_os = "macos"), not(target_os = "windows")))]
    let status = {
        let parent = target.parent().unwrap_or(target.as_path());
        Command::new("xdg-open")
            .arg(parent)
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()
    };

    match status {
        Ok(status) if status.success() => Ok(json!({ "ok": true })),
        Ok(status) => Err(BridgeError::with_details(
            "reveal_failed",
            format!("File manager exited with status {status}"),
            json!({ "path": target.display().to_string() }),
        )),
        Err(error) => Err(BridgeError::with_details(
            "reveal_failed",
            format!("Failed to launch file manager: {error}"),
            json!({ "path": target.display().to_string() }),
        )),
    }
}
