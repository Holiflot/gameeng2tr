"""Windows 10/11 dahili OCR motoru (Windows.Media.Ocr)."""

from __future__ import annotations

import asyncio
import sys

import numpy as np

from .base import OcrEngine, OcrLine, OcrUnavailable, union_box

INSTALL_HINT = (
    "Windows'ta İngilizce OCR dil paketi yüklü değil. Yönetici PowerShell'de şunu çalıştırın:\n"
    'Add-WindowsCapability -Online -Name "Language.OCR~~~en-US~0.0.1.0"'
)


async def _await(op):
    return await op


class WindowsOcrEngine(OcrEngine):
    name = "windows"
    label = "Windows OCR"

    def __init__(self, language: str = "en-US"):
        if sys.platform != "win32":
            raise OcrUnavailable("Windows OCR sadece Windows'ta çalışır")
        try:
            from winrt.windows.globalization import Language
            from winrt.windows.graphics.imaging import BitmapPixelFormat, SoftwareBitmap
            from winrt.windows.media.ocr import OcrEngine as WinOcrEngine
            from winrt.windows.storage.streams import DataWriter
        except ImportError as exc:
            raise OcrUnavailable("winrt-Windows.Media.Ocr paketleri kurulu değil") from exc

        lang = Language(language)
        if not WinOcrEngine.is_language_supported(lang):
            raise OcrUnavailable(INSTALL_HINT)
        self._engine = WinOcrEngine.try_create_from_language(lang)
        if self._engine is None:
            raise OcrUnavailable(INSTALL_HINT)
        self._SoftwareBitmap = SoftwareBitmap
        self._RGBA8 = BitmapPixelFormat.RGBA8
        self._DataWriter = DataWriter
        self._loop = asyncio.new_event_loop()

    def recognize(self, img_bgr: np.ndarray) -> list[OcrLine]:
        h, w = img_bgr.shape[:2]
        rgba = np.empty((h, w, 4), dtype=np.uint8)
        rgba[..., 0] = img_bgr[..., 2]
        rgba[..., 1] = img_bgr[..., 1]
        rgba[..., 2] = img_bgr[..., 0]
        rgba[..., 3] = 255
        writer = self._DataWriter()
        writer.write_bytes(rgba.tobytes())
        bitmap = self._SoftwareBitmap.create_copy_from_buffer(writer.detach_buffer(), self._RGBA8, w, h)
        result = self._loop.run_until_complete(_await(self._engine.recognize_async(bitmap)))
        lines = []
        for line in result.lines:
            if not line.text.strip():
                continue
            rects = [w.bounding_rect for w in line.words]
            box = union_box((r.x, r.y, r.x + r.width, r.y + r.height) for r in rects)
            lines.append(OcrLine(line.text, box))
        return lines

    def close(self) -> None:
        self._loop.close()
