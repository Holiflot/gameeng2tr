"""Google TranslateGemma 4B, yerel Ollama sunucusu üzerinden (tamamen çevrimdışı)."""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

from .base import Translator, TranslatorError

log = logging.getLogger(__name__)

# TranslateGemma model kartındaki resmi istem biçimi (metinden önce iki boş satır).
PROMPT_TEMPLATE = (
    "You are a professional English (en) to Turkish (tr) translator. Your goal is to accurately "
    "convey the meaning and nuances of the original English text while adhering to Turkish grammar, "
    "vocabulary, and cultural sensitivities. Produce only the Turkish translation, without any "
    "additional explanations or commentary. Please translate the following English text into "
    "Turkish:\n\n\n{text}"
)

OLLAMA_HINT = (
    "Ollama'ya bağlanılamadı. Ollama'yı kurun (https://ollama.com/download) ve "
    "'ollama pull {model}' komutunu bir kez çalıştırın."
)


def build_prompt(text: str) -> str:
    return PROMPT_TEMPLATE.format(text=text)


def clean_output(source: str, output: str) -> str:
    text = output.strip()
    # Olası düşünme/etiket artıkları
    text = re.sub(r"<[^>]{1,20}>", "", text).strip()
    for prefix in ("Turkish:", "Türkçe:", "Translation:", "Çeviri:"):
        if text.startswith(prefix):
            text = text[len(prefix):].strip()
    # Kaynakta tırnak yoksa modelin eklediği dış tırnakları kaldır.
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'" and source[:1] not in "\"'":
        text = text[1:-1].strip()
    # Tek satırlık altyazı için model ek açıklama paragrafı yazdıysa ilk paragrafı al.
    if "\n\n" in text and "\n" not in source:
        text = text.split("\n\n", 1)[0].strip()
    return re.sub(r"\s*\n\s*", " ", text)


class GemmaTranslator(Translator):
    name = "gemma"
    label = "TranslateGemma 4B (kaliteli)"

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11434",
        model: str = "translategemma:4b",
        cpu_only: bool = False,
        timeout: float = 30.0,
        keep_alive: str = "30m",
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.cpu_only = cpu_only
        self.timeout = timeout
        self.keep_alive = keep_alive
        self._loaded = False
        self._server_process: subprocess.Popen | None = None

    @property
    def loaded(self) -> bool:
        return self._loaded

    # --- HTTP yardımcıları -------------------------------------------------
    def _request(self, path: str, payload: dict | None = None, timeout: float | None = None) -> dict:
        url = self.base_url + path
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout or self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
            raise TranslatorError(f"Ollama hata döndürdü ({exc.code}): {body[:300]}") from exc
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            raise TranslatorError(OLLAMA_HINT.format(model=self.model) + f" [{exc}]") from exc

    def _server_alive(self) -> bool:
        try:
            self._request("/api/version", timeout=2)
            return True
        except TranslatorError:
            return False

    def _try_start_server(self) -> None:
        exe = shutil.which("ollama")
        if not exe:
            return
        log.info("Ollama sunucusu başlatılıyor: %s", exe)
        flags = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW
        self._server_process = subprocess.Popen(
            [exe, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags
        )
        for _ in range(40):
            time.sleep(0.25)
            if self._server_alive():
                return

    def _options(self) -> dict:
        options = {"temperature": 0.0, "top_k": 1, "num_predict": 256, "num_ctx": 1024}
        if self.cpu_only:
            options["num_gpu"] = 0
        return options

    def _ensure_model_pulled(self) -> None:
        tags = self._request("/api/tags", timeout=5).get("models", [])
        names = {m.get("name", "") for m in tags} | {m.get("model", "") for m in tags}
        wanted = self.model if ":" in self.model else self.model + ":latest"
        if wanted not in names:
            raise TranslatorError(
                f"'{self.model}' modeli Ollama'da yok. Komut satırında 'ollama pull {self.model}' çalıştırın "
                "(veya kurulum.bat)."
            )

    # --- Translator arayüzü ------------------------------------------------
    def load(self) -> None:
        if not self._server_alive():
            self._try_start_server()
            if not self._server_alive():
                raise TranslatorError(OLLAMA_HINT.format(model=self.model))
        self._ensure_model_pulled()
        # Isınma: modeli belleğe yükler ki ilk altyazı beklemesin.
        self._chat("Hello.", timeout=max(self.timeout, 120))
        self._loaded = True
        log.info("TranslateGemma hazır (%s, cpu_only=%s)", self.model, self.cpu_only)

    def unload(self) -> None:
        if not self._loaded:
            return
        try:
            self._request("/api/generate", {"model": self.model, "keep_alive": 0}, timeout=5)
            log.info("TranslateGemma bellekten çıkarıldı")
        except TranslatorError as exc:
            log.warning("TranslateGemma çıkarılamadı: %s", exc)
        self._loaded = False

    def _chat(self, text: str, timeout: float | None = None) -> str:
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": build_prompt(text)}],
            "stream": False,
            "keep_alive": self.keep_alive,
            "options": self._options(),
        }
        response = self._request("/api/chat", payload, timeout=timeout)
        return response.get("message", {}).get("content", "")

    def translate(self, text: str) -> str:
        if not self._loaded:
            self.load()
        return clean_output(text, self._chat(text))

    def shutdown(self) -> None:
        self.unload()
        if self._server_process is not None:
            self._server_process.terminate()
            self._server_process = None
