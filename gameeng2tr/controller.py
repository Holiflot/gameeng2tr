"""Bileşenleri birbirine bağlayan uygulama denetleyicisi (Qt ana iş parçacığında yaşar)."""

from __future__ import annotations

import logging
import threading

from PySide6.QtCore import QObject, QTimer, Signal

from .capture import ScreenCapture
from .config import ENGINE_GEMMA, ENGINE_OPUS, Settings
from .hotkeys import HotkeyManager
from .pipeline import CapturePipeline
from .textproc import SubtitleEvent
from .translate import LABELS as ENGINE_LABELS
from .translate import make_factories
from .translate.glossary import Glossary
from .translate.service import STATE_ERROR, STATE_LOADING, STATE_READY, TranslationResult, TranslationService
from .ui.overlay import SubtitleOverlay, Toast

log = logging.getLogger(__name__)

STATE_TEXT = {
    "idle": "bekliyor",
    STATE_LOADING: "yükleniyor...",
    STATE_READY: "hazır",
    STATE_ERROR: "hata",
}


class Controller(QObject):
    # Arka plan iş parçacıklarından ana iş parçacığına köprü sinyalleri
    subtitle_event = Signal(object)
    translation_result = Signal(object)
    engine_state = Signal(str, str, str)
    error = Signal(str)
    status = Signal(str)
    metrics = Signal(dict)
    ocr_ready = Signal(str)
    hotkey = Signal(str)
    running_changed = Signal(bool)
    region_changed = Signal()
    engine_changed = Signal(str)
    overlay_hidden_changed = Signal(bool)
    pipeline_stopped = Signal()
    background = Signal(object)

    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings
        self.overlay = SubtitleOverlay(settings)
        self.toast = Toast(settings)
        self._capture: ScreenCapture | None = None
        self._capture_lock = threading.Lock()
        self._seq = 0
        self._shown_seq = 0
        self.last_translation_ms = 0.0
        self._selector = None

        self.service = TranslationService(
            make_factories(settings),
            settings.engine,
            on_result=self.translation_result.emit,
            on_state=self.engine_state.emit,
            on_error=self.error.emit,
            glossary=Glossary.load(),
            split_speaker_names=settings.split_speaker,
            keep_loaded=lambda name: name == ENGINE_OPUS or self.settings.gemma_keep_loaded,
        )
        self.pipeline = CapturePipeline(
            settings,
            self._get_capture,
            on_event=self.subtitle_event.emit,
            on_status=self.status.emit,
            on_metrics=self.metrics.emit,
            on_ocr_ready=self.ocr_ready.emit,
            on_stopped=self.pipeline_stopped.emit,
            on_background=self.background.emit,
        )
        self.hotkeys = HotkeyManager(on_error=self.error.emit)

        self.subtitle_event.connect(self._on_subtitle_event)
        self.translation_result.connect(self._on_translation)
        self.engine_state.connect(self._on_engine_state)
        self.hotkey.connect(self._on_hotkey)
        self.pipeline_stopped.connect(self._on_pipeline_stopped)
        self.background.connect(self.overlay.set_background)

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._save_now)

    # --- yaşam döngüsü ------------------------------------------------------
    def boot(self) -> None:
        self.service.start()
        self.bind_hotkeys()
        if self.settings.autostart:
            self.start()

    def shutdown(self) -> None:
        self._save_now()
        self.hotkeys.stop()
        self.pipeline.close()
        self.service.stop()
        if self._capture is not None:
            self._capture.close()
            self._capture = None
        self.overlay.close()
        self.toast.close()

    def bind_hotkeys(self) -> None:
        s = self.settings
        for name, combo in (
            ("toggle", s.hotkey_toggle),
            ("engine", s.hotkey_engine),
            ("overlay", s.hotkey_overlay),
            ("region", s.hotkey_region),
        ):
            self.hotkeys.bind(name, combo, lambda n=name: self.hotkey.emit(n))
        self.hotkeys.start()

    def save_later(self) -> None:
        self._save_timer.start(400)

    def _save_now(self) -> None:
        try:
            self.settings.save()
        except OSError as exc:
            log.warning("Ayarlar kaydedilemedi: %s", exc)

    # --- yakalama -----------------------------------------------------------
    def _get_capture(self) -> ScreenCapture | None:
        # Hem yakalama iş parçacığından hem de bölge seçiminde (ana iş parçacığı) çağrılır.
        with self._capture_lock:
            if self._capture is not None and self._capture.monitor != self.settings.monitor:
                self._capture.close()
                self._capture = None
            if self._capture is None:
                try:
                    self._capture = ScreenCapture(self.settings.monitor)
                except RuntimeError as exc:
                    self.error.emit(str(exc))
                    return None
            return self._capture

    @property
    def running(self) -> bool:
        return self.pipeline.running

    def start(self) -> None:
        if self.running:
            return
        self.service.set_engine(self.settings.engine)
        self.pipeline.start()
        self.running_changed.emit(True)
        self.toast.show_message(f"Çeviri başladı • {ENGINE_LABELS[self.settings.engine]}")

    def stop(self) -> None:
        if not self.running:
            return
        self.pipeline.stop()
        self.service.cancel_live(self._seq)
        self.overlay.clear()
        self.running_changed.emit(False)
        self.status.emit("Durduruldu")
        self.toast.show_message("Çeviri durduruldu")

    def _on_pipeline_stopped(self) -> None:
        self.pipeline.stop()
        self.overlay.clear()
        self.running_changed.emit(False)
        self.toast.show_message("Çeviri durdu, ayrıntılar uygulama penceresinde", 4000)

    def toggle(self) -> None:
        self.stop() if self.running else self.start()

    # --- motor --------------------------------------------------------------
    def set_engine(self, name: str) -> None:
        if name == self.settings.engine and self.service.state(name) != STATE_ERROR:
            return
        self.settings.engine = name
        self.save_later()
        self.service.set_engine(name)
        self.engine_changed.emit(name)
        self.toast.show_message(f"Motor: {ENGINE_LABELS[name]}")

    def cycle_engine(self) -> None:
        self.set_engine(ENGINE_GEMMA if self.settings.engine == ENGINE_OPUS else ENGINE_OPUS)

    def reconfigure_engine(self, name: str) -> None:
        self.save_later()
        self.service.cache.clear()
        self.service.reconfigure(name)

    def reload_glossary(self) -> None:
        self.service.glossary = Glossary.load()
        self.service.cache.clear()

    def translate_manual(self, text: str) -> None:
        self.service.submit(-1, text, tag="manual")

    # --- olaylar ------------------------------------------------------------
    def _on_subtitle_event(self, event: SubtitleEvent) -> None:
        if event.kind == "show":
            self._seq += 1
            self.overlay.set_source_layout(event.layout)
            self.service.submit(self._seq, event.text)
        elif event.kind == "clear":
            self.service.cancel_live(self._seq)
            self.overlay.clear()

    def _on_translation(self, result: TranslationResult) -> None:
        if result.tag != "live":
            return
        if result.seq < self._shown_seq:
            return
        self._shown_seq = result.seq
        self.last_translation_ms = result.ms
        badge = "Opus" if result.engine == ENGINE_OPUS else "Gemma"
        self.overlay.show_text(result.text, badge)

    def _on_engine_state(self, name: str, state: str, message: str) -> None:
        if name != self.settings.engine:
            return
        label = ENGINE_LABELS[name]
        if state == STATE_LOADING:
            self.toast.show_message(f"{label} yükleniyor...", 4000)
        elif state == STATE_READY:
            where = f" ({message})" if message else ""
            self.toast.show_message(f"{label} hazır{where}", 2500 if message else 1500)
        elif state == STATE_ERROR:
            self.toast.show_message(f"{label} başlatılamadı, ayrıntılar uygulama penceresinde", 4000)

    def _on_hotkey(self, name: str) -> None:
        if name == "toggle":
            self.toggle()
        elif name == "engine":
            self.cycle_engine()
        elif name == "overlay":
            self.set_overlay_hidden(not self.overlay.user_hidden)
        elif name == "region":
            self.select_region()

    def set_overlay_hidden(self, hidden: bool) -> None:
        self.overlay.set_user_hidden(hidden)
        self.overlay_hidden_changed.emit(hidden)
        self.toast.show_message("Çeviri gizlendi" if hidden else "Çeviri gösteriliyor", 1200)

    # --- bölge seçimi ---------------------------------------------------------
    def select_region(self) -> None:
        from .ui.region_selector import RegionSelector

        if self._selector is not None:
            return
        capture = self._get_capture()
        frame = capture.grab_full() if capture else None
        self._selector = RegionSelector(frame, self.settings.monitor, self.settings.region)
        self._selector.selected.connect(self.set_region)
        self._selector.destroyed.connect(self._on_selector_closed)
        self._selector.show()

    def _on_selector_closed(self) -> None:
        self._selector = None

    def set_region(self, region: list) -> None:
        from .config import normalize_region

        self.settings.region = normalize_region(region)
        self.save_later()
        self.pipeline.reset()
        self.overlay.refresh()
        self.region_changed.emit()
