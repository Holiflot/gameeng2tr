"""Ekran yakalama.

Birincil yöntem DXcam (DXGI Desktop Duplication): tam ekran (exclusive fullscreen) DirectX
oyunlarını da yakalar. DXcam yoksa veya başlatılamazsa `mss` (GDI) kullanılır.
"""

from __future__ import annotations

import logging
import threading

import numpy as np

log = logging.getLogger(__name__)


def region_to_pixels(region: list[float], width: int, height: int) -> tuple[int, int, int, int]:
    left, top, right, bottom = region
    l = max(0, min(width - 1, int(round(left * width))))
    t = max(0, min(height - 1, int(round(top * height))))
    r = max(l + 1, min(width, int(round(right * width))))
    b = max(t + 1, min(height, int(round(bottom * height))))
    return l, t, r, b


class ScreenCapture:
    def __init__(self, monitor: int = 0):
        self.monitor = monitor
        self.backend = "none"
        self.width = 0
        self.height = 0
        self._lock = threading.Lock()
        self._camera = None
        self._mss = None
        self._mss_monitor = None
        self._last: dict[tuple, np.ndarray] = {}
        self._open()

    def _open(self) -> None:
        try:
            import dxcam

            self._camera = dxcam.create(output_idx=self.monitor, output_color="BGR")
            if self._camera is None:
                raise RuntimeError("dxcam.create None döndürdü")
            self.width, self.height = self._camera.width, self._camera.height
            self.backend = "dxcam"
            log.info("Yakalama: DXcam, monitör %d, %dx%d", self.monitor, self.width, self.height)
            return
        except Exception as exc:
            log.warning("DXcam kullanılamıyor (%s), mss'e geçiliyor", exc)
            self._camera = None
        try:
            import mss

            self._mss = mss.mss()
            monitors = self._mss.monitors
            index = self.monitor + 1 if self.monitor + 1 < len(monitors) else 1
            self._mss_monitor = monitors[index]
            self.width, self.height = self._mss_monitor["width"], self._mss_monitor["height"]
            self.backend = "mss"
            log.info("Yakalama: mss, monitör %d, %dx%d", self.monitor, self.width, self.height)
        except Exception as exc:
            raise RuntimeError(f"Ekran yakalama başlatılamadı: {exc}") from exc

    def _grab_box(self, box: tuple[int, int, int, int]) -> np.ndarray | None:
        if self._camera is not None:
            try:
                frame = self._camera.grab(region=box, new_frame_only=False)
            except TypeError:  # eski dxcam sürümleri
                frame = self._camera.grab(region=box)
            if frame is None:
                return self._last.get(box)
            self._last = {box: frame}
            return frame
        l, t, r, b = box
        mon = self._mss_monitor
        shot = self._mss.grab({"left": mon["left"] + l, "top": mon["top"] + t, "width": r - l, "height": b - t})
        return np.ascontiguousarray(np.asarray(shot)[..., :3])

    def grab_region(self, region: list[float]) -> np.ndarray | None:
        with self._lock:
            return self._grab_box(region_to_pixels(region, self.width, self.height))

    def grab_full(self) -> np.ndarray | None:
        with self._lock:
            return self._grab_box((0, 0, self.width, self.height))

    def close(self) -> None:
        with self._lock:
            if self._camera is not None:
                try:
                    self._camera.release()
                except Exception:
                    pass
                self._camera = None
            if self._mss is not None:
                self._mss.close()
                self._mss = None
