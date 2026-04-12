use std::io::{BufRead, BufReader, Read};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};

use serde::Deserialize;
use serde_json::{json, Value};

use crate::errors::BridgeError;

#[derive(Debug, Deserialize)]
struct BridgeEnvelope {
    ok: bool,
    #[serde(default)]
    data: Option<Value>,
    #[serde(default)]
    error: Option<BridgeError>,
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

pub fn run_python_bridge(args: &[String]) -> Result<Value, BridgeError> {
    let repo_root = repo_root()?;
    let script_path = runner_script(&repo_root);
    if !script_path.exists() {
        return Err(BridgeError::new(
            "python_bridge_script_missing",
            format!("Python runner script was not found at {}", script_path.display()),
        ));
    }

    let output = Command::new(&script_path)
        .args(args)
        .arg("--bridge-json")
        .current_dir(&repo_root)
        .output()
        .map_err(|error| {
            BridgeError::with_details(
                "python_bridge_exec_failed",
                format!("Failed to execute Python bridge: {error}"),
                json!({
                    "script_path": script_path.display().to_string(),
                }),
            )
        })?;

    let stdout_raw = String::from_utf8_lossy(&output.stdout).to_string();
    let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();

    let mut final_json = String::new();
    for line in stdout_raw.lines() {
        if line.starts_with("AOD_FINAL_RESPONSE: ") {
            final_json = line[20..].to_string();
            break;
        }
    }

    if final_json.is_empty() {
        return Err(BridgeError::with_details(
            "bridge_missing_data",
            "Python bridge did not output AOD_FINAL_RESPONSE marker.",
            json!({
                "stdout": stdout_raw,
                "stderr": stderr,
                "status": output.status.code(),
            }),
        ));
    }

    let envelope: BridgeEnvelope = serde_json::from_str(&final_json).map_err(|error| {
        BridgeError::with_details(
            "bridge_protocol_error",
            format!("Python bridge returned invalid JSON: {error}"),
            json!({
                "stdout": final_json,
                "stderr": stderr,
                "status": output.status.code(),
            }),
        )
    })?;

    if envelope.ok {
        return envelope.data.ok_or_else(|| {
            BridgeError::with_details(
                "bridge_missing_data",
                "Python bridge succeeded without a data payload.",
                json!({
                    "stdout": final_json,
                }),
            )
        });
    }

    if let Some(error) = envelope.error {
        return Err(error);
    }

    Err(BridgeError::with_details(
        "bridge_unknown_error",
        "Python bridge reported failure without an error payload.",
        json!({
            "stdout": final_json,
            "stderr": stderr,
            "status": output.status.code(),
        }),
    ))
}

pub fn run_python_bridge_stream<F>(args: &[String], mut on_line: F) -> Result<Value, BridgeError>
where
    F: FnMut(String) -> Result<(), BridgeError>,
{
    let repo_root = repo_root()?;
    let script_path = runner_script(&repo_root);
    if !script_path.exists() {
        return Err(BridgeError::new(
            "python_bridge_script_missing",
            format!("Python runner script was not found at {}", script_path.display()),
        ));
    }

    let mut child = Command::new(&script_path)
        .args(args)
        .arg("--bridge-json")
        .current_dir(&repo_root)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|error| {
            BridgeError::with_details(
                "python_bridge_spawn_failed",
                format!("Failed to spawn Python bridge: {error}"),
                json!({
                    "script_path": script_path.display().to_string(),
                }),
            )
        })?;

    let stdout = child.stdout.take().ok_or_else(|| {
        BridgeError::new("python_bridge_stdout_missing", "Failed to capture stdout.")
    })?;
    let stderr = child.stderr.take().ok_or_else(|| {
        BridgeError::new("python_bridge_stderr_missing", "Failed to capture stderr.")
    })?;

    let mut final_stdout = String::new();
    let reader = BufReader::new(stdout);
    for line in reader.lines() {
        let line = line.map_err(|e| BridgeError::new("python_bridge_read_failed", e.to_string()))?;
        let trimmed = line.trim();
        if trimmed.is_empty() {
            continue;
        }

        if trimmed.starts_with("AOD_FINAL_RESPONSE: ") {
            final_stdout = trimmed[20..].to_string();
        } else {
            // Pass any other line (chunks, logs, etc.) to the callback
            on_line(line)?;
        }
    }

    let status = child.wait().map_err(|e| {
        BridgeError::new("python_bridge_wait_failed", e.to_string())
    })?;

    if !status.success() {
        let mut stderr_content = String::new();
        let _ = BufReader::new(stderr).read_to_string(&mut stderr_content);
        return Err(BridgeError::with_details(
            "python_bridge_exit_error",
            format!("Python bridge exited with status {}", status),
            json!({
                "stdout": final_stdout,
                "stderr": stderr_content,
                "status": status.code(),
            }),
        ));
    }

    if final_stdout.is_empty() {
        return Err(BridgeError::new(
            "bridge_missing_data",
            "Python bridge finished without returning a JSON payload.",
        ));
    }

    let envelope: BridgeEnvelope = serde_json::from_str(&final_stdout).map_err(|error| {
        BridgeError::with_details(
            "bridge_protocol_error",
            format!("Python bridge returned invalid JSON: {error}"),
            json!({
                "stdout": final_stdout,
            }),
        )
    })?;

    if envelope.ok {
        return envelope.data.ok_or_else(|| {
            BridgeError::new("bridge_missing_data", "Python bridge succeeded without data.")
        });
    }

    if let Some(error) = envelope.error {
        return Err(error);
    }

    Err(BridgeError::new("bridge_unknown_error", "Python bridge failed without error payload."))
}
