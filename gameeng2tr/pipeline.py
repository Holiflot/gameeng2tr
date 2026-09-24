"""Yakalama -> OCR -> altyazı takibi döngüsü (ayrı iş parçacığında)."""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable

from .config import Settings
from .ocr import OcrEngine, OcrUnavailable, create_ocr
from .preprocess import high_contrast, signature_changed, text_signature
from .textproc import SubtitleEvent, SubtitleTracker, clean_ocr_lines, looks_like_text

log = logging.getLogger(__name__)

FORCE_OCR_EVERY = 1.5  # görüntü değişmese de en az bu sıklıkla OCR yap (sn)


class CapturePipeline:
    def __init__(
        self,
        settings: Settings,
        get_capture: Callable,
        on_event: Callable[[SubtitleEvent], None],
        on_status: Callable[[str], None] = lambda msg: None,
        on_metrics: Callable[[dict], None] = lambda m: None,
        on_ocr_ready: Callable[[str], None] = lambda label: None,
        on_stopped: Callable[[], None] = lambda: None,
    ):
        self.settings = settings
        self._get_capture = get_capture
        self._on_event = on_event
        self._on_status = on_status
        self._on_metrics = on_metrics
        self._on_ocr_ready = on_ocr_ready
        self._on_stopped = on_stopped
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._ocr: OcrEngine | None = None
        self._ocr_name: str | None = None
        self._reset_requested = threading.Event()

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="capture", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        self._thread = None

    def reset(self) -> None:
        """Bölge/OCR ayarı değişince takip durumunu sıfırlar."""
        self._reset_requested.set()

    def close(self) -> None:
        self.stop()
        if self._ocr is not None:
            self._ocr.close()
            self._ocr = None

    def _ensure_ocr(self) -> OcrEngine:
        wanted = self.settings.ocr_backend
        if self._ocr is None or self._ocr_name != wanted:
            if self._ocr is not None:
                self._ocr.close()
                self._ocr = None
            self._on_status("OCR motoru yükleniyor...")
            engine, errors = create_ocr(wanted)
            for err in errors:
                log.info(err)
            self._ocr, self._ocr_name = engine, wanted
            self._on_ocr_ready(engine.label)
        return self._ocr

    def _run(self) -> None:
        try:
            self._loop()
        except OcrUnavailable as exc:
            log.error("%s", exc)
            self._on_status(str(exc))
            self._on_stopped()
        except Exception as exc:
            log.exception("Yakalama döngüsü çöktü")
            self._on_status(f"Hata: {exc}")
            self._on_stopped()

    def _loop(self) -> None:
        settings = self.settings
        tracker = SubtitleTracker(settings.stable_frames, settings.clear_after)
        prev_sig = None
        last_text = ""
        last_ocr_at = 0.0
        ocr_ms = 0.0

        ocr = self._ensure_ocr()
        self._on_status("Çalışıyor")
        while not self._stop.is_set():
            period = 1.0 / settings.capture_fps
            tick = time.perf_counter()

            if self._reset_requested.is_set():
                self._reset_requested.clear()
                tracker = SubtitleTracker(settings.stable_frames, settings.clear_after)
                prev_sig, last_text = None, ""
                ocr = self._ensure_ocr()

            capture = self._get_capture()
            frame = capture.grab_region(settings.region) if capture else None
            if frame is not None:
                sig = text_signature(frame)
                now = time.perf_counter()
                if signature_changed(prev_sig, sig) or now - last_ocr_at >= FORCE_OCR_EVERY:
                    prev_sig = sig
                    image = high_contrast(frame) if settings.high_contrast else frame
                    t0 = time.perf_counter()
                    try:
                        lines = ocr.recognize(image)
                    except Exception:
                        log.exception("OCR hatası")
                        lines = []
                    ocr_ms = (time.perf_counter() - t0) * 1000
                    last_ocr_at = now
                    text = clean_ocr_lines(lines)
                    last_text = text if looks_like_text(text, settings.min_text_len) else ""
                    self._on_metrics({"ocr_ms": ocr_ms, "ocr_text": last_text})

                event = tracker.update(last_text, time.perf_counter())
                if event is not None:
                    self._on_event(event)

            elapsed = time.perf_counter() - tick
            self._stop.wait(max(0.0, period - elapsed))
