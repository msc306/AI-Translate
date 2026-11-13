//! Window placement: docked (AppBar) or floating.

use std::path::PathBuf;

use serde::{Deserialize, Serialize};
use tauri::{PhysicalPosition, PhysicalSize, WebviewWindow};

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
        }
    }
}

pub fn config_dir() -> PathBuf {
    PathBuf::from(std::env::var("APPDATA").unwrap_or_else(|_| ".".into())).join("TuringTranslate")
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
            MonitorInfo {
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

pub fn hwnd(window: &WebviewWindow) -> Option<isize> {
    window.hwnd().ok().map(|h| h.0 as isize)
}

/// Applies the layout. `registered` tracks whether the window is currently registered as an AppBar.
pub fn apply(window: &WebviewWindow, layout: &Layout, registered: &mut bool) -> tauri::Result<()> {
    let Some(mon) = target_monitor(window, layout) else { return Ok(()) };
    let Some(handle) = hwnd(window) else { return Ok(()) };

    if layout.mode == "docked" {
        window.set_decorations(false)?;
        window.set_resizable(false)?;
        let _ = window.set_shadow(false);
        window.set_always_on_top(true)?;
        window.set_skip_taskbar(true)?;
        let width = ((mon.width as f64) * layout.width_percent / 100.0).round() as i32;
        let width = width.clamp(220, (mon.width - 200).max(220));
        if !*registered {
            appbar::register(handle);
            *registered = true;
        }
        let rect = appbar::set_pos(
            handle,
            layout.edge == "left",
            (mon.x, mon.y, mon.x + mon.width, mon.y + mon.height),
            width,
        );
        window.set_position(PhysicalPosition::new(rect.0, rect.1))?;
        window.set_size(PhysicalSize::new((rect.2 - rect.0) as u32, (rect.3 - rect.1) as u32))?;
    } else {
        if *registered {
            appbar::remove(handle);
            *registered = false;
        }
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
