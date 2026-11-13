//! Python sidecar: JSON lines over stdin/stdout.

use std::io::{BufRead, BufReader, Write};
use std::os::windows::process::CommandExt;
use std::path::PathBuf;
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::Mutex;

use serde_json::{json, Value};
use tauri::{AppHandle, Emitter};

const CREATE_NO_WINDOW: u32 = 0x0800_0000;

#[derive(Default)]
pub struct Sidecar {
    child: Mutex<Option<Child>>,
    stdin: Mutex<Option<ChildStdin>>,
    error: Mutex<Option<String>>,
}

/// Folder that holds sidecar\main.py and packs\ (the project or installation folder).
pub fn app_dir() -> PathBuf {
    if let Ok(dir) = std::env::var("TURING_TRANSLATE_DIR") {
        return PathBuf::from(dir);
    }
    let exe = std::env::current_exe().unwrap_or_default();
    for dir in exe.ancestors().skip(1) {
        if dir.join("sidecar").join("main.py").is_file() {
            return dir.to_path_buf();
        }
    }
    exe.parent().map(|p| p.to_path_buf()).unwrap_or_default()
}

fn find_python(app_dir: &PathBuf) -> PathBuf {
    if let Ok(path) = std::env::var("TURING_TRANSLATE_PYTHON") {
        return PathBuf::from(path);
    }
    // The project environment carries the optional packages (ChromaDB) for the phrase memory.
    let venv = app_dir.join(".venv").join("Scripts").join("python.exe");
    if venv.is_file() {
        return venv;
    }
    let bundled = app_dir.join("python").join("python.exe");
    if bundled.is_file() {
        return bundled;
    }
    if let Ok(appdata) = std::env::var("APPDATA") {
        if let Ok(entries) = std::fs::read_dir(PathBuf::from(appdata).join("uv").join("python")) {
            let mut found: Vec<PathBuf> = entries
                .flatten()
                .map(|e| e.path().join("python.exe"))
                .filter(|p| p.is_file())
                .collect();
            found.sort();
            if let Some(path) = found.pop() {
                return path;
            }
        }
    }
    PathBuf::from("python")
}

impl Sidecar {
    pub fn start(&self, app: &AppHandle) {
        let dir = app_dir();
        let python = find_python(&dir);
        let spawned = Command::new(&python)
            .arg(dir.join("sidecar").join("main.py"))
            .arg("--app-dir")
            .arg(&dir)
            .env("PYTHONUTF8", "1")
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .creation_flags(CREATE_NO_WINDOW)
            .spawn();
        let mut child = match spawned {
            Ok(child) => child,
            Err(err) => {
                *self.error.lock().unwrap() =
                    Some(format!("Sidecar konnte nicht gestartet werden ({}): {err}", python.display()));
                return;
            }
        };
        *self.stdin.lock().unwrap() = child.stdin.take();
        if let Some(stdout) = child.stdout.take() {
            let app = app.clone();
            std::thread::spawn(move || {
                for line in BufReader::new(stdout).lines() {
                    let Ok(line) = line else { break };
                    if let Ok(value) = serde_json::from_str::<Value>(&line) {
                        let _ = app.emit("sidecar", value);
                    }
                }
                let _ = app.emit("sidecar", json!({"event": "sidecar_exit"}));
            });
        }
        *self.child.lock().unwrap() = Some(child);
    }

    pub fn send(&self, message: &Value) -> Result<(), String> {
        if let Some(err) = self.error.lock().unwrap().clone() {
            return Err(err);
        }
        let mut guard = self.stdin.lock().unwrap();
        let stdin = guard.as_mut().ok_or("Sidecar laeuft nicht.")?;
        let mut line = message.to_string();
        line.push('\n');
        stdin.write_all(line.as_bytes()).map_err(|e| e.to_string())?;
        stdin.flush().map_err(|e| e.to_string())
    }

    /// Stops the sidecar, which unloads the model and ends llama-server on its way out.
    pub fn stop(&self) {
        let _ = self.send(&json!({"cmd": "shutdown"}));
        *self.stdin.lock().unwrap() = None; // EOF als zweite Sicherung
        if let Some(mut child) = self.child.lock().unwrap().take() {
            for _ in 0..80 {
                if matches!(child.try_wait(), Ok(Some(_))) {
                    return;
                }
                std::thread::sleep(std::time::Duration::from_millis(100));
            }
            let _ = child.kill();
        }
    }
}
