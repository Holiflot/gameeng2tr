"""OCR çıktısını temizleme ve altyazı değişimlerini takip etme."""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

_OCR_FIXES = (
    ("|", "I"),
    ("’", "'"),
    ("‘", "'"),
    ("“", '"'),
    ("”", '"'),
    ("…", "..."),
    ("`", "'"),
)

_SPEAKER_RE = re.compile(r"^([A-Z][\w'\-. ]{0,28}?)\s*:\s+(\S.*)$")
_SENTENCE_RE = re.compile(r"(?:(?<=[.!?])|(?<=[.!?][\"')\]]))\s+(?=[\"'(\[]?[A-Z0-9])")
_EDGE_JUNK_RE = re.compile(r"^[^\w\"'(\[¿¡.]+|[^\w\"')\].!?]+$")
_I_FIX_RE = re.compile(r"(?<![\w'])l(?=( |'m |'ll |'ve |'d ))")


def clean_ocr_lines(lines: list[str]) -> str:
    """OCR satırlarını tek bir altyazı metnine çevirir, sık görülen OCR hatalarını düzeltir."""
    text = " ".join(line.strip() for line in lines if line and line.strip())
    for old, new in _OCR_FIXES:
        text = text.replace(old, new)
    # Satır sonunda tireyle bölünmüş kelimeler: "remem- ber" -> "remember"
    text = re.sub(r"(\w)- (\w)", r"\1\2", text)
    text = _I_FIX_RE.sub("I", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = _EDGE_JUNK_RE.sub("", text).strip()
    return text


def looks_like_text(text: str, min_len: int = 3) -> bool:
    """Arka plandaki gürültüden okunan anlamsız karakter dizilerini eler."""
    if len(text) < min_len:
        return False
    letters = sum(ch.isalpha() for ch in text)
    if letters < 2:
        return False
    visible = sum(not ch.isspace() for ch in text)
    return letters / max(visible, 1) >= 0.55


def split_speaker(text: str) -> tuple[str, str]:
    """"Tiel: Merhaba" -> ("Tiel", "Merhaba"). Konuşmacı yoksa ("", text)."""
    match = _SPEAKER_RE.match(text)
    if not match:
        return "", text
    name, rest = match.group(1).strip(), match.group(2).strip()
    if len(name.split()) > 3:
        return "", text
    return name, rest


def split_sentences(text: str) -> list[str]:
    parts = [p.strip() for p in _SENTENCE_RE.split(text)]
    return [p for p in parts if p]


def normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def similarity(a: str, b: str) -> float:
    na, nb = normalize(a), normalize(b)
    if not na and not nb:
        return 1.0
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    return SequenceMatcher(None, na, nb, autojunk=False).ratio()


@dataclass
class SubtitleEvent:
    kind: str  # "show" veya "clear"
    text: str = ""


class SubtitleTracker:
    """Ardışık OCR sonuçlarından ne zaman yeni bir altyazı gösterileceğine karar verir.

    - Metin `stable_frames` kare boyunca (bulanık olarak) aynı kalmadan gösterilmez;
      böylece harf harf yazılan (daktilo efekti) altyazılar yarım çevrilmez.
    - Aynı altyazının OCR titreşimleri tekrar çeviri tetiklemez.
    - Metin uzarsa (altyazı devam ederse) yeniden çevrilir.
    - Bölge `clear_after` saniye boş kalırsa çeviri ekrandan kaldırılır.
    """

    def __init__(self, stable_frames: int = 2, clear_after: float = 0.7, same_ratio: float = 0.88):
        self.stable_frames = max(1, stable_frames)
        self.clear_after = clear_after
        self.same_ratio = same_ratio
        self.reset()

    def reset(self) -> None:
        self._candidate = ""
        self._count = 0
        self._shown = ""
        self._empty_since: float | None = None

    @property
    def shown(self) -> str:
        return self._shown

    def update(self, text: str, now: float) -> SubtitleEvent | None:
        if not text:
            self._candidate, self._count = "", 0
            if not self._shown:
                return None
            if self._empty_since is None:
                self._empty_since = now
            if now - self._empty_since >= self.clear_after:
                self._shown = ""
                self._empty_since = None
                return SubtitleEvent("clear")
            return None

        self._empty_since = None
        growing = len(normalize(text)) > len(normalize(self._candidate))
        if self._candidate and not growing and similarity(text, self._candidate) >= self.same_ratio:
            self._count += 1
        else:
            self._count = 1
        self._candidate = text

        if self._count < self.stable_frames:
            return None
        if self._should_show(text):
            self._shown = text
            return SubtitleEvent("show", text)
        return None

    def _should_show(self, text: str) -> bool:
        if not self._shown:
            return True
        if normalize(text) == normalize(self._shown):
            return False
        if similarity(text, self._shown) < self.same_ratio:
            return True
        # Aynı altyazı uzadıysa (ör. ikinci satır belirdi) yeniden çevir.
        return len(normalize(text)) > len(normalize(self._shown)) + 3
