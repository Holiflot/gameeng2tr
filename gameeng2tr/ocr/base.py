from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np


class OcrUnavailable(RuntimeError):
    """OCR motoru bu sistemde kullanılamıyor (eksik paket/DLL/dil paketi)."""


class OcrEngine(ABC):
    name = "ocr"
    label = "OCR"

    @abstractmethod
    def recognize(self, img_bgr: np.ndarray) -> list[str]:
        """BGR görüntüdeki metin satırlarını yukarıdan aşağıya sırayla döndürür."""

    def close(self) -> None:
        pass


def group_lines(boxes: list[tuple[float, float, float, str]]) -> list[str]:
    """(üst, alt, sol, metin) kutularını satırlara gruplayıp soldan sağa birleştirir."""
    lines: list[list[tuple[float, float, float, str]]] = []
    for box in sorted(boxes, key=lambda b: (b[0] + b[1]) / 2):
        center = (box[0] + box[1]) / 2
        if lines:
            last = lines[-1]
            top = min(b[0] for b in last)
            bottom = max(b[1] for b in last)
            if top <= center <= bottom:
                last.append(box)
                continue
        lines.append([box])
    return [" ".join(b[3] for b in sorted(line, key=lambda b: b[2])) for line in lines]
