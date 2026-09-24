"""Uçtan uca: sahte oyun karesi -> gerçek RapidOCR -> takip -> (sahte) çevirmen -> overlay."""

import time

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("rapidocr_onnxruntime")

from PySide6.QtWidgets import QApplication

from gameeng2tr.config import Settings
from gameeng2tr.translate.base import Translator

from .test_ocr_pipeline import render_subtitle


class EchoTranslator(Translator):
    name = "opus"

    def load(self):
        pass

    def translate(self, text):
        return "TR<" + text + ">"


class GameScreen:
    def __init__(self):
        self.lines = []
        self.frames = {}

    def grab_region(self, region):
        key = tuple(self.lines)
        if key not in self.frames:
            self.frames[key] = render_subtitle(list(key)) if key else render_subtitle([])
        return self.frames[key]

    def close(self):
        pass


def wait_until(app, predicate, timeout=15.0):
    end = time.time() + timeout
    while time.time() < end:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.02)
    return False


def test_full_chain(monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(
        "gameeng2tr.controller.make_factories",
        lambda settings: {"opus": EchoTranslator, "gemma": EchoTranslator},
    )
    from gameeng2tr.controller import Controller

    settings = Settings(ocr_backend="rapidocr", capture_fps=10, stable_frames=2, clear_after=0.3)
    controller = Controller(settings)
    screen = GameScreen()
    monkeypatch.setattr(controller, "_get_capture", lambda: screen)
    controller.pipeline._get_capture = lambda: screen
    controller.boot()
    try:
        controller.start()
        screen.lines = ["Tiel: You shouldn't have come back here."]
        assert wait_until(app, lambda: controller.overlay._text == "Tiel: TR<You shouldn't have come back here.>")
        assert controller.overlay.isVisible()

        screen.lines = []
        assert wait_until(app, lambda: not controller.overlay.isVisible())
    finally:
        controller.stop()
        controller.shutdown()
