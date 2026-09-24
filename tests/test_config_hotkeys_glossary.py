import json

import pytest

from gameeng2tr import paths
from gameeng2tr.config import Settings, normalize_region
from gameeng2tr.hotkeys import MOD_ALT, MOD_CONTROL, MOD_SHIFT, parse_hotkey
from gameeng2tr.translate.glossary import Glossary


def test_settings_roundtrip(tmp_path):
    path = tmp_path / "s.json"
    s = Settings(engine="gemma", font_size=40, region=[0.1, 0.7, 0.9, 0.95])
    s.save(path)
    loaded = Settings.load(path)
    assert loaded.engine == "gemma"
    assert loaded.font_size == 40
    assert loaded.region == [0.1, 0.7, 0.9, 0.95]


def test_settings_tolerates_bad_values(tmp_path):
    path = tmp_path / "s.json"
    path.write_text(json.dumps({"engine": "nope", "font_size": "abc", "unknown": 1, "capture_fps": 500, "region": [1, 1, 0, 0]}))
    s = Settings.load(path)
    assert s.engine == "opus"
    assert s.font_size == 28
    assert s.capture_fps == 30.0
    assert s.region == [0.0, 0.0, 1.0, 1.0]


def test_settings_corrupt_file(tmp_path):
    path = tmp_path / "s.json"
    path.write_text("{not json")
    assert Settings.load(path).engine == "opus"


def test_normalize_region():
    assert normalize_region([0.9, 0.97, 0.1, 0.8]) == [0.1, 0.8, 0.9, 0.97]
    assert normalize_region([0.5, 0.5, 0.5, 0.5]) == [0.12, 0.80, 0.88, 0.97]
    assert normalize_region("bad") == [0.12, 0.80, 0.88, 0.97]


def test_parse_hotkey():
    assert parse_hotkey("ctrl+alt+t") == (MOD_CONTROL | MOD_ALT, ord("T"))
    assert parse_hotkey("Shift + F9") == (MOD_SHIFT, 0x78)
    assert parse_hotkey("alt+num5") == (MOD_ALT, 0x65)
    with pytest.raises(ValueError):
        parse_hotkey("ctrl+hyper+x")
    with pytest.raises(ValueError):
        parse_hotkey("")


def test_glossary_rules():
    g = Glossary({"Foundiing": "Foundling"}, {"Kabuk": "Shell", "Kurtarıcı": "Foundling"})
    assert g.fix_source("Hello Foundiing.") == "Hello Foundling."
    assert g.fix_target("Kabuk seni hatırlıyor, Kurtarıcı.") == "Shell seni hatırlıyor, Foundling."
    # Tam kelime eşleşmesi: "Kabuklar" değişmez
    assert g.fix_target("Kabuklar") == "Kabuklar"


def test_glossary_creates_template_file():
    g = Glossary.load()
    assert paths.glossary_path().exists()
    assert g.fix_source("Foundiing") == "Foundling"
