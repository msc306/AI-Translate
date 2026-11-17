#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod appbar;
mod layout;
mod sidecar;

use std::sync::Mutex;

use serde_json::Value;
use tauri::menu::{Menu, MenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Emitter, Manager, RunEvent, State, WindowEvent};
use tauri_plugin_autostart::ManagerExt as _;
use tauri_plugin_clipboard_manager::ClipboardExt as _;
use tauri_plugin_dialog::DialogExt as _;
use tauri_plugin_global_shortcut::{GlobalShortcutExt as _, Shortcut, ShortcutState};

use layout::{Layout, MonitorInfo, Rect};

struct AppState {
    layout: Mutex<Layout>,
    /// true while the window is registered as an AppBar
    registered: Mutex<bool>,
    sidecar: sidecar::Sidecar,
    /// global shortcuts: show/hide, translate clipboard, speech input
    hotkeys: Mutex<[Option<Shortcut>; 3]>,
    /// interface language: de, en, es or fr
    ui_lang: Mutex<String>,
    /// tray menu entries (toggle, dock, quit), kept to rename them with the language
    tray_items: Mutex<Vec<MenuItem<tauri::Wry>>>,
}

/// Texts of the window shell in German, English, Spanish and French.
fn text(lang: &str, key: &str) -> &'static str {
    let row: [&'static str; 4] = match key {
        "toggle" => ["Anzeigen / Verbergen", "Show / Hide", "Mostrar / Ocultar", "Afficher / Masquer"],
        "dock" => ["Andocken / Lösen", "Dock / Undock", "Acoplar / Soltar", "Ancrer / Détacher"],
        "quit" => ["Beenden", "Quit", "Salir", "Quitter"],
        "pick_model" => ["Modelldatei auswählen", "Choose a model file", "Elegir archivo de modelo", "Choisir un fichier de modèle"],
        "models" => ["GGUF-Modelle", "GGUF models", "Modelos GGUF", "Modèles GGUF"],
        "pick_speech" => ["Sprachmodell auswählen", "Choose a speech model", "Elegir modelo de voz", "Choisir un modèle vocal"],
        "speech_models" => ["Whisper-Modelle (ggml)", "Whisper models (ggml)", "Modelos Whisper (ggml)", "Modèles Whisper (ggml)"],
        "pick_pack" => ["Sprachpaket auswählen", "Choose a language pack", "Elegir paquete de idioma", "Choisir un pack de langue"],
        "packs" => ["Sprachpakete", "Language packs", "Paquetes de idioma", "Packs de langue"],
        "csv" => ["CSV-Tabelle", "CSV table", "Tabla CSV", "Tableau CSV"],
        "pack" => ["Sprachpaket", "Language pack", "Paquete de idioma", "Pack de langue"],
        "save_as" => ["Speichern unter", "Save as", "Guardar como", "Enregistrer sous"],
        _ => [""; 4],
    };
    row[match lang { "en" => 1, "es" => 2, "fr" => 3, _ => 0 }]
}

fn ui_lang(app: &AppHandle) -> String {
    app.state::<AppState>().ui_lang.lock().unwrap().clone()
}

fn apply_current(app: &AppHandle) {
    let Some(window) = app.get_webview_window("main") else { return };
    let state = app.state::<AppState>();
    let current = state.layout.lock().unwrap().clone();
    let mut registered = state.registered.lock().unwrap();
    let _ = layout::apply(&window, &current, &mut registered);
}

fn show(app: &AppHandle) {
    show_window(app, true);
}

/// `focus = false` at program start: the bar appears without taking the focus from running work.
fn show_window(app: &AppHandle, focus: bool) {
    apply_current(app);
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.unminimize();
        let _ = window.show();
        if focus {
            let _ = window.set_focus();
            let _ = app.emit("shown", ());
        }
    }
}

fn release_appbar(app: &AppHandle) {
    let Some(window) = app.get_webview_window("main") else { return };
    let state = app.state::<AppState>();
    let mut registered = state.registered.lock().unwrap();
    if *registered {
        if let Some(handle) = layout::hwnd(&window) {
            appbar::remove(handle);
        }
        *registered = false;
    }
}

