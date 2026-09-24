import numpy as np

from gameeng2tr.preprocess import ensure_min_size, high_contrast, signature_changed, text_signature


def make_frame(text_boxes, noise_seed=None, shape=(180, 1300)):
    rng = np.random.default_rng(noise_seed)
    frame = (rng.random((*shape, 3)) * 140).astype(np.uint8) if noise_seed is not None else np.zeros((*shape, 3), np.uint8)
    for x, y, w, h in text_boxes:
        # "yazı" benzeri beyaz çizgiler
        frame[y:y + h:3, x:x + w] = 255
    return frame


def test_signature_ignores_changing_dark_background():
    a = text_signature(make_frame([(300, 60, 500, 30)], noise_seed=1))
    b = text_signature(make_frame([(300, 60, 500, 30)], noise_seed=2))
    assert not signature_changed(a, b)


def test_signature_detects_new_text_even_short_word():
    a = text_signature(make_frame([(300, 60, 500, 30)]))
    b = text_signature(make_frame([(300, 60, 500, 30), (900, 60, 50, 30)]))
    assert signature_changed(a, b)
    assert signature_changed(None, a)


def test_high_contrast_makes_black_text_on_white():
    frame = make_frame([(10, 10, 100, 20)], shape=(60, 200))
    out = high_contrast(frame)
    assert out.shape == frame.shape
    assert out[10, 50].tolist() == [0, 0, 0]
    assert out[50, 190].tolist() == [255, 255, 255]


def test_ensure_min_size():
    small = np.zeros((20, 300, 3), np.uint8)
    assert ensure_min_size(small).shape[0] >= 60
    big = np.zeros((100, 300, 3), np.uint8)
    assert ensure_min_size(big) is big
