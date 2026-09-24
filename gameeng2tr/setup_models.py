"""Modelleri indirip hazırlar (sadece bir kez, internet gerekir; sonrası tamamen çevrimdışı).

Kullanım:
    python -m gameeng2tr.setup_models            # ikisi birden
    python -m gameeng2tr.setup_models --opus     # sadece Opus-MT
    python -m gameeng2tr.setup_models --gemma    # sadece TranslateGemma (Ollama)
    python -m gameeng2tr.setup_models --test     # iki motoru da dener
"""

from __future__ import annotations

import argparse
import importlib.util
import shutil
import subprocess
import sys
import time

from . import paths
from .config import Settings

TORCH_CPU_INDEX = "https://download.pytorch.org/whl/cpu"


def _pip(*args: str) -> None:
    subprocess.check_call([sys.executable, "-m", "pip", "install", *args])


def setup_opus(force: bool = False) -> bool:
    out = paths.opus_model_dir()
    if (out / "model.bin").exists() and (out / "source.spm").exists() and not force:
        print(f"[Opus-MT] Model zaten hazır: {out}")
        return True

    print("[Opus-MT] Dönüştürme araçları kontrol ediliyor (torch + transformers, sadece kurulumda gerekir)...")
    if importlib.util.find_spec("torch") is None:
        _pip("torch", "--index-url", TORCH_CPU_INDEX)
    if importlib.util.find_spec("transformers") is None:
        _pip("transformers>=4.40", "sentencepiece", "sacremoses")

    from ctranslate2.converters import TransformersConverter

    print(f"[Opus-MT] {paths.OPUS_MODEL_ID} indiriliyor ve CTranslate2 INT8 biçimine dönüştürülüyor...")
    start = time.time()
    converter = TransformersConverter(paths.OPUS_MODEL_ID, copy_files=["source.spm", "target.spm"])
    converter.convert(str(out), quantization="int8", force=True)
    print(f"[Opus-MT] Tamam ({time.time() - start:.0f} sn): {out}")
    return True


def find_ollama() -> str | None:
    exe = shutil.which("ollama")
    if exe:
        return exe
    if sys.platform == "win32":
        import os
        from pathlib import Path

        candidate = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe"
        if candidate.exists():
            return str(candidate)
    return None


def setup_gemma(model: str) -> bool:
    exe = find_ollama()
    if not exe:
        print(
            "[Gemma] Ollama bulunamadı.\n"
            "        1) https://ollama.com/download adresinden Windows için Ollama'yı kurun\n"
            "           (veya: winget install Ollama.Ollama)\n"
            "        2) Bu betiği tekrar çalıştırın."
        )
        return False
    print(f"[Gemma] '{model}' indiriliyor (~3,3 GB, bir kez)...")
    try:
        subprocess.check_call([exe, "pull", model])
    except subprocess.CalledProcessError as exc:
        print(f"[Gemma] İndirme başarısız: {exc}. Ollama çalışıyor mu? (Başlat menüsünden Ollama'yı açın)")
        return False
    print("[Gemma] Tamam.")
    return True


def run_test(settings: Settings) -> None:
    from .translate import make_factories

    sample = "You shouldn't have come back here, Foundling. The Shell remembers what you have forgotten."
    print(f"\nEN: {sample}")
    for name, factory in make_factories(settings).items():
        translator = factory()
        try:
            translator.load()
            start = time.perf_counter()
            result = translator.translate(sample)
            print(f"[{name}] {result}  ({(time.perf_counter() - start) * 1000:.0f} ms)")
        except Exception as exc:
            print(f"[{name}] HATA: {exc}")
        finally:
            translator.unload()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="gameeng2tr model kurulumu")
    parser.add_argument("--opus", action="store_true", help="Opus-MT modelini hazırla")
    parser.add_argument("--gemma", action="store_true", help="TranslateGemma'yı Ollama ile indir")
    parser.add_argument("--test", action="store_true", help="Motorları dene")
    parser.add_argument("--force", action="store_true", help="Opus modelini yeniden dönüştür")
    args = parser.parse_args(argv)

    settings = Settings.load()
    do_all = not (args.opus or args.gemma or args.test)
    ok = True
    if args.opus or do_all:
        ok &= setup_opus(args.force)
    if args.gemma or do_all:
        ok &= setup_gemma(settings.gemma_model)
    if args.test or do_all:
        run_test(settings)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
