use std::fs::{self, OpenOptions};
use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::thread::sleep;
use std::time::{Duration, Instant};

use serde_json::{json, Value};
use tauri::{AppHandle, Manager, State};

use crate::errors::BridgeError;

const DEFAULT_HOST: &str = "127.0.0.1";
const READY_TIMEOUT: Duration = Duration::from_secs(30);
const READY_POLL_INTERVAL: Duration = Duration::from_millis(200);
const REQUIRED_RUNTIME_ROUTE: &str = "/api/v1/voice-studio/presets";
/// Finder-launched apps do not inherit the shell PATH; ffmpeg/ffprobe/codex live here.
const EXTRA_PATH: &str = "/opt/homebrew/bin:/usr/local/bin";

struct RuntimeProcess {
    child: Child,
    port: u16,
}

#[derive(Default)]
pub struct DesktopRuntimeState {
    runtime: Mutex<Option<RuntimeProcess>>,
}

impl DesktopRuntimeState {
    pub fn stop(&self) {
        if let Ok(mut guard) = self.runtime.lock() {
            if let Some(mut process) = guard.take() {
                let _ = process.child.kill();
                let _ = process.child.wait();
            }
        }
    }
}

impl Drop for DesktopRuntimeState {
    fn drop(&mut self) {
        self.stop();
    }
}

fn base_url(port: u16) -> String {
    format!("http://{DEFAULT_HOST}:{port}")
}

fn pick_free_port() -> Result<u16, BridgeError> {
    TcpListener::bind((DEFAULT_HOST, 0))
        .and_then(|listener| listener.local_addr())
        .map(|address| address.port())
        .map_err(|error| {
            BridgeError::new(
                "python_runtime_port_unavailable",
                format!("Failed to reserve a localhost port: {error}"),
            )
        })
}

fn http_status(port: u16, path: &str) -> Option<u16> {
    let mut stream = TcpStream::connect((DEFAULT_HOST, port)).ok()?;
    let _ = stream.set_read_timeout(Some(Duration::from_secs(1)));
    let _ = stream.set_write_timeout(Some(Duration::from_secs(1)));

    let request =
        format!("GET {path} HTTP/1.1\r\nHost: {DEFAULT_HOST}:{port}\r\nConnection: close\r\n\r\n");
    stream.write_all(request.as_bytes()).ok()?;

    let mut response = String::new();
    stream.read_to_string(&mut response).ok()?;
    response
        .lines()
        .next()
        .and_then(|line| line.split_whitespace().nth(1))
        .and_then(|code| code.parse::<u16>().ok())
}

fn runtime_ready(port: u16) -> bool {
    http_status(port, "/healthz") == Some(200) && http_status(port, REQUIRED_RUNTIME_ROUTE) == Some(200)
}

fn runtime_path_env() -> String {
    match std::env::var("PATH") {
        Ok(existing) if !existing.is_empty() => format!("{EXTRA_PATH}:{existing}"),
        _ => EXTRA_PATH.to_string(),
    }
}

/// Release builds run the frozen runtime shipped in the app bundle against the
/// per-user data directory; debug builds run the repository script against `.local-data`.
fn runtime_command(app: &AppHandle, port: u16) -> Result<(Command, PathBuf), BridgeError> {
    let port_arg = port.to_string();
    let common = ["--serve-http", "--host", DEFAULT_HOST, "--port", port_arg.as_str()];

    if cfg!(debug_assertions) {
        let repo_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .ancestors()
            .nth(3)
            .map(Path::to_path_buf)
            .ok_or_else(|| {
                BridgeError::new("repo_root_not_found", "Failed to locate repository root.")
            })?;
        let script = repo_root.join("scripts/dev/run-python-core.sh");
        if !script.exists() {
            return Err(BridgeError::new(
                "python_runtime_script_missing",
                format!("Python runner script was not found at {}", script.display()),
            ));
        }
        let mut command = Command::new(&script);
        command.args(common).current_dir(&repo_root);
        return Ok((command, script));
    }

    let resource_dir = app.path().resource_dir().map_err(|error| {
        BridgeError::new(
            "python_runtime_binary_missing",
            format!("Failed to locate the app resources: {error}"),
        )
    })?;
    let binary = resource_dir.join("aodcast-runtime/aodcast-runtime");
    if !binary.exists() {
        return Err(BridgeError::new(
            "python_runtime_binary_missing",
            format!("Bundled runtime was not found at {}", binary.display()),
        ));
    }
    let data_dir = app
        .path()
        .data_dir()
        .map_err(|error| {
            BridgeError::new(
                "data_dir_unavailable",
                format!("Failed to locate the user data directory: {error}"),
            )
        })?
        .join("Aodcast");
    fs::create_dir_all(&data_dir).map_err(|error| {
        BridgeError::new(
            "data_dir_create_failed",
            format!("Failed to create {}: {error}", data_dir.display()),
        )
    })?;

    let mut command = Command::new(&binary);
    command
        .args(common)
        .arg("--cwd")
        .arg(&data_dir)
        .arg("--data-dir")
        .arg(&data_dir)
        .current_dir(&data_dir);
    Ok((command, binary))
}

