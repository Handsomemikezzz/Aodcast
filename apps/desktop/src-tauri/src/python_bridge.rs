use std::path::{Path, PathBuf};
use std::process::Command;

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

    let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();
    let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();

    let envelope: BridgeEnvelope = serde_json::from_str(&stdout).map_err(|error| {
        BridgeError::with_details(
            "bridge_protocol_error",
            format!("Python bridge returned invalid JSON: {error}"),
            json!({
                "stdout": stdout,
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
                    "stdout": stdout,
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
            "stdout": stdout,
            "stderr": stderr,
            "status": output.status.code(),
        }),
    ))
}
