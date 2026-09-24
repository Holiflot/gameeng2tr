import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from gameeng2tr.translate.base import TranslatorError
from gameeng2tr.translate.gemma import GemmaTranslator, build_prompt, clean_output


class FakeOllama(BaseHTTPRequestHandler):
    requests = []
    models = ["translategemma:4b"]
    reply = "Buraya geri dönmemeliydin, Foundling."
    vram_share = 1.0

    def log_message(self, *args):
        pass

    def _send(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        FakeOllama.requests.append(("GET", self.path, None))
        if self.path == "/api/version":
            self._send({"version": "0.12.0"})
        elif self.path == "/api/ps":
            size = 3_500_000_000
            self._send({"models": [{"name": "translategemma:4b", "model": "translategemma:4b",
                                    "size": size, "size_vram": int(size * FakeOllama.vram_share)}]})
        elif self.path == "/api/tags":
            self._send({"models": [{"name": m, "model": m} for m in FakeOllama.models]})
        else:
            self._send({"error": "not found"}, 404)

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeOllama.requests.append(("POST", self.path, payload))
        if self.path == "/api/chat":
            self._send({"message": {"role": "assistant", "content": FakeOllama.reply}, "done": True})
        elif self.path == "/api/generate":
            self._send({"done": True})
        else:
            self._send({"error": "not found"}, 404)


@pytest.fixture
def ollama():
    FakeOllama.requests = []
    FakeOllama.models = ["translategemma:4b"]
    FakeOllama.vram_share = 1.0
    server = HTTPServer(("127.0.0.1", 0), FakeOllama)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def test_prompt_matches_translategemma_format():
    prompt = build_prompt("Hello.")
    assert prompt.startswith("You are a professional English (en) to Turkish (tr) translator.")
    assert prompt.endswith("into Turkish:\n\n\nHello.")


def test_clean_output():
    assert clean_output("Hello.", '"Merhaba."') == "Merhaba."
    assert clean_output('"Hello."', '"Merhaba."') == '"Merhaba."'
    assert clean_output("Hello.", "Türkçe: Merhaba.") == "Merhaba."
    assert clean_output("Hello.", "Merhaba.\n\nNote: this is a greeting.") == "Merhaba."
    assert clean_output("Hello.", "<end_of_turn>Merhaba.") == "Merhaba."


def test_translate_via_ollama(ollama):
    g = GemmaTranslator(base_url=ollama, cpu_only=True)
    g.load()
    assert g.translate("You shouldn't have come back here, Foundling.") == "Buraya geri dönmemeliydin, Foundling."
    chats = [p for m, path, p in FakeOllama.requests if path == "/api/chat"]
    assert len(chats) == 2  # ısınma + çeviri
    last = chats[-1]
    assert last["model"] == "translategemma:4b"
    assert last["stream"] is False
    assert last["options"]["temperature"] == 0.0
    assert last["options"]["num_gpu"] == 0
    assert last["options"]["num_thread"] == 4
    assert last["options"]["num_ctx"] == 512
    assert last["messages"][0]["content"].endswith("Foundling.")
    g.unload()
    unload = [p for m, path, p in FakeOllama.requests if path == "/api/generate"][-1]
    assert unload == {"model": "translategemma:4b", "keep_alive": 0}
    assert not g.loaded


def test_missing_model_gives_pull_hint(ollama):
    FakeOllama.models = ["llama3:8b"]
    g = GemmaTranslator(base_url=ollama)
    with pytest.raises(TranslatorError, match="ollama pull translategemma:4b"):
        g.load()


def test_no_server_gives_install_hint(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    g = GemmaTranslator(base_url="http://127.0.0.1:9", timeout=1)
    with pytest.raises(TranslatorError, match="Ollama"):
        g.load()


@pytest.mark.parametrize(
    "share, cpu_only, expected",
    [
        (1.0, False, "GPU"),
        (0.0, True, "CPU"),
        (0.0, False, "CPU: GPU kullanılamadı"),
        (0.6, False, "GPU %60 + CPU"),
    ],
)
def test_placement_note(ollama, share, cpu_only, expected):
    FakeOllama.vram_share = share
    g = GemmaTranslator(base_url=ollama, cpu_only=cpu_only)
    g.load()
    assert g.note.startswith(expected)
    if not cpu_only:
        chat = [p for m, path, p in FakeOllama.requests if path == "/api/chat"][-1]
        assert "num_gpu" not in chat["options"] and "num_thread" not in chat["options"]
