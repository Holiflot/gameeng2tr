"""Kullanıcı sözlüğü: OCR düzeltmeleri (çeviriden önce) ve çeviri düzeltmeleri (çeviriden sonra)."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from .. import paths

log = logging.getLogger(__name__)

TEMPLATE = {
    "_aciklama": (
        "kaynak: çeviriden ÖNCE İngilizce metne uygulanır (OCR hatalarını düzeltmek için). "
        "ceviri: çeviriden SONRA Türkçe metne uygulanır (isim/terim düzeltmek için). "
        "Anahtarlar büyük/küçük harfe duyarlıdır ve tam kelime olarak eşleşir."
    ),
    "kaynak": {"Foundiing": "Foundling"},
    "ceviri": {},
}


def _compile(mapping: dict) -> list[tuple[re.Pattern, str]]:
    rules = []
    for key, value in mapping.items():
        if not isinstance(key, str) or not isinstance(value, str) or not key:
            continue
        rules.append((re.compile(r"(?<!\w)" + re.escape(key) + r"(?!\w)"), value))
    # Uzun ifadeler önce uygulanır.
    rules.sort(key=lambda r: -len(r[0].pattern))
    return rules


class Glossary:
    def __init__(self, source: dict | None = None, target: dict | None = None):
        self._source = _compile(source or {})
        self._target = _compile(target or {})

    @classmethod
    def load(cls, path: Path | None = None) -> "Glossary":
        path = path or paths.glossary_path()
        if not path.exists():
            try:
                path.write_text(json.dumps(TEMPLATE, indent=2, ensure_ascii=False), encoding="utf-8")
            except OSError:
                pass
            return cls(TEMPLATE["kaynak"], TEMPLATE["ceviri"])
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            log.warning("Sözlük okunamadı: %s", exc)
            return cls()
        return cls(data.get("kaynak", {}), data.get("ceviri", {}))

    @staticmethod
    def _apply(rules, text: str) -> str:
        for pattern, value in rules:
            text = pattern.sub(value, text)
        return text

    def fix_source(self, text: str) -> str:
        return self._apply(self._source, text)

    def fix_target(self, text: str) -> str:
        return self._apply(self._target, text)