fn hide(app: &AppHandle) {
    release_appbar(app);
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.hide();
    }
    app.state::<AppState>().layout.lock().unwrap().save();
}

fn toggle_visible(app: &AppHandle) {
    let visible = app
        .get_webview_window("main")
        .and_then(|w| w.is_visible().ok())
        .unwrap_or(false);
    if visible {
        hide(app);
    } else {
        show(app);
    }
}

fn toggle_dock_mode(app: &AppHandle) -> Layout {
    let state = app.state::<AppState>();
    let current = {
        let mut current = state.layout.lock().unwrap();
        current.mode = if current.mode == "docked" { "floating".into() } else { "docked".into() };
        current.save();
        current.clone()
    };
    apply_current(app);
    let _ = app.emit("layout", current.clone());
    current
}

fn register_hotkeys(app: &AppHandle) {
    let state = app.state::<AppState>();
    let current = state.layout.lock().unwrap().clone();
    let shortcuts = app.global_shortcut();
    let _ = shortcuts.unregister_all();
    let toggle = current.hotkey_toggle.parse::<Shortcut>().ok();
    let clipboard = current.hotkey_clipboard.parse::<Shortcut>().ok();
    let mic = current.hotkey_mic.parse::<Shortcut>().ok();
    let keys = [toggle, clipboard, mic];
    for shortcut in keys.into_iter().flatten() {
        let _ = shortcuts.register(shortcut);
    }
    *state.hotkeys.lock().unwrap() = keys;
}

// ---------- Commands for the interface ----------

/// Native file picker. `kind` is "model" (.gguf) or "pack" (language pack .zip / manifest.json).
/// Async so the blocking dialog never runs on the main thread.
#[tauri::command]
async fn pick_file(app: AppHandle, kind: String) -> Option<String> {
    let lang = ui_lang(&app);
    let dialog = app.dialog().file();
    let dialog = match kind.as_str() {
        "model" => dialog.set_title(text(&lang, "pick_model")).add_filter(text(&lang, "models"), &["gguf"]),
        "pack" => dialog.set_title(text(&lang, "pick_pack")).add_filter(text(&lang, "packs"), &["zip", "json"]),
        "speech" => dialog.set_title(text(&lang, "pick_speech")).add_filter(text(&lang, "speech_models"), &["bin"]),
        _ => dialog,
    };
    let path = dialog.blocking_pick_file()?.into_path().ok()?;
    Some(path.to_string_lossy().into_owned())
}

/// Ask where to save an export; the sidecar writes the file.
#[tauri::command]
async fn pick_save(app: AppHandle, kind: String, name: String) -> Option<String> {
    let lang = ui_lang(&app);
    let dialog = app.dialog().file().set_file_name(name);
    let dialog = match kind.as_str() {
        "csv" => dialog.add_filter(text(&lang, "csv"), &["csv"]),
        "json" => dialog.add_filter("JSON", &["json"]),
        "md" => dialog.add_filter("Markdown", &["md"]),
        "pack" => dialog.add_filter(text(&lang, "pack"), &["zip"]),
        _ => dialog,
    };
    let path = dialog.set_title(text(&lang, "save_as")).blocking_save_file()?.into_path().ok()?;
    Some(path.to_string_lossy().into_owned())
}

#[tauri::command]
fn sidecar_send(state: State<AppState>, msg: Value) -> Result<(), String> {
    state.sidecar.send(&msg)
}

#[tauri::command]
fn get_layout(state: State<AppState>) -> Layout {
    state.layout.lock().unwrap().clone()
}

