//! Windows-AppBar: reserviert Bildschirmplatz wie die Taskleiste.

use windows::Win32::Foundation::{HWND, LPARAM, RECT};
use windows::Win32::UI::Shell::{
    SHAppBarMessage, ABE_LEFT, ABE_RIGHT, ABM_NEW, ABM_QUERYPOS, ABM_REMOVE, ABM_SETPOS, APPBARDATA,
};
use windows::Win32::UI::WindowsAndMessaging::WM_APP;

fn data(hwnd: isize) -> APPBARDATA {
    APPBARDATA {
        cbSize: std::mem::size_of::<APPBARDATA>() as u32,
        hWnd: HWND(hwnd as *mut _),
        uCallbackMessage: WM_APP + 71,
        uEdge: 0,
        rc: RECT::default(),
        lParam: LPARAM(0),
    }
}

pub fn register(hwnd: isize) {
    let mut d = data(hwnd);
    unsafe {
        SHAppBarMessage(ABM_NEW, &mut d);
    }
}

pub fn remove(hwnd: isize) {
    let mut d = data(hwnd);
    unsafe {
        SHAppBarMessage(ABM_REMOVE, &mut d);
    }
}

/// Reserviert einen Streifen der Breite `width` am linken/rechten Rand des Monitors
/// (`monitor` = left, top, right, bottom). Liefert das tatsaechlich zugeteilte Rechteck.
pub fn set_pos(hwnd: isize, left_edge: bool, monitor: (i32, i32, i32, i32), width: i32) -> (i32, i32, i32, i32) {
    let mut d = data(hwnd);
    d.uEdge = if left_edge { ABE_LEFT } else { ABE_RIGHT };
    d.rc = RECT { left: monitor.0, top: monitor.1, right: monitor.2, bottom: monitor.3 };
    if left_edge {
        d.rc.right = d.rc.left + width;
    } else {
        d.rc.left = d.rc.right - width;
    }
    unsafe {
        SHAppBarMessage(ABM_QUERYPOS, &mut d);
    }
    // Das System darf den Rand verschieben (z. B. wegen anderer Leisten): Breite wiederherstellen.
    if left_edge {
        d.rc.right = d.rc.left + width;
    } else {
        d.rc.left = d.rc.right - width;
    }
    unsafe {
        SHAppBarMessage(ABM_SETPOS, &mut d);
    }
    (d.rc.left, d.rc.top, d.rc.right, d.rc.bottom)
}
