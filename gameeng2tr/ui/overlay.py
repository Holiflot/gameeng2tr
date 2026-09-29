"""Oyunun üstünde duran, tıklanamaz ve ekran yakalamaya girmeyen çeviri katmanı."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QGuiApplication,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
    QTextLayout,
    QTextOption,
)
from PySide6.QtWidgets import QWidget

import numpy as np

from .. import win32
from ..config import Settings
from ..textproc import SubtitleLayout

PADDING_X = 18
PADDING_Y = 10
GAP = 6


def layout_lines(text: str, font: QFont, width: float) -> list[tuple[str, float]]:
    """Metni verilen genişliğe göre satırlara böler: [(satır, genişlik)]."""
    option = QTextOption()
    option.setWrapMode(QTextOption.WrapMode.WordWrap)
    layout = QTextLayout(text, font)
    layout.setTextOption(option)
    layout.beginLayout()
    lines = []
    while True:
        line = layout.createLine()
        if not line.isValid():
            break
        line.setLineWidth(max(width, 10))
        segment = text[line.textStart(): line.textStart() + line.textLength()].strip()
        if segment:
            lines.append((segment, line.naturalTextWidth()))
    layout.endLayout()
    return lines


_INK_RATIOS: dict[tuple[str, bool], float] = {}


def ink_ratio(font: QFont) -> float:
    """Yazı tipinin mürekkep yüksekliği / piksel boyutu oranı (büyük harf üstü -> kuyruk altı)."""
    key = (font.family(), font.bold())
    if key not in _INK_RATIOS:
        probe = QFont(font)
        probe.setPixelSize(100)
        rect = QFontMetricsF(probe).tightBoundingRect("Hdkfgjpqy")
        _INK_RATIOS[key] = min(max(rect.height() / 100.0, 0.6), 1.3) if rect.height() > 0 else 0.95
    return _INK_RATIOS[key]


def bgra_to_qimage(image: np.ndarray) -> QImage:
    image = np.ascontiguousarray(image)
    h, w = image.shape[:2]
    # Little-endian'da bellekte B,G,R,A sırası = QImage ARGB32
    return QImage(image.data, w, h, 4 * w, QImage.Format.Format_ARGB32).copy()


class _OverlayBase(QWidget):
    def __init__(self):
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
            | Qt.WindowType.WindowDoesNotAcceptFocus
            | Qt.WindowType.NoDropShadowWindowHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        # Yerel pencereyi göstermeden oluştur ve Win32 özelliklerini hemen uygula.
        hwnd = int(self.winId())
        win32.make_overlay_window(hwnd)
        self.excluded_from_capture = win32.exclude_from_capture(hwnd)
        self._topmost_timer = QTimer(self)
        self._topmost_timer.timeout.connect(self._raise_topmost)
        self._topmost_timer.start(1000)

    def showEvent(self, event):
        super().showEvent(event)
        # Qt gösterirken stilleri değiştirmiş olabilir; tekrar uygula.
        win32.make_overlay_window(int(self.winId()))
        self._raise_topmost()

    def _raise_topmost(self):
        if self.isVisible():
            win32.keep_topmost(int(self.winId()))

    @staticmethod
    def draw_outlined_text(
        painter: QPainter,
        lines,
        font: QFont,
        rect: QRectF,
        color: QColor,
        outline: QColor,
        outline_width: float | None = None,
        shadow: float = 0.0,
    ):
        metrics = QFontMetricsF(font)
        line_h = metrics.lineSpacing()
        total_h = line_h * len(lines)
        y = rect.top() + (rect.height() - total_h) / 2 + metrics.ascent()
        path = QPainterPath()
        for text, width in lines:
            x = rect.left() + (rect.width() - width) / 2
            path.addText(QPointF(x, y), font, text)
            y += line_h
        if outline_width is None:
            outline_width = max(2.0, font.pixelSize() / 7)
        if shadow > 0:
            shade = QColor(0, 0, 0, 150)
            painter.setPen(QPen(shade, outline_width * 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            painter.setBrush(shade)
            painter.drawPath(path.translated(shadow, shadow))
        painter.setPen(QPen(outline, outline_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawPath(path)


class SubtitleOverlay(_OverlayBase):
    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings
        self._text = ""
        self._badge = ""
        self._lines: list[tuple[str, float]] = []
        self._layout: SubtitleLayout | None = None
        self._patch: tuple[QImage, int, int, tuple[int, int]] | None = None
        self._exact = False  # İngilizce altyazının tam üstüne mi yazılıyor
        self._style = settings.overlay_style
        self._block = QRectF()  # yazı bloğu (pencere koordinatı)
        self._source = QRectF()  # İngilizce altyazının kutusu (pencere koordinatı)
        self._region_origin = QPointF()  # bölgenin sol üstü (pencere koordinatı)
        self._scale = 1.0  # bölge pikseli -> mantıksal piksel
        self._font = QFont()
        self.user_hidden = False

    # --- geometri ----------------------------------------------------------
    def _screen(self):
        screens = QGuiApplication.screens()
        index = self.settings.monitor
        return screens[index] if 0 <= index < len(screens) else QGuiApplication.primaryScreen()

    def region_rect(self) -> QRect:
        geo = self._screen().geometry()
        l, t, r, b = self.settings.region
        return QRect(
            geo.x() + round(l * geo.width()),
            geo.y() + round(t * geo.height()),
            max(40, round((r - l) * geo.width())),
            max(20, round((b - t) * geo.height())),
        )

    def font(self, pixel_size: int | None = None) -> QFont:
        font = QFont(self.settings.font_family)
        font.setPixelSize(pixel_size or self.settings.font_size)
        font.setBold(self.settings.font_bold)
        return font

    def _effective_mode(self) -> tuple[str, str]:
        style, mode = self.settings.overlay_style, self.settings.overlay_position
        if not self.excluded_from_capture:
            # Pencere yakalamadan hariç tutulamıyorsa kendi yazımızı OCR'lamamak için
            # altyazının üstüne yazamayız: koyu kutuyla yukarıda göster.
            if mode == "over":
                mode = "above"
            if style == "blur":
                style = "box"
        if style == "blur":
            mode = "over"
        return style, mode

    def _relayout(self) -> None:
        style, mode = self._effective_mode()
        self._style = style
        self._exact = mode == "over" and self._layout is not None
        if self._exact:
            self._relayout_exact()
        else:
            self._relayout_band(mode)

    def _relayout_band(self, mode: str) -> None:
        """Konum bilgisi yoksa: bölge genişliğinde bir şerit (eski davranış)."""
        region = self.region_rect()
        screen_geo = self._screen().geometry()
        width = max(region.width(), 200)
        self._font = self.font()
        self._lines = layout_lines(self._text, self._font, width - 2 * PADDING_X)
        text_h = QFontMetricsF(self._font).height() * max(1, len(self._lines)) + 2 * PADDING_Y
        if mode == "over":
            height = max(region.height(), int(text_h))
            top = region.bottom() + 1 - height
        elif mode == "above":
            height = int(text_h)
            top = region.top() - GAP - height
        else:
            height = int(text_h)
            top = region.bottom() + 1 + GAP
        top = max(screen_geo.top(), min(top, screen_geo.bottom() + 1 - height))
        left = region.left() + (region.width() - width) // 2
        self.setGeometry(left, top, width, height)
        self._block = QRectF(PADDING_X, PADDING_Y, width - 2 * PADDING_X, height - 2 * PADDING_Y)
        self._region_origin = QPointF(region.left() - left, region.top() - top)

    def _relayout_exact(self) -> None:
        """Türkçeyi İngilizce altyazının konumuna, aynı yazı boyutuyla yerleştirir."""
        layout = self._layout
        region = self.region_rect()
        screen_geo = self._screen().geometry()
        frame_w, frame_h = layout.frame_size
        scale = region.width() / max(1, frame_w)
        self._scale = scale
        x0, y0, x1, y1 = layout.box
        box = QRectF(region.left() + x0 * scale, region.top() + y0 * scale, (x1 - x0) * scale, (y1 - y0) * scale)

        if self.settings.font_auto:
            size = layout.line_height * scale / ink_ratio(self.font(100)) * self.settings.font_scale
        else:
            size = self.settings.font_size
        size = int(min(max(size, 12), 96))
        max_w = region.width() * 0.98
        wrap_w = min(max_w, box.width() * 1.15) if layout.line_count >= 2 else max_w
        allowed_h = max(region.height(), box.height() * 1.6)
        min_size = max(12, int(size * 0.7))
        while True:
            font = self.font(size)
            metrics = QFontMetricsF(font)
            lines = layout_lines(self._text, font, wrap_w)
            block_h = metrics.lineSpacing() * max(1, len(lines))
            if block_h <= allowed_h or size <= min_size:
                break
            size -= 1
        self._font, self._lines = font, lines
        block_w = max((w for _, w in lines), default=0.0)
        block = QRectF(0, 0, block_w, block_h)
        block.moveCenter(box.center())

        margin = max(6.0, size * 0.25)
        area = QRectF(region).united(block.adjusted(-margin, -margin, margin, margin))
        area = area.intersected(QRectF(screen_geo))
        geo = area.toAlignedRect()
        self.setGeometry(geo)
        self._block = block.translated(-geo.left(), -geo.top())
        self._source = box.translated(-geo.left(), -geo.top())
        self._region_origin = QPointF(region.left() - geo.left(), region.top() - geo.top())

    # --- dış arayüz --------------------------------------------------------
    def set_source_layout(self, layout: SubtitleLayout | None) -> None:
        """İngilizce altyazının konumu (yeni altyazı algılanınca)."""
        self._layout = layout
        if self._text:
            self._relayout()
            self.update()

    def set_background(self, patch) -> None:
        """Yazısı silinmiş bulanık arka plan parçası (her karede)."""
        if patch is None:
            self._patch = None
            return
        image = bgra_to_qimage(patch.image)
        self._patch = (image, patch.x, patch.y, patch.frame_size)
        if self._text and self.isVisible() and self._style == "blur":
            self.update()

    def show_text(self, text: str, badge: str = "") -> None:
        self._text = text
        self._badge = badge if self.settings.show_engine_badge else ""
        if not text:
            self._patch = None
            self.hide()
            return
        self._relayout()
        if not self.user_hidden:
            self.show()
        self.update()

    def clear(self) -> None:
        self._layout = None
        self.show_text("")

    def refresh(self) -> None:
        if self._text:
            self.show_text(self._text, self._badge)

    def set_user_hidden(self, hidden: bool) -> None:
        self.user_hidden = hidden
        if hidden:
            self.hide()
        elif self._text:
            self.show()

    # --- çizim ---------------------------------------------------------------
    def _draw_patch(self, painter: QPainter) -> None:
        if self._patch is None or self._layout is None:
            return
        image, x, y, frame_size = self._patch
        if frame_size != self._layout.frame_size:
            return
        s = self._scale
        target = QRectF(
            self._region_origin.x() + x * s,
            self._region_origin.y() + y * s,
            image.width() * s,
            image.height() * s,
        )
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawImage(target, image)

    def paintEvent(self, event):
        if not self._text:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        text_color = QColor(self.settings.text_color)
        outline = QColor(self.settings.outline_color)
        size = self._font.pixelSize()

        if self._exact:
            if self._style == "blur":
                self._draw_patch(painter)
            elif self._style == "box":
                pad = max(6.0, size * 0.35)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(0, 0, 0, int(255 * self.settings.background_opacity)))
                # Kutu hem Türkçeyi hem de altındaki İngilizceyi örter.
                cover = self._block.united(self._source).adjusted(-pad, -pad * 0.6, pad, pad * 0.6)
                painter.drawRoundedRect(cover, 8, 8)
            # Oyun altyazısı gibi: ince dış çizgi + yumuşak gölge
            self.draw_outlined_text(
                painter, self._lines, self._font, self._block, text_color, outline,
                outline_width=max(1.5, size / 11), shadow=max(1.0, size / 16),
            )
        else:
            if self._style != "text" and self.settings.background_opacity > 0:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(0, 0, 0, int(255 * self.settings.background_opacity)))
                painter.drawRoundedRect(QRectF(self.rect()), 10, 10)
            self.draw_outlined_text(painter, self._lines, self._font, self._block, text_color, outline)

        if self._badge:
            small = QFont(self.settings.font_family)
            small.setPixelSize(max(10, size // 2))
            painter.setFont(small)
            painter.setPen(QColor(200, 200, 200, 200))
            painter.drawText(QRectF(self.rect()).adjusted(8, 4, -8, -4), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop, self._badge)
        painter.end()


class Toast(_OverlayBase):
    """Tam ekranda oyun oynarken kısa durum mesajları (ör. motor değişti)."""

    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings
        self._text = ""
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)

    def _font(self) -> QFont:
        font = QFont(self.settings.font_family)
        font.setPixelSize(max(14, int(self.settings.font_size * 0.75)))
        font.setBold(True)
        return font

    def show_message(self, text: str, ms: int = 2000) -> None:
        self._text = text
        screens = QGuiApplication.screens()
        index = self.settings.monitor
        screen = screens[index] if 0 <= index < len(screens) else QGuiApplication.primaryScreen()
        geo = screen.geometry()
        metrics = QFontMetricsF(self._font())
        width = int(min(geo.width() * 0.8, metrics.horizontalAdvance(text) + 48))
        height = int(metrics.height() + 24)
        self.setGeometry(geo.x() + (geo.width() - width) // 2, geo.y() + int(geo.height() * 0.06), width, height)
        self.show()
        self.update()
        self._hide_timer.start(ms)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect())
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(20, 20, 20, 210))
        painter.drawRoundedRect(rect, 12, 12)
        font = self._font()
        lines = layout_lines(self._text, font, rect.width() - 24)
        self.draw_outlined_text(painter, lines, font, rect.adjusted(12, 6, -12, -6), QColor("#FFD54F"), QColor("#000000"))
        painter.end()
