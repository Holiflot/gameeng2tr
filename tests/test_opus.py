import sys
import types
from pathlib import Path

import pytest

from gameeng2tr.translate.base import TranslatorError
from gameeng2tr.translate.opus import OpusTranslator


class FakeSP:
    def __init__(self, model_file):
        self.model_file = model_file

    def encode(self, text, out_type=str):
        return ["▁" + w for w in text.split()]

    def decode(self, tokens):
        return "".join(tokens).replace("▁", " ").strip()


class FakeResult:
    def __init__(self, tokens):
        self.hypotheses = [tokens]


class FakeCT2Translator:
    instances = []

    def __init__(self, path, **kwargs):
        self.path = path
        self.kwargs = kwargs
        self.batches = []
        FakeCT2Translator.instances.append(self)

    def translate_batch(self, batch, target_prefix=None, **kwargs):
        self.batches.append((batch, target_prefix, kwargs))
        return [FakeResult(["▁TR"] + [t.upper() for t in src if t != "</s>"] + ["</s>"]) for src in batch]


@pytest.fixture
def fake_libs(monkeypatch):
    ct2 = types.SimpleNamespace(Translator=FakeCT2Translator, get_cuda_device_count=lambda: 0)
    spm = types.SimpleNamespace(SentencePieceProcessor=FakeSP)
    monkeypatch.setitem(sys.modules, "ctranslate2", ct2)
    monkeypatch.setitem(sys.modules, "sentencepiece", spm)
    FakeCT2Translator.instances = []


def make_model_dir(tmp_path: Path) -> Path:
    for name in ("model.bin", "source.spm", "target.spm", "shared_vocabulary.json"):
        (tmp_path / name).write_text("x")
    return tmp_path


def test_missing_model_raises_setup_hint(tmp_path, fake_libs):
    with pytest.raises(TranslatorError, match="setup_models"):
        OpusTranslator(model_dir=tmp_path).load()


def test_translate_splits_sentences_and_appends_eos(tmp_path, fake_libs):
    t = OpusTranslator(model_dir=make_model_dir(tmp_path), device="cuda", beam_size=3)
    out = t.translate("Go now. Why wait?")
    ct2 = FakeCT2Translator.instances[0]
    # CUDA yoksa CPU'ya düşer
    assert ct2.kwargs["device"] == "cpu"
    assert ct2.kwargs["compute_type"] == "int8"
    batch, prefix, kwargs = ct2.batches[0]
    assert batch == [["▁Go", "▁now.", "</s>"], ["▁Why", "▁wait?", "</s>"]]
    assert prefix is None
    assert kwargs["beam_size"] == 3
    assert out == "TR GO NOW. TR WHY WAIT?"


def test_target_prefix(tmp_path, fake_libs):
    t = OpusTranslator(model_dir=make_model_dir(tmp_path), target_prefix=">>tur<<")
    t.translate("Hi.")
    batch, prefix, _ = FakeCT2Translator.instances[0].batches[0]
    assert prefix == [[">>tur<<"]]
