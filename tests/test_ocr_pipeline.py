import glob
import threading
import time

import numpy as np
import pytest

from gameeng2tr.config import Settings
from gameeng2tr.ocr import create_ocr
from gameeng2tr.ocr.base import OcrEngine, group_lines
from gameeng2tr.pipeline import CapturePipeline


def render_subtitle(lines, size=(160, 1300), seed=0):
    from PIL import Image, ImageDraw, ImageFilter, ImageFont

    fonts = sorted(glob.glob("/usr/share/fonts/**/DejaVuSans.ttf", recursive=True)) or sorted(
        glob.glob("/usr/share/fonts/**/*Sans*.ttf", recursive=True)
    )
    if not fonts:
        pytest.skip("yazı tipi yok")
    font = ImageFont.truetype(fonts[0], 30)
    rng = np.random.default_rng(seed)
    bg = (rng.random((*size, 3)) * 120).astype("uint8")
    img = Image.fromarray(bg).filter(ImageFilter.GaussianBlur(3))
    draw = ImageDraw.Draw(img)
    for i, line in enumerate(lines):
        width = draw.textlength(line, font=font)
        draw.text(((size[1] - width) / 2, 20 + i * 50), line, font=font, fill=(255, 255, 255), stroke_width=2, stroke_fill=(0, 0, 0))
    return np.array(img)[:, :, ::-1].copy()  # BGR


def test_group_lines_orders_boxes():
    boxes = [(50, 80, 400, "world"), (0, 30, 10, "Hello"), (52, 78, 10, "big"), (2, 28, 300, "there")]
    assert group_lines(boxes) == ["Hello there", "big world"]


def test_rapidocr_reads_game_subtitle():
    pytest.importorskip("rapidocr_onnxruntime")
    engine, _ = create_ocr("rapidocr")
    lines = engine.recognize(render_subtitle(["Tiel: You shouldn't have come back here.", "The Shell remembers."]))
    assert lines == ["Tiel: You shouldn't have come back here.", "The Shell remembers."]


def test_auto_ocr_falls_back_on_linux():
    pytest.importorskip("rapidocr_onnxruntime")
    engine, errors = create_ocr("auto")
    assert engine.name == "rapidocr"
    assert len(errors) == 2


class ScriptedOcr(OcrEngine):
    name = "fake"
    label = "Fake"

    def __init__(self, script):
        self.script = script
        self.calls = 0

    def recognize(self, img):
        self.calls += 1
        return self.script(img)


class FrameSource:
    """Görüntünün ilk pikseli hangi altyazının gösterildiğini kodlar."""

    def __init__(self):
        self.value = 0

    def grab_region(self, region):
        frame = np.zeros((60, 400, 3), np.uint8)
        if self.value:
            frame[10:40:2, 20:20 + 30 * self.value] = 255
        return frame


def test_pipeline_emits_show_and_clear(monkeypatch):
    texts = {0: [], 1: ["Welcome back,", "Foundling."], 2: ["Go now."]}
    source = FrameSource()
    ocr = ScriptedOcr(lambda img: texts[source.value])
    monkeypatch.setattr("gameeng2tr.pipeline.create_ocr", lambda name: (ocr, []))

    settings = Settings(capture_fps=30, stable_frames=2, clear_after=0.2)
    events = []
    lock = threading.Lock()

    def on_event(ev):
        with lock:
            events.append((ev.kind, ev.text))

    pipe = CapturePipeline(settings, lambda: source, on_event=on_event)
    pipe.start()
    try:
        time.sleep(0.2)
        source.value = 1
        time.sleep(0.4)
        source.value = 2
        time.sleep(0.4)
        source.value = 0
        time.sleep(0.6)
    finally:
        pipe.close()
    assert events == [("show", "Welcome back, Foundling."), ("show", "Go now."), ("clear", "")]
    # Görüntü değişmediğinde OCR atlanır (≈40 kare yerine çok daha az çağrı).
    assert ocr.calls < 20


def test_pipeline_reports_stop_when_no_ocr(monkeypatch):
    from gameeng2tr.ocr import OcrUnavailable

    def fail(name):
        raise OcrUnavailable("hiçbiri yok")

    monkeypatch.setattr("gameeng2tr.pipeline.create_ocr", fail)
    stopped, statuses = [], []
    pipe = CapturePipeline(Settings(), lambda: FrameSource(), on_event=lambda e: None,
                           on_status=statuses.append, on_stopped=lambda: stopped.append(True))
    pipe.start()
    time.sleep(0.3)
    assert stopped == [True]
    assert statuses[-1] == "hiçbiri yok"
    assert not pipe.running
