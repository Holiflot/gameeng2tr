"""Çeviri iş parçacığı: motor yükleme/değiştirme, önbellek ve en güncel işi çevirme."""

from __future__ import annotations

import logging
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Callable

from ..textproc import split_speaker
from .base import Translator, TranslatorError
from .glossary import Glossary

log = logging.getLogger(__name__)

STATE_IDLE = "idle"
STATE_LOADING = "loading"
STATE_READY = "ready"
STATE_ERROR = "error"


@dataclass
class TranslationResult:
    seq: int
    source: str
    text: str
    engine: str
    ms: float
    cached: bool
    tag: str = "live"


class LruCache:
    def __init__(self, capacity: int = 4000):
        self.capacity = capacity
        self._data: OrderedDict[tuple[str, str], str] = OrderedDict()

    def get(self, key):
        value = self._data.get(key)
        if value is not None:
            self._data.move_to_end(key)
        return value

    def put(self, key, value) -> None:
        self._data[key] = value
        self._data.move_to_end(key)
        while len(self._data) > self.capacity:
            self._data.popitem(last=False)

    def clear(self) -> None:
        self._data.clear()


class TranslationService:
    def __init__(
        self,
        factories: dict[str, Callable[[], Translator]],
        engine: str,
        on_result: Callable[[TranslationResult], None],
        on_state: Callable[[str, str, str], None] = lambda *a: None,
        on_error: Callable[[str], None] = lambda msg: None,
        glossary: Glossary | None = None,
        split_speaker_names: bool = True,
        keep_loaded: Callable[[str], bool] = lambda name: name == "opus",
    ):
        self._factories = dict(factories)
        self._instances: dict[str, Translator] = {}
        self._states: dict[str, str] = {name: STATE_IDLE for name in factories}
        self._on_result = on_result
        self._on_state = on_state
        self._on_error = on_error
        self.glossary = glossary or Glossary()
        self.split_speaker_names = split_speaker_names
        self._keep_loaded = keep_loaded
        self.cache = LruCache()

        self._cond = threading.Condition()
        self._desired = engine
        self._active: str | None = None
        self._failed: str | None = None
        self._pending: tuple[int, str, str] | None = None
        self._last_live: tuple[int, str] | None = None
        self._cancel_seq = -1
        self._reload: set[str] = set()
        self._running = False
        self._thread: threading.Thread | None = None

    # --- dış arayüz (herhangi bir iş parçacığından çağrılabilir) -------------
    @property
    def engine(self) -> str:
        return self._desired

    def state(self, name: str) -> str:
        return self._states.get(name, STATE_IDLE)

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, name="translation", daemon=True)
        self._thread.start()
        with self._cond:
            self._cond.notify_all()

    def stop(self) -> None:
        with self._cond:
            self._running = False
            self._cond.notify_all()
        if self._thread:
            self._thread.join(timeout=10)
        for instance in self._instances.values():
            try:
                if hasattr(instance, "shutdown"):
                    instance.shutdown()
                else:
                    instance.unload()
            except Exception:  # kapanışta hatalar önemsiz
                log.exception("Motor kapatılamadı")

    def set_engine(self, name: str) -> None:
        if name not in self._factories:
            raise ValueError(name)
        with self._cond:
            self._desired = name
            self._failed = None  # yeniden seçim = yeniden dene
            # Motor değişince ekrandaki altyazıyı yeni motorla tekrar çevir.
            if self._last_live and self._pending is None:
                seq, text = self._last_live
                self._pending = (seq, text, "live")
            self._cond.notify_all()

    def reconfigure(self, name: str) -> None:
        """Ayarı değişen motoru bir sonraki kullanımda yeniden oluşturur."""
        with self._cond:
            self._reload.add(name)
            if self._failed == name:
                self._failed = None
            self._cond.notify_all()

    def submit(self, seq: int, text: str, tag: str = "live") -> None:
        with self._cond:
            self._pending = (seq, text, tag)
            if tag == "live":
                self._last_live = (seq, text)
            else:
                self._failed = None  # elle deneme = motoru yeniden dene
            self._cond.notify_all()

    def cancel_live(self, seq: int) -> None:
        """`seq` ve öncesindeki canlı işleri iptal eder (altyazı ekrandan kalktığında)."""
        with self._cond:
            self._cancel_seq = max(self._cancel_seq, seq)
            self._last_live = None
            if self._pending and self._pending[2] == "live" and self._pending[0] <= seq:
                self._pending = None

    # --- iş parçacığı --------------------------------------------------------
    def _set_state(self, name: str, state: str, message: str = "") -> None:
        self._states[name] = state
        try:
            self._on_state(name, state, message)
        except Exception:
            log.exception("on_state hatası")

    def _instance(self, name: str) -> Translator:
        if name in self._reload:
            self._reload.discard(name)
            old = self._instances.pop(name, None)
            if old is not None:
                old.unload()
            self._set_state(name, STATE_IDLE)
        if name not in self._instances:
            self._instances[name] = self._factories[name]()
        return self._instances[name]

    def _activate(self, name: str) -> bool:
        if self._active == name and name not in self._reload and self._states.get(name) == STATE_READY:
            return True
        previous = self._active
        if previous and previous != name and not self._keep_loaded(previous):
            instance = self._instances.get(previous)
            if instance is not None:
                instance.unload()
                self._set_state(previous, STATE_IDLE)
        self._active = name
        translator = self._instance(name)
        if translator.loaded and self._states.get(name) == STATE_READY:
            return True
        self._set_state(name, STATE_LOADING)
        try:
            translator.load()
        except Exception as exc:
            if isinstance(exc, TranslatorError):
                log.error("%s yüklenemedi: %s", name, exc)
            else:
                log.exception("%s yüklenemedi", name)
            self._set_state(name, STATE_ERROR, str(exc))
            self._on_error(str(exc))
            return False
        self._set_state(name, STATE_READY, getattr(translator, "note", ""))
        return True

    def _needs_work(self) -> bool:
        if self._desired in self._reload:
            return True
        if self._desired == self._failed:
            # Yüklenemeyen motor: kullanıcı motoru yeniden seçene kadar işleri at.
            self._pending = None
            return False
        return (
            self._pending is not None
            or self._desired != self._active
            or self._states.get(self._desired) != STATE_READY
        )

    def _run(self) -> None:
        while True:
            with self._cond:
                while self._running and not self._needs_work():
                    self._cond.wait()
                if not self._running:
                    return
                engine = self._desired
                job = self._pending
                self._pending = None

            if not self._activate(engine):
                with self._cond:
                    self._failed = engine
                continue
            with self._cond:
                self._failed = None
            if job is None:
                continue
            seq, text, tag = job
            with self._cond:
                if tag == "live" and seq <= self._cancel_seq:
                    continue
            self._translate_job(engine, seq, text, tag)

    def translate_text(self, engine: str, text: str) -> tuple[str, bool]:
        speaker, body = split_speaker(text) if self.split_speaker_names else ("", text)
        body = self.glossary.fix_source(body)
        key = (engine, body)
        cached = self.cache.get(key)
        if cached is None:
            translated = self._instance(engine).translate(body)
            translated = self.glossary.fix_target(translated)
            self.cache.put(key, translated)
            hit = False
        else:
            translated, hit = cached, True
        return (f"{speaker}: {translated}" if speaker else translated), hit

    def _translate_job(self, engine: str, seq: int, text: str, tag: str) -> None:
        start = time.perf_counter()
        try:
            translated, hit = self.translate_text(engine, text)
        except TranslatorError as exc:
            self._set_state(engine, STATE_ERROR, str(exc))
            self._on_error(str(exc))
            return
        except Exception as exc:
            log.exception("Çeviri hatası")
            self._on_error(f"Çeviri hatası: {exc}")
            return
        ms = (time.perf_counter() - start) * 1000
        with self._cond:
            if tag == "live" and seq <= self._cancel_seq:
                return
            if self._desired != engine:
                return  # bu arada motor değişti; yeni motorla tekrar çevrilecek
        self._on_result(TranslationResult(seq, text, translated, engine, ms, hit, tag))
