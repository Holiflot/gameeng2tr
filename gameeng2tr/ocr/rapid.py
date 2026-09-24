"""RapidOCR (PaddleOCR modelleri, ONNX Runtime). Kurulumu en kolay, her yerde çalışan yedek motor."""

from __future__ import annotations

import numpy as np

from .base import OcrEngine, OcrUnavailable, group_lines


class RapidOcrEngine(OcrEngine):
    name = "rapidocr"
    label = "RapidOCR"

    def __init__(self, min_score: float = 0.5):
        try:
            from rapidocr_onnxruntime import RapidOCR
        except ImportError as exc:
            raise OcrUnavailable("rapidocr_onnxruntime paketi kurulu değil") from exc
        self._engine = RapidOCR()
        self._min_score = min_score

    def recognize(self, img_bgr: np.ndarray) -> list[str]:
        result, _ = self._engine(img_bgr, use_cls=False)
        if not result:
            return []
        boxes = []
        for points, text, score in result:
            if float(score) < self._min_score or not text.strip():
                continue
            ys = [p[1] for p in points]
            xs = [p[0] for p in points]
            boxes.append((min(ys), max(ys), min(xs), text.strip()))
        return group_lines(boxes)
