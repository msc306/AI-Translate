//! Window placement: docked (AppBar on Windows, an edge strip of the work area elsewhere) or floating.

use std::path::PathBuf;

use serde::{Deserialize, Serialize};
use tauri::{PhysicalPosition, PhysicalSize, WebviewWindow};

#[cfg(windows)]
use crate::appbar;

#[derive(Clone, Copy, Serialize, Deserialize)]
pub struct Rect {
    pub x: i32,
    pub y: i32,
    pub width: u32,
    pub height: u32,
}

#[derive(Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct Layout {
    /// "docked" or "floating"
    pub mode: String,
    /// Device name of the monitor, e.g. \\.\DISPLAY3. Without it the primary monitor is used.
    pub monitor: String,
    /// "right" or "left"
    pub edge: String,
    pub width_percent: f64,
    pub floating: Option<Rect>,
    pub floating_on_top: bool,
    pub hotkey_toggle: String,
    pub hotkey_clipboard: String,
    /// starts and stops speech input
    pub hotkey_mic: String,
}

impl Default for Layout {
    fn default() -> Self {
        Self {
            mode: "docked".into(),
            monitor: r"\\.\DISPLAY3".into(),
            edge: "right".into(),
            width_percent: 25.0,
            floating: None,
            floating_on_top: false,
            hotkey_toggle: "Ctrl+Alt+T".into(),
            hotkey_clipboard: "Ctrl+Alt+U".into(),
            hotkey_mic: "Ctrl+Alt+M".into(),
        }
    }
}

pub const DATA_FOLDER: &str = "AITranslate";
/// Folder name used before the app was renamed; its contents move over once.
const OLD_DATA_FOLDER: &str = "TuringTranslate";

/// Settings folder: %APPDATA%\AITranslate on Windows, ~/Library/Application Support/AITranslate
/// on macOS, $XDG_CONFIG_HOME/AITranslate (or ~/.config) on Linux. Matches the sidecar.
pub fn config_dir() -> PathBuf {
    let home = || PathBuf::from(std::env::var("HOME").unwrap_or_else(|_| ".".into()));
    let base = if cfg!(windows) {
        PathBuf::from(std::env::var("APPDATA").unwrap_or_else(|_| ".".into()))
    } else if cfg!(target_os = "macos") {
        home().join("Library").join("Application Support")
    } else {
        std::env::var("XDG_CONFIG_HOME").map(PathBuf::from).unwrap_or_else(|_| home().join(".config"))
    };
    base.join(DATA_FOLDER)
}

/// Renames the data folders of the old name (settings in APPDATA, runtime and models in
/// LOCALAPPDATA) so nothing is lost or downloaded again. Runs before anything reads them.
/// Only Windows had the old name.
pub fn migrate_old_folders() {
    if !cfg!(windows) {
        return;
    }
    for var in ["APPDATA", "LOCALAPPDATA"] {
        let Ok(base) = std::env::var(var) else { continue };
        let old = PathBuf::from(&base).join(OLD_DATA_FOLDER);
        let new = PathBuf::from(&base).join(DATA_FOLDER);
        if old.is_dir() && !new.exists() {
            let _ = std::fs::rename(&old, &new);
        }
    }
}

fn file() -> PathBuf {
    config_dir().join("window.json")
}

impl Layout {
    /// Returns (layout, first_start).
    pub fn load() -> (Self, bool) {
        match std::fs::read_to_string(file()) {
            Ok(text) => (serde_json::from_str(&text).unwrap_or_default(), false),
            Err(_) => (Self::default(), true),
        }
    }

    pub fn save(&self) {
        let _ = std::fs::create_dir_all(config_dir());
        if let Ok(text) = serde_json::to_string_pretty(self) {
            let _ = std::fs::write(file(), text);
        }
    }
}

#[derive(Clone, Serialize)]
pub struct MonitorInfo {
    pub name: String,
    pub x: i32,
    pub y: i32,
    pub width: i32,
    pub height: i32,
    pub primary: bool,
    pub scale: f64,
    /// usable area without menu bar, Dock or taskbar
    pub work_x: i32,
    pub work_y: i32,
    pub work_width: i32,
    pub work_height: i32,
}

