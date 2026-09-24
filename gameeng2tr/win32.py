"""Windows'a özel pencere yardımcıları (ctypes). Diğer platformlarda hiçbir şey yapmaz."""

from __future__ import annotations

import logging
import sys

log = logging.getLogger(__name__)

IS_WINDOWS = sys.platform == "win32"

GWL_EXSTYLE = -20
WS_EX_TOPMOST = 0x00000008
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_LAYERED = 0x00080000
WS_EX_NOACTIVATE = 0x08000000

HWND_TOPMOST = -1
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_NOOWNERZORDER = 0x0200

WDA_NONE = 0x0
WDA_EXCLUDEFROMCAPTURE = 0x11

if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
    user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    user32.SetWindowPos.argtypes = [
        wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT
    ]
    user32.SetWindowDisplayAffinity.argtypes = [wintypes.HWND, wintypes.DWORD]
    user32.SetWindowDisplayAffinity.restype = wintypes.BOOL


def make_overlay_window(hwnd: int) -> None:
    """Pencereyi tıklanamaz, odak almayan, görev çubuğunda görünmeyen ve en üstte yapar."""
    if not IS_WINDOWS or not hwnd:
        return
    style = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
    style |= WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_TOPMOST
    user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, style)
    keep_topmost(hwnd)


def keep_topmost(hwnd: int) -> None:
    """Oyun kendini öne aldığında overlay'i tekrar en üste çıkarır (odak çalmadan)."""
    if not IS_WINDOWS or not hwnd:
        return
    user32.SetWindowPos(
        hwnd, HWND_TOPMOST, 0, 0, 0, 0,
        SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_NOOWNERZORDER,
    )


def exclude_from_capture(hwnd: int) -> bool:
    """Pencereyi ekran yakalamadan hariç tutar (Windows 10 2004+).

    Böylece çeviri, İngilizce altyazının tam üstüne yazılsa bile OCR İngilizceyi okumaya devam eder.
    """
    if not IS_WINDOWS or not hwnd:
        return False
    ok = bool(user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE))
    if not ok:
        log.warning("SetWindowDisplayAffinity başarısız (hata %d)", ctypes.get_last_error())
    return ok
