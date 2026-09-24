import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from gameeng2tr.config import Settings
from gameeng2tr.textproc import SubtitleEvent
from gameeng2tr.translate.service import TranslationResult


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_overlay_layout_and_positions(app):
    from gameeng2tr.ui.overlay import SubtitleOverlay, layout_lines

    settings = Settings(region=[0.1, 0.8, 0.9, 0.95], overlay_position="above", font_size=28)
    overlay = SubtitleOverlay(settings)
    long_text = "Buraya geri dönmemeliydin, Foundling. Kabuk senin unuttuklarını hatırlıyor ve seni bekliyor. " * 2
    overlay.show_text(long_text)
    region = overlay.region_rect()
    assert overlay.isVisible()
    assert overlay.geometry().bottom() < region.top()
    assert len(layout_lines(long_text, overlay.font(), region.width() - 36)) >= 2

    settings.overlay_position = "below"
    settings.region = [0.1, 0.3, 0.9, 0.4]
    overlay.refresh()
    assert overlay.geometry().top() > overlay.region_rect().bottom()

    # Ekran dışına taşmaz
    settings.region = [0.1, 0.8, 0.9, 0.95]
    overlay.refresh()
    screen = overlay._screen().geometry()
    assert overlay.geometry().bottom() <= screen.bottom()

    # Yakalamadan hariç tutulamıyorsa "over" kendi yazısını OCR'lamamak için yukarı kayar.
    settings.overlay_position = "over"
    overlay.excluded_from_capture = False
    overlay.refresh()
    assert overlay.geometry().bottom() < region.top()
    overlay.excluded_from_capture = True
    overlay.refresh()
    assert overlay.geometry().bottom() == region.bottom()

    overlay.set_user_hidden(True)
    assert not overlay.isVisible()
    overlay.set_user_hidden(False)
    assert overlay.isVisible()
    overlay.clear()
    assert not overlay.isVisible()
    img = overlay.grab()
    assert not img.isNull()


def test_main_window_and_controller_flow(app):
    from gameeng2tr.controller import Controller
    from gameeng2tr.ui.main_window import MainWindow

    settings = Settings()
    controller = Controller(settings)
    window = MainWindow(controller)
    window.show()

    submitted = []
    controller.service.submit = lambda seq, text, tag="live": submitted.append((seq, text, tag))
    controller._on_subtitle_event(SubtitleEvent("show", "Hello there."))
    assert submitted == [(1, "Hello there.", "live")]

    controller.translation_result.emit(TranslationResult(1, "Hello there.", "Merhaba.", "opus", 12.0, False))
    app.processEvents()
    assert window.live_tr.text() == "Merhaba."
    assert window.history.count() == 1
    assert controller.overlay._text == "Merhaba."

    # Eski bir sonucun yenisinin üzerine yazmaması
    controller._on_subtitle_event(SubtitleEvent("show", "Second."))
    controller.translation_result.emit(TranslationResult(2, "Second.", "İkinci.", "opus", 10.0, False))
    controller.translation_result.emit(TranslationResult(1, "Hello there.", "Merhaba.", "gemma", 10.0, False))
    app.processEvents()
    assert controller.overlay._text == "İkinci."

    controller._on_subtitle_event(SubtitleEvent("clear"))
    assert not controller.overlay.isVisible()

    # Motor değiştirme: radyo düğmesi ve ayar birlikte güncellenir
    switched = []
    controller.service.set_engine = switched.append
    controller.cycle_engine()
    assert settings.engine == "gemma" and switched == ["gemma"]
    assert window.engine_radios["gemma"].isChecked()
    window.engine_radios["opus"].setChecked(True)
    assert settings.engine == "opus" and switched == ["gemma", "opus"]

    controller.set_region([0.2, 0.7, 0.8, 0.9])
    assert settings.region == [0.2, 0.7, 0.8, 0.9]
    assert "%20" in window.region_label.text()

    window.close()
    controller.toast.close()
    controller.overlay.close()


def test_region_selector_emits_fractions(app):
    import numpy as np
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtCore import QEvent

    from gameeng2tr.ui.region_selector import RegionSelector

    frame = np.zeros((1080, 1920, 3), np.uint8)
    selector = RegionSelector(frame, 0, [0.1, 0.8, 0.9, 0.95])
    selector.setGeometry(0, 0, 1000, 500)
    got = []
    selector.selected.connect(got.append)

    def mouse(kind, x, y):
        buttons = Qt.MouseButton.LeftButton if kind != QEvent.Type.MouseButtonRelease else Qt.MouseButton.NoButton
        return QMouseEvent(kind, QPointF(x, y), QPointF(x, y), Qt.MouseButton.LeftButton, buttons, Qt.KeyboardModifier.NoModifier)

    selector.mousePressEvent(mouse(QEvent.Type.MouseButtonPress, 100, 400))
    selector.mouseMoveEvent(mouse(QEvent.Type.MouseMove, 900, 480))
    selector.mouseReleaseEvent(mouse(QEvent.Type.MouseButtonRelease, 900, 480))
    assert got and got[0] == pytest.approx([0.1, 0.8, 0.901, 0.962], abs=0.002)
