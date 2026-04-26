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
const REQUIRED_RUNTIME_ROUTE: &str = "/api/v1/models/storage";

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

fn http_status(path: &str) -> Option<u16> {
    let address = format!("{DEFAULT_HOST}:{DEFAULT_PORT}");
    let mut stream = match TcpStream::connect(address) {
        Ok(stream) => stream,
        Err(_) => return None,
    };
    let _ = stream.set_read_timeout(Some(Duration::from_secs(1)));
    let _ = stream.set_write_timeout(Some(Duration::from_secs(1)));

    let request = format!(
        "GET {path} HTTP/1.1\r\nHost: {DEFAULT_HOST}:{DEFAULT_PORT}\r\nConnection: close\r\n\r\n"
    );
    if stream.write_all(request.as_bytes()).is_err() {
        return None;
    }

    let mut response = String::new();
    if stream.read_to_string(&mut response).is_err() {
        return None;
    }
    let status = response
        .lines()
        .next()
        .and_then(|line| line.split_whitespace().nth(1))
        .and_then(|code| code.parse::<u16>().ok());
    status
}

fn healthz_ready() -> bool {
    http_status("/healthz") == Some(200)
}

fn runtime_contract_ready() -> bool {
    http_status(REQUIRED_RUNTIME_ROUTE) == Some(200)
}

fn stop_runtime_on_port() {
    #[cfg(target_family = "unix")]
    {
        let output = Command::new("lsof")
            .args(["-ti", &format!("tcp:{DEFAULT_PORT}")])
            .output();
        let Ok(output) = output else {
            return;
        };
        if !output.status.success() {
            return;
        }
        let stdout = String::from_utf8_lossy(&output.stdout);
        for pid in stdout.lines().map(str::trim).filter(|pid| !pid.is_empty()) {
            let _ = Command::new("kill")
                .arg(pid)
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .status();
        }
        for _ in 0..50 {
            if !healthz_ready() {
                return;
            }
            sleep(Duration::from_millis(100));
        }
        let output = Command::new("lsof")
            .args(["-ti", &format!("tcp:{DEFAULT_PORT}")])
            .output();
        if let Ok(output) = output {
            let stdout = String::from_utf8_lossy(&output.stdout);
            for pid in stdout.lines().map(str::trim).filter(|pid| !pid.is_empty()) {
                let _ = Command::new("kill")
                    .args(["-9", pid])
                    .stdout(Stdio::null())
                    .stderr(Stdio::null())
                    .status();
            }
        }
    }
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
      if healthz_ready() && runtime_contract_ready() {
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
    if healthz_ready() && runtime_contract_ready() {
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
                if runtime_contract_ready() {
                    wait_for_runtime_ready(existing_child)?;
                    return Ok(json!({ "base_url": base_url() }));
                }
                let _ = existing_child.kill();
                let _ = existing_child.wait();
                *guard = None;
            }
            Ok(Some(_)) | Err(_) => {
                *guard = None;
            }
        }
    }

    if healthz_ready() && !runtime_contract_ready() {
        stop_runtime_on_port();
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

#[tauri::command]
pub fn pick_directory(title: Option<String>) -> Result<Value, BridgeError> {
    #[cfg(target_os = "macos")]
    {
        let prompt = title
            .unwrap_or_else(|| "Choose a model storage folder".to_string())
            .replace('"', "\\\"");
        let script = format!(
            "POSIX path of (choose folder with prompt \"{}\")",
            prompt
        );
        let output = Command::new("osascript")
            .arg("-e")
            .arg(script)
            .output()
            .map_err(|error| {
                BridgeError::with_details(
                    "pick_directory_failed",
                    format!("Failed to open directory picker: {error}"),
                    json!({}),
                )
            })?;

        if output.status.success() {
            let path = String::from_utf8_lossy(&output.stdout).trim().to_string();
            return Ok(json!({ "path": path }));
        }

        let stderr = String::from_utf8_lossy(&output.stderr);
        if stderr.contains("User canceled") || output.status.code() == Some(1) {
            return Ok(json!({ "path": Value::Null }));
        }

        return Err(BridgeError::with_details(
            "pick_directory_failed",
            format!("Directory picker exited with status {}", output.status),
            json!({ "stderr": stderr.trim() }),
        ));
    }

    #[cfg(not(target_os = "macos"))]
    {
        let _ = title;
        Err(BridgeError::new(
            "pick_directory_unsupported",
            "Directory picker is only implemented for the macOS desktop shell.",
        ))
    }
}
