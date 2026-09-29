"""OCR motoru seçimi."""

from __future__ import annotations

import logging

from .base import OcrEngine, OcrLine, OcrUnavailable

log = logging.getLogger(__name__)

LABELS = {
    "auto": "Otomatik",
    "oneocr": "OneOCR (en hızlı)",
    "windows": "Windows OCR",
    "rapidocr": "RapidOCR (yedek)",
}

AUTO_ORDER = ("oneocr", "windows", "rapidocr")


def _create_one(name: str) -> OcrEngine:
    if name == "oneocr":
        from .oneocr_engine import OneOcrEngine

        return OneOcrEngine()
    if name == "windows":
        from .windows_ocr import WindowsOcrEngine

        return WindowsOcrEngine()
    if name == "rapidocr":
        from .rapid import RapidOcrEngine

        return RapidOcrEngine()
    raise OcrUnavailable(f"Bilinmeyen OCR motoru: {name}")


def create_ocr(name: str = "auto") -> tuple[OcrEngine, list[str]]:
    """İstenen motoru oluşturur. "auto" ise sırayla dener.

    Dönüş: (motor, denenip başarısız olanların açıklamaları)
    """
    order = AUTO_ORDER if name == "auto" else (name,)
    errors: list[str] = []
    for candidate in order:
        try:
            engine = _create_one(candidate)
            log.info("OCR motoru: %s", engine.label)
            return engine, errors
        except OcrUnavailable as exc:
            log.info("OCR motoru %s kullanılamıyor: %s", candidate, exc)
            errors.append(f"{LABELS.get(candidate, candidate)}: {exc}")
    raise OcrUnavailable("Hiçbir OCR motoru başlatılamadı:\n" + "\n".join(errors))


__all__ = ["OcrEngine", "OcrLine", "OcrUnavailable", "create_ocr", "LABELS"]
