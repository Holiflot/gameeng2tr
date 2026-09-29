from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np

Box = tuple[float, float, float, float]  # (sol, üst, sağ, alt), görüntü pikseli


class OcrUnavailable(RuntimeError):
    """OCR motoru bu sistemde kullanılamıyor (eksik paket/DLL/dil paketi)."""


@dataclass
class OcrLine:
    text: str
    box: Box | None = None


class OcrEngine(ABC):
    name = "ocr"
    label = "OCR"

    @abstractmethod
    def recognize(self, img_bgr: np.ndarray) -> list[OcrLine]:
        """BGR görüntüdeki metin satırlarını (konumlarıyla) yukarıdan aşağıya sırayla döndürür."""

    def close(self) -> None:
        pass


def union_box(boxes) -> Box | None:
    boxes = [b for b in boxes if b is not None]
    if not boxes:
        return None
    return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))


def points_box(points) -> Box:
    xs = [float(p[0]) for p in points]
    ys = [float(p[1]) for p in points]
    return (min(xs), min(ys), max(xs), max(ys))


def group_lines(words: list[tuple[str, Box]]) -> list[OcrLine]:
    """Kelime/parça kutularını satırlara gruplayıp soldan sağa birleştirir."""
    lines: list[list[tuple[str, Box]]] = []
    for word in sorted(words, key=lambda w: (w[1][1] + w[1][3]) / 2):
        center = (word[1][1] + word[1][3]) / 2
        if lines:
            last = lines[-1]
            top = min(w[1][1] for w in last)
            bottom = max(w[1][3] for w in last)
            if top <= center <= bottom:
                last.append(word)
                continue
        lines.append([word])
    result = []
    for line in lines:
        line.sort(key=lambda w: w[1][0])
        result.append(OcrLine(" ".join(w[0] for w in line), union_box(w[1] for w in line)))
    return result
