"""Genel (oyun odaktayken de çalışan) kısayol tuşları: Win32 RegisterHotKey."""

from __future__ import annotations

import logging
import sys
import threading
from typing import Callable

log = logging.getLogger(__name__)

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

_MODS = {"ctrl": MOD_CONTROL, "control": MOD_CONTROL, "alt": MOD_ALT, "shift": MOD_SHIFT, "win": MOD_WIN}

_NAMED_KEYS = {
    "space": 0x20, "enter": 0x0D, "tab": 0x09, "esc": 0x1B, "escape": 0x1B,
    "insert": 0x2D, "delete": 0x2E, "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27, "pause": 0x13,
    "num0": 0x60, "num1": 0x61, "num2": 0x62, "num3": 0x63, "num4": 0x64,
    "num5": 0x65, "num6": 0x66, "num7": 0x67, "num8": 0x68, "num9": 0x69,
}


def parse_hotkey(text: str) -> tuple[int, int]:
    """"ctrl+alt+t" -> (modifiers, virtual key)."""
    parts = [p.strip().lower() for p in text.replace(" ", "").split("+") if p.strip()]
    if not parts:
        raise ValueError("boş kısayol")
    mods = 0
    for part in parts[:-1]:
        if part not in _MODS:
            raise ValueError(f"bilinmeyen değiştirici: {part}")
        mods |= _MODS[part]
    key = parts[-1]
    if len(key) == 1 and key.isalnum():
        vk = ord(key.upper())
    elif key.startswith("f") and key[1:].isdigit() and 1 <= int(key[1:]) <= 24:
        vk = 0x70 + int(key[1:]) - 1
    elif key in _NAMED_KEYS:
        vk = _NAMED_KEYS[key]
    else:
        raise ValueError(f"bilinmeyen tuş: {key}")
    return mods, vk


class HotkeyManager:
    """Kısayolları ayrı bir iş parçacığında kaydeder; basılınca geri çağırmayı çalıştırır."""

    def __init__(self, on_error: Callable[[str], None] = lambda msg: None):
        self._bindings: dict[str, tuple[str, Callable[[], None]]] = {}
        self._thread: threading.Thread | None = None
        self._thread_id = 0
        self._on_error = on_error
        self._ready = threading.Event()

    def bind(self, name: str, combo: str, callback: Callable[[], None]) -> None:
        self._bindings[name] = (combo, callback)

    def start(self) -> None:
        if sys.platform != "win32":
            log.info("Kısayollar sadece Windows'ta etkin")
            return
        self.stop()
        self._ready.clear()
        self._thread = threading.Thread(target=self._run, name="hotkeys", daemon=True)
        self._thread.start()
        self._ready.wait(2)

    def restart(self) -> None:
        self.start()

    def stop(self) -> None:
        if sys.platform != "win32" or not self._thread:
            return
        import ctypes

        WM_QUIT = 0x0012
        ctypes.windll.user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        self._thread.join(timeout=2)
        self._thread = None

    def _run(self) -> None:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        self._thread_id = kernel32.GetCurrentThreadId()
        WM_HOTKEY = 0x0312

        ids: dict[int, Callable[[], None]] = {}
        for index, (name, (combo, callback)) in enumerate(self._bindings.items(), start=1):
            try:
                mods, vk = parse_hotkey(combo)
            except ValueError as exc:
                self._on_error(f"Kısayol '{combo}' geçersiz: {exc}")
                continue
            if not user32.RegisterHotKey(None, index, mods | MOD_NOREPEAT, vk):
                self._on_error(f"Kısayol '{combo}' kaydedilemedi (başka bir program kullanıyor olabilir)")
                continue
            ids[index] = callback
        self._ready.set()

        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_HOTKEY and msg.wParam in ids:
                try:
                    ids[msg.wParam]()
                except Exception:
                    log.exception("Kısayol işlenemedi")
        for index in ids:
            user32.UnregisterHotKey(None, index)