fn spawn_runtime_process(app: &AppHandle, port: u16) -> Result<Child, BridgeError> {
    let (mut command, program) = runtime_command(app, port)?;
    command.env("PATH", runtime_path_env());

    let log = if cfg!(debug_assertions) {
        None
    } else {
        app.path()
            .data_dir()
            .ok()
            .map(|dir| dir.join("Aodcast/logs"))
            .and_then(|dir| fs::create_dir_all(&dir).ok().map(|_| dir.join("runtime.log")))
            .and_then(|path| OpenOptions::new().create(true).append(true).open(path).ok())
    };
    match log.and_then(|file| file.try_clone().ok().map(|clone| (file, clone))) {
        Some((out, err)) => command.stdout(Stdio::from(out)).stderr(Stdio::from(err)),
        None => command.stdout(Stdio::null()).stderr(Stdio::null()),
    };

    command.spawn().map_err(|error| {
        BridgeError::with_details(
            "python_runtime_spawn_failed",
            format!("Failed to spawn HTTP runtime: {error}"),
            json!({ "program": program.display().to_string() }),
        )
    })
}

fn wait_for_runtime_ready(child: &mut Child, port: u16) -> Result<(), BridgeError> {
    let started = Instant::now();
    while started.elapsed() < READY_TIMEOUT {
        if runtime_ready(port) {
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

#[tauri::command]
pub fn ensure_http_runtime(
    app: AppHandle,
    state: State<'_, DesktopRuntimeState>,
) -> Result<Value, BridgeError> {
    let mut guard = state.runtime.lock().map_err(|_| {
        BridgeError::new(
            "python_runtime_lock_failed",
            "Failed to lock runtime state.",
        )
    })?;

    if let Some(process) = guard.as_mut() {
        if matches!(process.child.try_wait(), Ok(None)) && runtime_ready(process.port) {
            return Ok(json!({ "base_url": base_url(process.port) }));
        }
        let _ = process.child.kill();
        let _ = process.child.wait();
        *guard = None;
    }

    let port = pick_free_port()?;
    let mut child = spawn_runtime_process(&app, port)?;
    if let Err(error) = wait_for_runtime_ready(&mut child, port) {
        let _ = child.kill();
        let _ = child.wait();
        return Err(error);
    }
    *guard = Some(RuntimeProcess { child, port });

    Ok(json!({ "base_url": base_url(port) }))
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
pub fn open_external_url(url: String) -> Result<Value, BridgeError> {
    let trimmed = url.trim();
    let allowed = trimmed.starts_with("https://chatgpt.com/")
        || trimmed.starts_with("https://auth.openai.com/");
    if !allowed {
        return Err(BridgeError::with_details(
            "external_url_rejected",
            "Only official ChatGPT authentication URLs may be opened.",
            json!({}),
        ));
    }

    #[cfg(target_os = "macos")]
    let status = Command::new("open")
        .arg(trimmed)
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status();

    #[cfg(target_os = "windows")]
    let status = Command::new("rundll32")
        .arg("url.dll,FileProtocolHandler")
        .arg(trimmed)
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status();

    #[cfg(all(not(target_os = "macos"), not(target_os = "windows")))]
    let status = Command::new("xdg-open")
        .arg(trimmed)
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status();

    match status {
        Ok(status) if status.success() => Ok(json!({ "ok": true })),
        Ok(status) => Err(BridgeError::with_details(
            "external_url_open_failed",
            format!("Browser launcher exited with status {status}"),
            json!({}),
        )),
        Err(error) => Err(BridgeError::with_details(
            "external_url_open_failed",
            format!("Failed to open the browser: {error}"),
            json!({}),
        )),
    }
}
