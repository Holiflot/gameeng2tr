"""Altyazıyı yerinde silme/bulanıklaştırma ve Türkçeyi tam üstüne yerleştirme."""

import time

import numpy as np
import pytest

from gameeng2tr.config import Settings
from gameeng2tr.ocr.base import OcrEngine, OcrLine
from gameeng2tr.pipeline import BackgroundPatch, CapturePipeline, measure_layout
from gameeng2tr.preprocess import erase_text_patch, ink_height
from gameeng2tr.textproc import SubtitleLayout

cv2 = pytest.importorskip("cv2")


def game_frame(w=1200, h=180):
    yy, xx = np.mgrid[0:h, 0:w]
    bg = np.stack([60 + 50 * np.sin(xx / 90.0), 80 + 40 * np.cos(yy / 30.0 + xx / 200.0), 50 + 30 * np.sin(xx / 40.0)], -1)
    bg = np.clip(bg, 0, 255).astype(np.uint8)
    cv2.circle(bg, (200, 90), 50, (40, 120, 200), -1)
    return bg


def with_text(frame, lines, size=1.0, y0=40, step=50):
    out = frame.copy()
    for i, line in enumerate(lines):
        (tw, th), _ = cv2.getTextSize(line, cv2.FONT_HERSHEY_SIMPLEX, size, 2)
        org = ((out.shape[1] - tw) // 2, y0 + i * step + th)
        cv2.putText(out, line, org, cv2.FONT_HERSHEY_SIMPLEX, size, (0, 0, 0), 6, cv2.LINE_AA)
        cv2.putText(out, line, org, cv2.FONT_HERSHEY_SIMPLEX, size, (255, 255, 255), 2, cv2.LINE_AA)
    return out


def text_box(frame, clean):
    diff = np.any(np.abs(frame.astype(int) - clean.astype(int)) > 30, axis=2)
    ys, xs = np.nonzero(diff)
    return (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1)


def test_ink_height_measures_text_size():
    clean = game_frame()
    small = with_text(clean, ["Hello there"], size=0.8)
    big = with_text(clean, ["Hello there"], size=1.6)
    h_small = ink_height(small, text_box(small, clean))
    h_big = ink_height(big, text_box(big, clean))
    assert h_small and h_big
    assert 1.7 < h_big / h_small < 2.3


def test_erase_removes_text_and_blends_edges():
    clean = game_frame()
    frame = with_text(clean, ["You shouldn't have come back here.", "The Shell remembers."])
    box = text_box(frame, clean)
    lh = ink_height(frame, box)
    patch, x, y = erase_text_patch(frame, box, lh, blur=8)
    ph, pw = patch.shape[:2]
    assert x <= box[0] and y <= box[1] and x + pw >= box[2] and y + ph >= box[3]

    alpha = patch[..., 3].astype(np.float32) / 255
    # Kutu içi tamamen kapalı, dış kenarlar yumuşakça sıfıra iner
    cy, cx = (box[1] + box[3]) // 2 - y, (box[0] + box[2]) // 2 - x
    assert alpha[cy, cx] > 0.98
    assert alpha[0, 0] < 0.05

    out = frame.copy().astype(np.float32)
    region = out[y:y + ph, x:x + pw]
    out[y:y + ph, x:x + pw] = patch[..., :3] * alpha[..., None] + region * (1 - alpha[..., None])
    out = out.astype(np.uint8)
    inside = (slice(box[1], box[3]), slice(box[0], box[2]))
    # Beyaz yazı pikselleri kalmadı
    assert np.count_nonzero(cv2.cvtColor(out[inside], cv2.COLOR_BGR2GRAY) > 200) == 0
    # Sonuç, yazısız sahnenin bulanık haline yakın (renkler korunur)
    assert np.abs(out[inside].astype(int) - clean[inside].astype(int)).mean() < 25


def test_measure_layout():
    clean = game_frame()
    frame = with_text(clean, ["First line of text", "Second line"], size=1.0)
    boxes = []
    for i in range(2):
        band = frame[40 + i * 50 - 5: 40 + i * 50 + 40]
        band_clean = clean[40 + i * 50 - 5: 40 + i * 50 + 40]
        x0, y0, x1, y1 = text_box(band, band_clean)
        boxes.append((x0, y0 + 40 + i * 50 - 5, x1, y1 + 40 + i * 50 - 5))
    layout = measure_layout(frame, [OcrLine("First line of text", boxes[0]), OcrLine("Second line", boxes[1])])
    assert layout.line_count == 2
    assert layout.frame_size == (1200, 180)
    assert layout.box[0] == min(b[0] for b in boxes) and layout.box[3] == max(b[3] for b in boxes)
    assert 15 < layout.line_height < 40


class FixedOcr(OcrEngine):
    name = "fake"

    def __init__(self, source):
        self.source = source

    def recognize(self, img):
        if not self.source.lines:
            return []
        return [OcrLine(t, (300, 40 + 50 * i, 900, 75 + 50 * i)) for i, t in enumerate(self.source.lines)]


class Screen:
    def __init__(self):
        self.lines = []
        self.clean = game_frame()

    def grab_region(self, region):
        return with_text(self.clean, self.lines) if self.lines else self.clean


def test_pipeline_attaches_layout_and_streams_backgrounds(monkeypatch):
    screen = Screen()
    monkeypatch.setattr("gameeng2tr.pipeline.create_ocr", lambda name: (FixedOcr(screen), []))
    settings = Settings(capture_fps=10, blur_fps=30, stable_frames=2, clear_after=0.2, overlay_style="blur")
    events, patches = [], []
    pipe = CapturePipeline(settings, lambda: screen, on_event=events.append, on_background=patches.append)
    pipe.start()
    try:
        time.sleep(0.2)
        screen.lines = ["Welcome back."]
        time.sleep(0.8)
        shown_patches = len(patches)
        screen.lines = []
        time.sleep(0.6)
    finally:
        pipe.close()
    show = [e for e in events if e.kind == "show"]
    assert show and show[0].layout is not None
    assert show[0].layout.frame_size == (1200, 180)
    # Altyazı ekrandayken arka plan sürekli güncellenir (blur_fps ~30)
    assert shown_patches >= 10
    assert all(isinstance(p, BackgroundPatch) for p in patches)
    assert events[-1].kind == "clear"
    # Altyazı kalkınca yama üretimi durur
    count = len(patches)
    assert count - shown_patches <= 12


def test_no_backgrounds_in_box_style(monkeypatch):
    screen = Screen()
    screen.lines = ["Hello there."]
    monkeypatch.setattr("gameeng2tr.pipeline.create_ocr", lambda name: (FixedOcr(screen), []))
    patches = []
    pipe = CapturePipeline(Settings(capture_fps=20, overlay_style="box"), lambda: screen,
                           on_event=lambda e: None, on_background=patches.append)
    pipe.start()
    time.sleep(0.4)
    pipe.close()
    assert patches == []


# --- overlay yerleşimi (Qt, ekransız) ---------------------------------------

@pytest.fixture(scope="module")
def app():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def make_overlay(settings):
    from gameeng2tr.ui.overlay import SubtitleOverlay

    overlay = SubtitleOverlay(settings)
    overlay.excluded_from_capture = True  # Windows'ta WDA_EXCLUDEFROMCAPTURE başarılı
    return overlay


def test_exact_placement_matches_english_position_and_size(app):
    from gameeng2tr.ui.overlay import ink_ratio

    # Ekransız Qt ekranı 800x800; bölge ekranın alt çeyreği = 800x200 mantıksal piksel
    settings = Settings(region=[0.0, 0.75, 1.0, 1.0], overlay_style="blur", font_family="DejaVu Sans")
    overlay = make_overlay(settings)
    region = overlay.region_rect()
    # Yakalanan kare 1600x400 (ör. %200 ölçekli ekran) -> ölçek 0.5
    layout = SubtitleLayout(box=(400, 100, 1200, 180), line_height=40, line_count=1, frame_size=(1600, 400))
    overlay.set_source_layout(layout)
    overlay.show_text("Buraya geri dönmemeliydin.")
    geo = overlay.geometry()
    block = overlay._block.translated(geo.left(), geo.top())
    english_center_x = region.left() + (400 + 1200) / 2 * 0.5
    english_center_y = region.top() + (100 + 180) / 2 * 0.5
    assert abs(block.center().x() - english_center_x) < 1.5
    assert abs(block.center().y() - english_center_y) < 1.5
    # Yazı boyutu: mürekkep yüksekliği 40 * 0.5 = 20 mantıksal piksel
    expected = 20 / ink_ratio(overlay.font(100))
    assert abs(overlay._font.pixelSize() - expected) <= 1
    assert geo.contains(region)

    settings.font_scale = 1.5
    overlay.refresh()
    assert abs(overlay._font.pixelSize() - expected * 1.5) <= 1

    settings.font_auto = False
    settings.font_size = 33
    overlay.refresh()
    assert overlay._font.pixelSize() == 33


def test_long_turkish_wraps_and_grows_window(app):
    settings = Settings(region=[0.0, 0.8, 1.0, 0.95], overlay_style="blur", font_family="DejaVu Sans")
    overlay = make_overlay(settings)
    region = overlay.region_rect()
    layout = SubtitleLayout(box=(250, 20, 550, 60), line_height=30, line_count=2, frame_size=(800, 120))
    overlay.set_source_layout(layout)
    overlay.show_text("Kabuk senin unuttuklarını hatırlıyor ve karanlıkta seni bekliyor, geri dönmemeliydin Foundling.")
    assert len(overlay._lines) >= 2
    # İki satırlık İngilizce: Türkçe benzer genişlikte sarılır
    assert max(w for _, w in overlay._lines) <= 300 * 1.15 + 1
    assert overlay.geometry().contains(region)


def test_blur_falls_back_to_box_without_capture_exclusion(app):
    settings = Settings(region=[0.0, 0.75, 1.0, 1.0], overlay_style="blur")
    overlay = make_overlay(settings)
    overlay.excluded_from_capture = False
    overlay.set_source_layout(SubtitleLayout((100, 50, 700, 90), 30, 1, (800, 200)))
    overlay.show_text("Merhaba.")
    assert overlay._style == "box"
    assert overlay.geometry().bottom() < overlay.region_rect().top()


def test_background_patch_is_painted(app):
    from PySide6.QtGui import QColor

    settings = Settings(region=[0.0, 0.75, 1.0, 1.0], overlay_style="blur", font_family="DejaVu Sans")
    overlay = make_overlay(settings)
    overlay.set_source_layout(SubtitleLayout((100, 50, 700, 150), 30, 1, (800, 200)))
    patch = np.zeros((200, 800, 4), np.uint8)
    patch[..., 1] = 200  # yeşil
    patch[..., 3] = 255
    overlay.set_background(BackgroundPatch(patch, 0, 0, (800, 200)))
    overlay.show_text("x")
    image = overlay.grab().toImage()
    corner = QColor(image.pixel(5, image.height() - 5))
    assert corner.green() > 150 and corner.red() < 50
    overlay.clear()
    assert overlay._patch is None