#[tauri::command]
fn set_layout(app: AppHandle, state: State<AppState>, patch: Value) -> Result<Layout, String> {
    let updated = {
        let mut current = state.layout.lock().unwrap();
        let mut merged = serde_json::to_value(&*current).map_err(|e| e.to_string())?;
        if let (Some(target), Some(source)) = (merged.as_object_mut(), patch.as_object()) {
            for (key, value) in source {
                target.insert(key.clone(), value.clone());
            }
        }
        let mut updated: Layout = serde_json::from_value(merged).map_err(|e| e.to_string())?;
        updated.width_percent = updated.width_percent.clamp(10.0, 70.0);
        *current = updated.clone();
        current.save();
        updated
    };
    apply_current(&app);
    register_hotkeys(&app);
    Ok(updated)
}

#[tauri::command]
fn resize_dock(app: AppHandle, state: State<AppState>, delta_px: i32) -> Layout {
    let updated = {
        let mut current = state.layout.lock().unwrap();
        if let Some(window) = app.get_webview_window("main") {
            if let Some(mon) = layout::target_monitor(&window, &current) {
                let width = mon.width as f64 * current.width_percent / 100.0 + delta_px as f64;
                current.width_percent = (width / mon.width as f64 * 100.0).clamp(10.0, 70.0);
            }
        }
        current.save();
        current.clone()
    };
    apply_current(&app);
    updated
}

#[tauri::command]
fn list_monitors(app: AppHandle) -> Vec<MonitorInfo> {
    app.get_webview_window("main").map(|w| layout::monitors(&w)).unwrap_or_default()
}

#[tauri::command]
fn toggle_dock(app: AppHandle) -> Layout {
    toggle_dock_mode(&app)
}

#[tauri::command]
fn hide_window(app: AppHandle) {
    hide(&app);
}

#[tauri::command]
fn quit(app: AppHandle) {
    app.exit(0);
}

#[tauri::command]
fn get_autostart(app: AppHandle) -> bool {
    app.autolaunch().is_enabled().unwrap_or(false)
}

#[tauri::command]
fn set_autostart(app: AppHandle, enabled: bool) -> Result<bool, String> {
    let manager = app.autolaunch();
    if enabled { manager.enable() } else { manager.disable() }.map_err(|e| e.to_string())?;
    Ok(manager.is_enabled().unwrap_or(false))
}

#[tauri::command]
fn read_clipboard(app: AppHandle) -> String {
    app.clipboard().read_text().unwrap_or_default()
}

#[tauri::command]
fn write_clipboard(app: AppHandle, text: String) -> Result<(), String> {
    app.clipboard().write_text(text).map_err(|e| e.to_string())
}

/// Open a web page in the default browser. Only https addresses are passed on.
#[tauri::command]
fn open_url(url: String) -> Result<(), String> {
    if !url.starts_with("https://") || url.chars().any(|c| c.is_control() || c == '"') {
        return Err("only https addresses can be opened".into());
    }
    std::process::Command::new("rundll32")
        .args(["url.dll,FileProtocolHandler", &url])
        .spawn()
        .map(|_| ())
        .map_err(|e| e.to_string())
}

/// Switch the texts of the tray menu and the file dialogs.
#[tauri::command]
fn set_ui_language(state: State<AppState>, lang: String) {
    let lang = match lang.as_str() {
        "en" | "es" | "fr" => lang,
        _ => "de".to_string(),
    };
    for (item, key) in state.tray_items.lock().unwrap().iter().zip(["toggle", "dock", "quit"]) {
        let _ = item.set_text(text(&lang, key));
    }
    *state.ui_lang.lock().unwrap() = lang;
}

