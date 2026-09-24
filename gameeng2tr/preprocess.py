"""OCR öncesi görüntü işlemleri ve kare değişim algılama."""

from __future__ import annotations

import numpy as np

try:
    import cv2
except ImportError:  # pragma: no cover - opencv RapidOCR ile birlikte gelir
    cv2 = None


def to_gray(img: np.ndarray) -> np.ndarray:
    if img.ndim == 2:
        return img
    if cv2 is not None:
        return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return (img[..., :3] @ np.array([0.114, 0.587, 0.299])).astype(np.uint8)


def text_signature(img: np.ndarray, size: tuple[int, int] = (160, 24)) -> np.ndarray:
    """Açık renkli (altyazı) piksellerin küçültülmüş maskesi.

    Arka plandaki 3B sahne sürekli değişse de beyaz altyazı pikselleri değişmedikçe
    imza neredeyse aynı kalır; böylece gereksiz OCR çağrıları atlanır.
    """
    gray = to_gray(img)
    mask = (gray > 185).astype(np.float32)
    if cv2 is not None:
        small = cv2.resize(mask, size, interpolation=cv2.INTER_AREA)
    else:
        h, w = mask.shape
        ys = np.linspace(0, h - 1, size[1]).astype(int)
        xs = np.linspace(0, w - 1, size[0]).astype(int)
        small = mask[np.ix_(ys, xs)]
    return small


def signature_changed(prev: np.ndarray | None, cur: np.ndarray, cell_delta: float = 0.08, min_cells: int = 2) -> bool:
    """En az `min_cells` hücrede belirgin değişim varsa True. Kısa kelimeler bile yakalanır."""
    if prev is None or prev.shape != cur.shape:
        return True
    return int(np.count_nonzero(np.abs(prev - cur) > cell_delta)) >= min_cells


def high_contrast(img: np.ndarray, threshold: int = 190) -> np.ndarray:
    """Beyaz altyazıyı ayırır: beyaz zemin üzerine siyah yazı (BGR) döndürür."""
    gray = to_gray(img)
    mask = gray > threshold
    out = np.full(gray.shape, 255, dtype=np.uint8)
    out[mask] = 0
    if cv2 is not None:
        out = cv2.erode(out, np.ones((2, 2), np.uint8))
        return cv2.cvtColor(out, cv2.COLOR_GRAY2BGR)
    return np.repeat(out[..., None], 3, axis=2)


def ensure_min_size(img: np.ndarray, min_h: int = 60, min_w: int = 60) -> np.ndarray:
    """Çok küçük bölgeleri büyütür (OneOCR 50 pikselden küçük görüntüleri reddeder)."""
    h, w = img.shape[:2]
    scale = max(min_h / h, min_w / w, 1.0)
    if scale <= 1.0:
        return img
    if cv2 is not None:
        return cv2.resize(img, (int(w * scale + 0.5), int(h * scale + 0.5)), interpolation=cv2.INTER_CUBIC)
    factor = int(np.ceil(scale))
    return np.repeat(np.repeat(img, factor, axis=0), factor, axis=1)
