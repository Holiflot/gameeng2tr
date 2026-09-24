"""Ekran görüntüsü üzerinde fareyle altyazı bölgesi seçme."""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QWidget


def bgr_to_qimage(frame: np.ndarray) -> QImage:
    frame = np.ascontiguousarray(frame[..., :3])
    h, w = frame.shape[:2]
    image = QImage(frame.data, w, h, 3 * w, QImage.Format.Format_BGR888)
    return image.copy()  # numpy belleğinden bağımsız kopya


class RegionSelector(QWidget):
    """Tam ekran seçim penceresi. Sürükleyip bırakınca `selected(list[float])` yayar."""

    selected = Signal(list)
    cancelled = Signal()

    def __init__(self, frame: np.ndarray | None, monitor: int, current: list[float]):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setCursor(Qt.CursorShape.CrossCursor)
        screens = QGuiApplication.screens()
        screen = screens[monitor] if 0 <= monitor < len(screens) else QGuiApplication.primaryScreen()
        self.setGeometry(screen.geometry())
        self._pixmap = QPixmap.fromImage(bgr_to_qimage(frame)) if frame is not None else None
        self._current = current
        self._origin: QPoint | None = None
        self._rect = QRect()

    def showEvent(self, event):
        super().showEvent(event)
        self.activateWindow()
        self.raise_()

    def _current_rect(self) -> QRect:
        l, t, r, b = self._current
        w, h = self.width(), self.height()
        return QRect(round(l * w), round(t * h), round((r - l) * w), round((b - t) * h))

    def paintEvent(self, event):
        painter = QPainter(self)
        if self._pixmap is not None:
            painter.drawPixmap(self.rect(), self._pixmap)
        else:
            painter.fillRect(self.rect(), QColor(30, 30, 30))
        painter.fillRect(self.rect(), QColor(0, 0, 0, 110))

        painter.setPen(QPen(QColor(255, 255, 255, 120), 1, Qt.PenStyle.DashLine))
        painter.drawRect(self._current_rect())

        if not self._rect.isNull():
            if self._pixmap is not None:
                source = QRect(
                    round(self._rect.x() * self._pixmap.width() / self.width()),
                    round(self._rect.y() * self._pixmap.height() / self.height()),
                    round(self._rect.width() * self._pixmap.width() / self.width()),
                    round(self._rect.height() * self._pixmap.height() / self.height()),
                )
                painter.drawPixmap(self._rect, self._pixmap, source)
            painter.setPen(QPen(QColor("#4FC3F7"), 2))
            painter.drawRect(self._rect)

        font = QFont("Segoe UI")
        font.setPixelSize(22)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor("#FFFFFF"))
        painter.drawText(
            self.rect().adjusted(0, 40, 0, 0),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            "Altyazının çıktığı alanı fareyle seçin (iki satırlık altyazıya yer bırakın)\n"
            "Esc: iptal  •  Enter: kesikli çizgili mevcut bölgeyi koru",
        )
        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._origin = event.position().toPoint()
            self._rect = QRect(self._origin, self._origin)
            self.update()
        elif event.button() == Qt.MouseButton.RightButton:
            self._cancel()

    def mouseMoveEvent(self, event):
        if self._origin is not None:
            self._rect = QRect(self._origin, event.position().toPoint()).normalized()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or self._origin is None:
            return
        self._origin = None
        rect = self._rect.normalized()
        if rect.width() < 20 or rect.height() < 10:
            self._rect = QRect()
            self.update()
            return
        w, h = self.width(), self.height()
        region = [rect.left() / w, rect.top() / h, (rect.right() + 1) / w, (rect.bottom() + 1) / h]
        self.selected.emit(region)
        self.close()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self._cancel()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.selected.emit(list(self._current))
            self.close()

    def _cancel(self):
        self.cancelled.emit()
        self.close()
