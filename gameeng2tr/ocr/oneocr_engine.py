"""OneOCR: Windows 11 Ekran Alıntısı Aracı'nın OCR motoru. En hızlı ve en isabetli seçenek.

Gerekli dosyalar (oneocr.dll, oneocr.onemodel, onnxruntime.dll) Ekran Alıntısı Aracı
klasöründen %USERPROFILE%\\.config\\oneocr\\ içine kopyalanmalıdır. Ayrıntılar README'de.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

from .base import OcrEngine, OcrUnavailable
from ..preprocess import ensure_min_size

ONEOCR_DIR = Path.home() / ".config" / "oneocr"
REQUIRED_FILES = ("oneocr.dll", "oneocr.onemodel", "onnxruntime.dll")


def missing_files() -> list[str]:
    return [name for name in REQUIRED_FILES if not (ONEOCR_DIR / name).exists()]


class OneOcrEngine(OcrEngine):
    name = "oneocr"
    label = "OneOCR"

    def __init__(self):
        if sys.platform != "win32":
            raise OcrUnavailable("OneOCR sadece Windows'ta çalışır")
        missing = missing_files()
        if missing:
            raise OcrUnavailable(f"OneOCR dosyaları eksik ({', '.join(missing)}) -> {ONEOCR_DIR}")
        try:
            import oneocr
        except ImportError as exc:
            raise OcrUnavailable("oneocr paketi kurulu değil") from exc
        try:
            self._engine = oneocr.OcrEngine()
        except Exception as exc:  # DLL yükleme hataları
            raise OcrUnavailable(f"OneOCR başlatılamadı: {exc}") from exc

    def recognize(self, img_bgr: np.ndarray) -> list[str]:
        img = np.ascontiguousarray(ensure_min_size(img_bgr))
        result = self._engine.recognize_cv2(img)
        if result.get("error"):
            return []
        return [line["text"] for line in result.get("lines", []) if line.get("text")]