fn main() {
    layout::migrate_old_folders();
    let (initial, first_run) = Layout::load();

    let app = tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| show(app)))
        .plugin(tauri_plugin_autostart::init(
            tauri_plugin_autostart::MacosLauncher::LaunchAgent,
            Some(vec!["--autostart"]),
        ))
        .plugin(tauri_plugin_clipboard_manager::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(
            tauri_plugin_global_shortcut::Builder::new()
                .with_handler(|app, shortcut, event| {
                    if event.state() != ShortcutState::Pressed {
                        return;
                    }
                    let [toggle, clipboard, mic] = *app.state::<AppState>().hotkeys.lock().unwrap();
                    if Some(*shortcut) == toggle {
                        toggle_visible(app);
                    } else if Some(*shortcut) == clipboard {
                        show(app);
                        let _ = app.emit("translate-clipboard", ());
                    } else if Some(*shortcut) == mic {
                        show(app);
                        let _ = app.emit("mic-toggle", ());
                    }
                })
                .build(),
        )
        .manage(AppState {
            layout: Mutex::new(initial),
            registered: Mutex::new(false),
            sidecar: sidecar::Sidecar::default(),
            hotkeys: Mutex::new([None, None, None]),
            ui_lang: Mutex::new("de".into()),
            tray_items: Mutex::new(Vec::new()),
        })
        .invoke_handler(tauri::generate_handler![
            sidecar_send,
            get_layout,
            set_layout,
            resize_dock,
            list_monitors,
            toggle_dock,
            hide_window,
            quit,
            get_autostart,
            set_autostart,
            read_clipboard,
            write_clipboard,
            pick_file,
            pick_save,
            open_url,
            set_ui_language
        ])
        .setup(move |app| {
            let handle = app.handle().clone();
            app.state::<AppState>().sidecar.start(&handle);

            // Switch on at the first start; later only refresh the path in case the EXE was moved.
            if first_run || app.autolaunch().is_enabled().unwrap_or(false) {
                let _ = app.autolaunch().enable();
            }
            if first_run {
                app.state::<AppState>().layout.lock().unwrap().save();
            }
            register_hotkeys(&handle);

            let show_item = MenuItem::with_id(app, "toggle", "Anzeigen / Verbergen", true, None::<&str>)?;
            let dock_item = MenuItem::with_id(app, "dock", "Andocken / Lösen", true, None::<&str>)?;
            let quit_item = MenuItem::with_id(app, "quit", "Beenden", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&show_item, &dock_item, &quit_item])?;
            *app.state::<AppState>().tray_items.lock().unwrap() =
                vec![show_item.clone(), dock_item.clone(), quit_item.clone()];
            let mut tray = TrayIconBuilder::with_id("main")
                .tooltip("AI Translate")
                .menu(&menu)
                .show_menu_on_left_click(false)
                .on_menu_event(|app, event| match event.id().as_ref() {
                    "toggle" => toggle_visible(app),
                    "dock" => {
                        toggle_dock_mode(app);
                    }
                    "quit" => app.exit(0),
                    _ => {}
                })
                .on_tray_icon_event(|tray, event| {
                    if let TrayIconEvent::Click {
                        button: MouseButton::Left,
                        button_state: MouseButtonState::Up,
                        ..
                    } = event
                    {
                        toggle_visible(tray.app_handle());
                    }
                });
            if let Some(icon) = app.default_window_icon() {
                tray = tray.icon(icon.clone());
            }
            tray.build(app)?;

            show_window(&handle, false);
            Ok(())
        })
        .on_window_event(|window, event| match event {
            WindowEvent::CloseRequested { api, .. } => {
                api.prevent_close();
                hide(window.app_handle());
            }
            WindowEvent::Moved(_) | WindowEvent::Resized(_) => {
                // Remember the position of the floating window
                let state = window.state::<AppState>();
                let Ok(mut current) = state.layout.try_lock() else { return };
                if current.mode != "floating"
                    || !window.is_visible().unwrap_or(false)
                    || window.is_minimized().unwrap_or(false)
                    || window.is_maximized().unwrap_or(false)
                {
                    return;
                }
                if let (Ok(pos), Ok(size)) = (window.outer_position(), window.inner_size()) {
                    if size.width > 0 && size.height > 0 {
                        current.floating = Some(Rect { x: pos.x, y: pos.y, width: size.width, height: size.height });
                    }
                }
            }
            _ => {}
        })
        .build(tauri::generate_context!())
        .expect("Fehler beim Start von AI Translate");

    app.run(|app, event| {
        if let RunEvent::Exit = event {
            release_appbar(app);
            let state = app.state::<AppState>();
            state.layout.lock().unwrap().save();
            state.sidecar.stop();
        }
    });
}
