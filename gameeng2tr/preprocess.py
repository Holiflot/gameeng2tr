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


def ink_height(frame: np.ndarray, box, threshold: int = 170) -> float | None:
    """Kutu içindeki açık renkli yazının piksel olarak dikey uzunluğu (üst uzantı + alt uzantı).

    OCR motorlarının kutuları farklı boşluklar içerdiğinden yazı boyutu doğrudan görüntüden ölçülür.
    """
    h, w = frame.shape[:2]
    x0, y0, x1, y1 = (int(round(v)) for v in box)
    x0, y0, x1, y1 = max(0, x0), max(0, y0), min(w, x1), min(h, y1)
    if x1 - x0 < 4 or y1 - y0 < 4:
        return None
    gray = to_gray(frame[y0:y1, x0:x1])
    rows = np.count_nonzero(gray > threshold, axis=1)
    active = np.nonzero(rows >= max(2, (x1 - x0) * 0.004))[0]
    if len(active) < 3:
        return None
    return float(active[-1] - active[0] + 1)


def erase_text_patch(
    frame: np.ndarray,
    box: tuple[float, float, float, float],
    line_height: float,
    blur: float = 10.0,
    text_threshold: int = 170,
) -> tuple[np.ndarray, int, int]:
    """Altyazıyı arka plandan silip bulanıklaştırılmış bir yama üretir.

    1. Altyazı pikselleri (açık renkli yazı + dış çizgi/gölge payı) maskelenir.
    2. Maskeli bölge, çevresindeki oyun görüntüsünden normalize bulanıklaştırmayla doldurulur
       (yazının "arkası" tahmin edilir), sonra buzlu cam görünümü için hafifçe bulanıklaştırılır.
    3. Kenarları yumuşak bir alfa maskesiyle oyun görüntüsüne karışır.

    Dönüş: (BGRA yama, sol x, üst y) bölge koordinatlarında.
    """
    if cv2 is None:
        raise RuntimeError("opencv gerekli")
    h, w = frame.shape[:2]
    lh = max(8.0, float(line_height))
    pad = int(lh * 0.45) + 4
    feather = max(6, int(lh * 0.35))
    margin = pad + feather + int(blur * 2)
    x0, y0, x1, y1 = box
    ox0, oy0 = max(0, int(x0) - margin), max(0, int(y0) - margin)
    ox1, oy1 = min(w, int(x1 + 0.999) + margin), min(h, int(y1 + 0.999) + margin)
    roi = frame[oy0:oy1, ox0:ox1, :3]
    rh, rw = roi.shape[:2]

    # Hız için yarım çözünürlükte çalış.
    scale = 0.5 if min(rh, rw) >= 40 else 1.0
    small = cv2.resize(roi, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) if scale != 1.0 else roi
    small_f = small.astype(np.float32)

    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    text_mask = (gray > text_threshold).astype(np.uint8)
    # Sadece altyazı kutusu çevresindeki parlak pikseller yazıdır.
    limit = np.zeros_like(text_mask)
    bx0, by0 = int((x0 - ox0 - pad) * scale), int((y0 - oy0 - pad) * scale)
    bx1, by1 = int((x1 - ox0 + pad) * scale) + 1, int((y1 - oy0 + pad) * scale) + 1
    limit[max(0, by0):by1, max(0, bx0):bx1] = 1
    text_mask &= limit
    # Dış çizgi ve gölge de silinsin diye maske genişletilir.
    grow = max(1, int(round(lh * 0.22 * scale)))
    text_mask = cv2.dilate(text_mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * grow + 1, 2 * grow + 1)))

    # Normalize bulanıklaştırma: yazı piksellerini hesaba katmadan çevreden doldur.
    keep = (1 - text_mask).astype(np.float32)
    fill_sigma = max(2.0, lh * 0.5 * scale)
    num = cv2.GaussianBlur(small_f * keep[..., None], (0, 0), fill_sigma)
    den = cv2.GaussianBlur(keep, (0, 0), fill_sigma)[..., None]
    blurred_all = cv2.GaussianBlur(small_f, (0, 0), fill_sigma)
    filled = np.where(den > 0.05, num / np.maximum(den, 1e-6), blurred_all)
    clean = np.where(text_mask[..., None] > 0, filled, small_f)
    if blur > 0:
        clean = cv2.GaussianBlur(clean, (0, 0), max(0.5, blur * scale))

    alpha = np.zeros((small.shape[0], small.shape[1]), np.float32)
    alpha[max(0, by0):by1, max(0, bx0):bx1] = 1.0
    alpha = cv2.GaussianBlur(alpha, (0, 0), max(1.0, feather * scale / 2))

    patch = np.empty((small.shape[0], small.shape[1], 4), np.uint8)
    patch[..., :3] = np.clip(clean, 0, 255).astype(np.uint8)
    patch[..., 3] = np.clip(alpha * 255, 0, 255).astype(np.uint8)
    if scale != 1.0:
        patch = cv2.resize(patch, (rw, rh), interpolation=cv2.INTER_LINEAR)
    return np.ascontiguousarray(patch), ox0, oy0