pub fn monitors(window: &WebviewWindow) -> Vec<MonitorInfo> {
    let primary = window
        .primary_monitor()
        .ok()
        .flatten()
        .and_then(|m| m.name().cloned())
        .unwrap_or_default();
    window
        .available_monitors()
        .unwrap_or_default()
        .iter()
        .map(|m| {
            let name = m.name().cloned().unwrap_or_default();
            let work = m.work_area();
            MonitorInfo {
                work_x: work.position.x,
                work_y: work.position.y,
                work_width: work.size.width as i32,
                work_height: work.size.height as i32,
                primary: name == primary,
                name,
                x: m.position().x,
                y: m.position().y,
                width: m.size().width as i32,
                height: m.size().height as i32,
                scale: m.scale_factor(),
            }
        })
        .collect()
}

/// The configured monitor, else the primary one, else the first.
pub fn target_monitor(window: &WebviewWindow, layout: &Layout) -> Option<MonitorInfo> {
    let all = monitors(window);
    all.iter()
        .find(|m| m.name == layout.monitor)
        .or_else(|| all.iter().find(|m| m.primary))
        .or_else(|| all.first())
        .cloned()
}

#[cfg(windows)]
pub fn hwnd(window: &WebviewWindow) -> Option<isize> {
    window.hwnd().ok().map(|h| h.0 as isize)
}

/// Reserves the strip (Windows AppBar) and returns the granted rectangle (left, top, right, bottom).
#[cfg(windows)]
fn dock_rect(window: &WebviewWindow, mon: &MonitorInfo, left: bool, width: i32, registered: &mut bool) -> Option<(i32, i32, i32, i32)> {
    let handle = hwnd(window)?;
    if !*registered {
        appbar::register(handle);
        *registered = true;
    }
    Some(appbar::set_pos(handle, left, (mon.x, mon.y, mon.x + mon.width, mon.y + mon.height), width))
}

/// macOS and Linux have no AppBar: the window covers a strip of the work area
/// (below the menu bar, beside the Dock) and stays on top.
#[cfg(not(windows))]
fn dock_rect(_window: &WebviewWindow, mon: &MonitorInfo, left: bool, width: i32, _registered: &mut bool) -> Option<(i32, i32, i32, i32)> {
    let (x, y, w, h) = if mon.work_width > 0 && mon.work_height > 0 {
        (mon.work_x, mon.work_y, mon.work_width, mon.work_height)
    } else {
        (mon.x, mon.y, mon.width, mon.height)
    };
    let width = width.min(w);
    Some(if left { (x, y, x + width, y + h) } else { (x + w - width, y, x + w, y + h) })
}

/// Gives the reserved strip back (Windows only).
pub fn release(window: &WebviewWindow, registered: &mut bool) {
    #[cfg(windows)]
    if *registered {
        if let Some(handle) = hwnd(window) {
            appbar::remove(handle);
        }
    }
    #[cfg(not(windows))]
    let _ = window;
    *registered = false;
}

/// Applies the layout. `registered` tracks whether the window is currently registered as an AppBar.
pub fn apply(window: &WebviewWindow, layout: &Layout, registered: &mut bool) -> tauri::Result<()> {
    let Some(mon) = target_monitor(window, layout) else { return Ok(()) };

    if layout.mode == "docked" {
        window.set_decorations(false)?;
        window.set_resizable(false)?;
        let _ = window.set_shadow(false);
        window.set_always_on_top(true)?;
        window.set_skip_taskbar(true)?;
        let width = ((mon.width as f64) * layout.width_percent / 100.0).round() as i32;
        let width = width.clamp(220, (mon.width - 200).max(220));
        let Some(rect) = dock_rect(window, &mon, layout.edge == "left", width, registered) else { return Ok(()) };
        window.set_position(PhysicalPosition::new(rect.0, rect.1))?;
        window.set_size(PhysicalSize::new((rect.2 - rect.0) as u32, (rect.3 - rect.1) as u32))?;
    } else {
        release(window, registered);
        window.set_decorations(true)?;
        window.set_resizable(true)?;
        let _ = window.set_shadow(true);
        window.set_always_on_top(layout.floating_on_top)?;
        window.set_skip_taskbar(false)?;
        let rect = layout.floating.unwrap_or_else(|| {
            let width = (mon.width as f64 * 0.25) as u32;
            let height = (mon.height as f64 * 0.7) as u32;
            Rect { x: mon.x + mon.width - width as i32 - 60, y: mon.y + 80, width, height }
        });
        window.set_size(PhysicalSize::new(rect.width.max(260), rect.height.max(300)))?;
        window.set_position(PhysicalPosition::new(rect.x, rect.y))?;
    }
    Ok(())
}
