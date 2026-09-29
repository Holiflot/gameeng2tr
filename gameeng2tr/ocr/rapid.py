"""RapidOCR (PaddleOCR modelleri, ONNX Runtime). Kurulumu en kolay, her yerde çalışan yedek motor."""

from __future__ import annotations

import numpy as np

from .base import OcrEngine, OcrLine, OcrUnavailable, group_lines, points_box


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

    def recognize(self, img_bgr: np.ndarray) -> list[OcrLine]:
        result, _ = self._engine(img_bgr, use_cls=False)
        if not result:
            return []
        words = [
            (text.strip(), points_box(points))
            for points, text, score in result
            if float(score) >= self._min_score and text.strip()
        ]
        return group_lines(words)
