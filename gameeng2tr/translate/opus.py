"""Helsinki-NLP/opus-mt-tc-big-en-tr, CTranslate2 (INT8) ile. Hızlı, GPU'suz çalışır."""

from __future__ import annotations

import logging
from pathlib import Path

from .. import paths
from ..textproc import split_sentences
from .base import Translator, TranslatorError

log = logging.getLogger(__name__)

SETUP_HINT = "Opus-MT modeli bulunamadı. Önce 'kurulum.bat' veya 'python -m gameeng2tr.setup_models --opus' çalıştırın."


class OpusTranslator(Translator):
    name = "opus"
    label = "Opus-MT (hızlı)"

    def __init__(
        self,
        model_dir: Path | None = None,
        device: str = "cpu",
        threads: int = 4,
        beam_size: int = 2,
        target_prefix: str = "",
    ):
        self.model_dir = Path(model_dir or paths.opus_model_dir())
        self.device = device
        self.threads = threads
        self.beam_size = beam_size
        self.target_prefix = target_prefix.strip()
        self._translator = None
        self._sp_source = None
        self._sp_target = None

    @property
    def loaded(self) -> bool:
        return self._translator is not None

    def load(self) -> None:
        if self._translator is not None:
            return
        if not (self.model_dir / "model.bin").exists():
            raise TranslatorError(SETUP_HINT)
        try:
            import ctranslate2
            import sentencepiece as spm
        except ImportError as exc:
            raise TranslatorError("ctranslate2 / sentencepiece paketleri kurulu değil") from exc

        source_spm = self.model_dir / "source.spm"
        target_spm = self.model_dir / "target.spm"
        if not source_spm.exists() or not target_spm.exists():
            raise TranslatorError(f"source.spm / target.spm eksik: {self.model_dir}. {SETUP_HINT}")
        self._sp_source = spm.SentencePieceProcessor(model_file=str(source_spm))
        self._sp_target = spm.SentencePieceProcessor(model_file=str(target_spm))

        device = self.device
        if device == "cuda" and ctranslate2.get_cuda_device_count() == 0:
            log.warning("CUDA bulunamadı, Opus-MT CPU'da çalışacak")
            device = "cpu"
        compute_type = "int8_float16" if device == "cuda" else "int8"
        self._translator = ctranslate2.Translator(
            str(self.model_dir),
            device=device,
            compute_type=compute_type,
            inter_threads=1,
            intra_threads=self.threads if device == "cpu" else 0,
        )
        log.info("Opus-MT yüklendi (%s, %s)", device, compute_type)

    def unload(self) -> None:
        self._translator = None

    def _encode(self, sentence: str) -> list[str]:
        tokens = self._sp_source.encode(sentence, out_type=str)
        return tokens + ["</s>"]

    def translate(self, text: str) -> str:
        if self._translator is None:
            self.load()
        sentences = split_sentences(text) or [text]
        batch = [self._encode(s) for s in sentences]
        prefix = [[self.target_prefix]] * len(batch) if self.target_prefix else None
        results = self._translator.translate_batch(
            batch,
            target_prefix=prefix,
            beam_size=self.beam_size,
            max_decoding_length=256,
            repetition_penalty=1.1,
        )
        out = []
        for result in results:
            tokens = [t for t in result.hypotheses[0] if t not in ("</s>", "<pad>") and t != self.target_prefix]
            out.append(self._sp_target.decode(tokens).strip())
        return " ".join(s for s in out if s)
