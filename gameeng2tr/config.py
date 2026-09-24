"""Kalıcı kullanıcı ayarları (JSON)."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from . import paths

log = logging.getLogger(__name__)

ENGINE_OPUS = "opus"
ENGINE_GEMMA = "gemma"
ENGINES = (ENGINE_OPUS, ENGINE_GEMMA)

OCR_BACKENDS = ("auto", "oneocr", "windows", "rapidocr")

OVERLAY_POSITIONS = ("over", "above", "below")


@dataclass
class Settings:
    # Altyazı bölgesi: monitörün (sol, üst, sağ, alt) oranları, 0..1
    region: list[float] = field(default_factory=lambda: [0.12, 0.80, 0.88, 0.97])
    monitor: int = 0

    engine: str = ENGINE_OPUS

    # Opus-MT (CTranslate2)
    opus_device: str = "cpu"  # "cpu" veya "cuda"
    opus_threads: int = 4
    opus_beam_size: int = 2
    opus_target_prefix: str = ""

    # TranslateGemma (Ollama)
    ollama_url: str = "http://127.0.0.1:11434"
    gemma_model: str = "translategemma:4b"
    gemma_cpu_only: bool = False
    gemma_keep_loaded: bool = False  # Opus'a geçince VRAM'de tut
    gemma_timeout: float = 30.0
    gemma_threads: int = 4  # sadece CPU modunda; oyuna çekirdek bırakmak için

    # OCR ve yakalama
    ocr_backend: str = "auto"
    capture_fps: float = 8.0
    stable_frames: int = 2
    clear_after: float = 0.7
    high_contrast: bool = False
    min_text_len: int = 3
    split_speaker: bool = True

    # Overlay
    overlay_position: str = "over"
    font_family: str = "Segoe UI"
    font_size: int = 28
    font_bold: bool = True
    text_color: str = "#FFFFFF"
    outline_color: str = "#000000"
    background_opacity: float = 0.90
    show_engine_badge: bool = False

    # Kısayollar (Ctrl+Alt+harf kullanılmaz: Türkçe Q klavyede AltGr ile aynıdır, € ve ₺ gibi karakterleri engeller)
    hotkey_toggle: str = "ctrl+alt+f9"
    hotkey_engine: str = "ctrl+alt+f10"
    hotkey_overlay: str = "ctrl+alt+f11"
    hotkey_region: str = "ctrl+alt+f12"

    autostart: bool = False

    @classmethod
    def load(cls, path: Path | None = None) -> "Settings":
        path = path or paths.settings_path()
        settings = cls()
        if not path.exists():
            return settings
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            log.warning("Ayarlar okunamadı (%s), varsayılanlar kullanılıyor", exc)
            return settings
        known = {f.name: f for f in fields(cls)}
        for key, value in data.items():
            if key not in known:
                continue
            default = getattr(settings, key)
            if isinstance(default, bool):
                value = bool(value)
            elif isinstance(default, int) and not isinstance(value, bool):
                try:
                    value = int(value)
                except (TypeError, ValueError):
                    continue
            elif isinstance(default, float):
                try:
                    value = float(value)
                except (TypeError, ValueError):
                    continue
            setattr(settings, key, value)
        settings.validate()
        return settings

    def validate(self) -> None:
        if self.engine not in ENGINES:
            self.engine = ENGINE_OPUS
        if self.ocr_backend not in OCR_BACKENDS:
            self.ocr_backend = "auto"
        if self.overlay_position not in OVERLAY_POSITIONS:
            self.overlay_position = "over"
        self.region = normalize_region(self.region)
        self.capture_fps = min(max(self.capture_fps, 1.0), 30.0)
        self.stable_frames = max(1, self.stable_frames)
        self.background_opacity = min(max(self.background_opacity, 0.0), 1.0)
        self.font_size = min(max(self.font_size, 10), 96)

    def save(self, path: Path | None = None) -> None:
        path = path or paths.settings_path()
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)


def normalize_region(region) -> list[float]:
    default = [0.12, 0.80, 0.88, 0.97]
    try:
        left, top, right, bottom = (float(v) for v in region)
    except (TypeError, ValueError):
        return default
    left, right = sorted((min(max(left, 0.0), 1.0), min(max(right, 0.0), 1.0)))
    top, bottom = sorted((min(max(top, 0.0), 1.0), min(max(bottom, 0.0), 1.0)))
    if right - left < 0.01 or bottom - top < 0.01:
        return default
    return [left, top, right, bottom]
