"""Uygulama verisi (ayarlar, modeller, log) için klasörler."""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "gameeng2tr"


def data_dir() -> Path:
    override = os.environ.get("GAMEENG2TR_HOME")
    if override:
        base = Path(override)
    elif sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / APP_NAME
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / APP_NAME
    base.mkdir(parents=True, exist_ok=True)
    return base


def models_dir() -> Path:
    path = data_dir() / "models"
    path.mkdir(parents=True, exist_ok=True)
    return path


def settings_path() -> Path:
    return data_dir() / "settings.json"


def glossary_path() -> Path:
    return data_dir() / "sozluk.json"


def log_path() -> Path:
    return data_dir() / "gameeng2tr.log"


OPUS_MODEL_ID = "Helsinki-NLP/opus-mt-tc-big-en-tr"


def opus_model_dir() -> Path:
    return models_dir() / "opus-mt-tc-big-en-tr-ct2"
