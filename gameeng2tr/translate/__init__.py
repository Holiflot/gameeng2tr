"""Çeviri motorları."""

from __future__ import annotations

from typing import Callable

from ..config import ENGINE_GEMMA, ENGINE_OPUS, Settings
from .base import Translator, TranslatorError

LABELS = {
    ENGINE_OPUS: "Opus-MT (hızlı)",
    ENGINE_GEMMA: "TranslateGemma 4B (kaliteli)",
}


def make_factories(settings: Settings) -> dict[str, Callable[[], Translator]]:
    """Ayarları her oluşturma anında okuyan motor fabrikaları."""

    def opus() -> Translator:
        from .opus import OpusTranslator

        return OpusTranslator(
            device=settings.opus_device,
            threads=settings.opus_threads,
            beam_size=settings.opus_beam_size,
            target_prefix=settings.opus_target_prefix,
        )

    def gemma() -> Translator:
        from .gemma import GemmaTranslator

        return GemmaTranslator(
            base_url=settings.ollama_url,
            model=settings.gemma_model,
            cpu_only=settings.gemma_cpu_only,
            timeout=settings.gemma_timeout,
        )

    return {ENGINE_OPUS: opus, ENGINE_GEMMA: gemma}


__all__ = ["LABELS", "Translator", "TranslatorError", "make_factories"]
