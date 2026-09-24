"""Oyunun üstünde duran, tıklanamaz ve ekran yakalamaya girmeyen çeviri katmanı."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QGuiApplication, QPainter, QPainterPath, QPen, QTextLayout, QTextOption
from PySide6.QtWidgets import QWidget

from .. import win32
from ..config import Settings

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
    def draw_outlined_text(painter: QPainter, lines, font: QFont, rect: QRectF, color: QColor, outline: QColor):
        metrics = QFontMetricsF(font)
        line_h = metrics.height()
        total_h = line_h * len(lines)
        y = rect.top() + (rect.height() - total_h) / 2 + metrics.ascent()
        path = QPainterPath()
        for text, width in lines:
            x = rect.left() + (rect.width() - width) / 2
            path.addText(QPointF(x, y), font, text)
            y += line_h
        outline_width = max(2.0, font.pixelSize() / 7)
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

    def font(self) -> QFont:
        font = QFont(self.settings.font_family)
        font.setPixelSize(self.settings.font_size)
        font.setBold(self.settings.font_bold)
        return font

    def _relayout(self) -> None:
        region = self.region_rect()
        screen_geo = self._screen().geometry()
        width = max(region.width(), 200)
        font = self.font()
        self._lines = layout_lines(self._text, font, width - 2 * PADDING_X)
        text_h = QFontMetricsF(font).height() * max(1, len(self._lines)) + 2 * PADDING_Y
        mode = self.settings.overlay_position
        if mode == "over" and not self.excluded_from_capture:
            # Pencere yakalamadan hariç tutulamadıysa kendi yazımızı OCR'lamamak için üste taşı.
            mode = "above"
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
        self.setGeometry(region.left() + (region.width() - width) // 2, top, width, height)

    # --- dış arayüz --------------------------------------------------------
    def show_text(self, text: str, badge: str = "") -> None:
        self._text = text
        self._badge = badge if self.settings.show_engine_badge else ""
        if not text:
            self.hide()
            return
        self._relayout()
        if not self.user_hidden:
            self.show()
        self.update()

    def clear(self) -> None:
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

    def paintEvent(self, event):
        if not self._text:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        rect = QRectF(self.rect())
        opacity = self.settings.background_opacity
        if opacity > 0:
            bg = QColor(0, 0, 0, int(255 * opacity))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(bg)
            painter.drawRoundedRect(rect, 10, 10)
        self.draw_outlined_text(
            painter,
            self._lines,
            self.font(),
            rect.adjusted(PADDING_X, PADDING_Y, -PADDING_X, -PADDING_Y),
            QColor(self.settings.text_color),
            QColor(self.settings.outline_color),
        )
        if self._badge:
            small = QFont(self.settings.font_family)
            small.setPixelSize(max(10, self.settings.font_size // 2))
            painter.setFont(small)
            painter.setPen(QColor(200, 200, 200, 200))
            painter.drawText(rect.adjusted(8, 4, -8, -4), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop, self._badge)
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
