"""OneOCR: Windows 11 Ekran Alıntısı Aracı'nın OCR motoru. En hızlı ve en isabetli seçenek.

Gerekli dosyalar (oneocr.dll, oneocr.onemodel, onnxruntime.dll) Ekran Alıntısı Aracı
klasöründen %USERPROFILE%\\.config\\oneocr\\ içine kopyalanmalıdır. Ayrıntılar README'de.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

from .base import OcrEngine, OcrLine, OcrUnavailable
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

    def recognize(self, img_bgr: np.ndarray) -> list[OcrLine]:
        img = np.ascontiguousarray(ensure_min_size(img_bgr))
        scale = img_bgr.shape[0] / img.shape[0]  # küçük görüntü büyütüldüyse kutuları geri ölçekle
        result = self._engine.recognize_cv2(img)
        if result.get("error"):
            return []
        lines = []
        for line in result.get("lines", []):
            if not line.get("text"):
                continue
            rect = line.get("bounding_rect")
            box = None
            if rect:
                xs = [rect[f"x{i}"] for i in range(1, 5)]
                ys = [rect[f"y{i}"] for i in range(1, 5)]
                box = (min(xs) * scale, min(ys) * scale, max(xs) * scale, max(ys) * scale)
            lines.append(OcrLine(line["text"], box))
        return lines
