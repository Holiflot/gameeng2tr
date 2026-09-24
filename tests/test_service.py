import threading
import time

from gameeng2tr.translate.base import Translator, TranslatorError
from gameeng2tr.translate.glossary import Glossary
from gameeng2tr.translate.service import STATE_ERROR, STATE_IDLE, STATE_READY, TranslationService


class FakeTranslator(Translator):
    def __init__(self, name, delay=0.0, fail_load=False, log=None):
        self.name = name
        self.delay = delay
        self.fail_load = fail_load
        self._loaded = False
        self.calls = []
        self.log = log if log is not None else []

    @property
    def loaded(self):
        return self._loaded

    def load(self):
        self.log.append(("load", self.name))
        if self.fail_load:
            raise TranslatorError(f"{self.name} yok")
        self._loaded = True

    def unload(self):
        self.log.append(("unload", self.name))
        self._loaded = False

    def translate(self, text):
        self.calls.append(text)
        time.sleep(self.delay)
        return f"[{self.name}] {text}"


class Collector:
    def __init__(self):
        self.results = []
        self.states = []
        self.errors = []
        self.event = threading.Event()

    def on_result(self, r):
        self.results.append(r)
        self.event.set()

    def wait(self, n=1, timeout=3):
        end = time.time() + timeout
        while len(self.results) < n and time.time() < end:
            time.sleep(0.01)
        return len(self.results) >= n


def make_service(engines, engine="opus", **kw):
    col = Collector()
    svc = TranslationService(
        {name: (lambda t=t: t) for name, t in engines.items()},
        engine,
        on_result=col.on_result,
        on_state=lambda *a: col.states.append(a),
        on_error=col.errors.append,
        **kw,
    )
    return svc, col


def test_translates_and_caches():
    opus = FakeTranslator("opus")
    svc, col = make_service({"opus": opus})
    svc.start()
    try:
        svc.submit(1, "Hello there.")
        assert col.wait(1)
        svc.submit(2, "Hello there.")
        assert col.wait(2)
    finally:
        svc.stop()
    assert [r.text for r in col.results] == ["[opus] Hello there.", "[opus] Hello there."]
    assert col.results[1].cached
    assert opus.calls == ["Hello there."]
    assert svc.state("opus") == STATE_READY


def test_speaker_name_is_kept_and_glossary_applied():
    opus = FakeTranslator("opus")
    svc, col = make_service({"opus": opus}, glossary=Glossary({"Foundiing": "Foundling"}, {"[opus]": "<o>"}))
    svc.start()
    try:
        svc.submit(1, "Tiel: Welcome, Foundiing.")
        assert col.wait(1)
    finally:
        svc.stop()
    assert opus.calls == ["Welcome, Foundling."]
    assert col.results[0].text == "Tiel: <o> Welcome, Foundling."


def test_only_latest_pending_job_is_translated():
    slow = FakeTranslator("opus", delay=0.2)
    svc, col = make_service({"opus": slow})
    svc.start()
    try:
        svc.submit(1, "one")
        time.sleep(0.05)  # "one" çevriliyor
        svc.submit(2, "two")
        svc.submit(3, "three")
        assert col.wait(2)
        time.sleep(0.3)
    finally:
        svc.stop()
    assert [r.seq for r in col.results] == [1, 3]


def test_cancel_drops_in_flight_result():
    slow = FakeTranslator("opus", delay=0.2)
    svc, col = make_service({"opus": slow})
    svc.start()
    try:
        svc.submit(1, "one")
        time.sleep(0.05)
        svc.cancel_live(1)
        time.sleep(0.4)
    finally:
        svc.stop()
    assert col.results == []


def test_switch_engine_retranslates_current_and_unloads_gemma():
    log = []
    opus = FakeTranslator("opus", log=log)
    gemma = FakeTranslator("gemma", log=log)
    svc, col = make_service({"opus": opus, "gemma": gemma})
    svc.start()
    try:
        svc.submit(1, "Stay a while.")
        assert col.wait(1)
        svc.set_engine("gemma")
        assert col.wait(2)
        svc.set_engine("opus")
        time.sleep(0.2)
        assert col.wait(3)
    finally:
        svc.stop()
    assert [r.engine for r in col.results] == ["opus", "gemma", "opus"]
    assert col.results[1].text == "[gemma] Stay a while."
    assert all(r.seq == 1 for r in col.results)
    # Opus bellekte kalır, Gemma Opus'a geçince çıkarılır.
    assert ("unload", "gemma") in log
    assert log.count(("load", "opus")) == 1
    assert svc.state("gemma") == STATE_IDLE


def test_failed_engine_reports_error_and_retries_on_reselect():
    gemma = FakeTranslator("gemma", fail_load=True)
    svc, col = make_service({"opus": FakeTranslator("opus"), "gemma": gemma}, engine="gemma")
    svc.start()
    try:
        svc.submit(1, "Hello")
        time.sleep(0.2)
        assert col.results == []
        assert svc.state("gemma") == STATE_ERROR
        assert col.errors and "gemma yok" in col.errors[0]
        loads = gemma.log.count(("load", "gemma"))
        svc.submit(2, "Again")  # otomatik tekrar denenmez
        time.sleep(0.2)
        assert gemma.log.count(("load", "gemma")) == loads
        gemma.fail_load = False
        svc.set_engine("gemma")  # kullanıcı yeniden seçti
        svc.submit(3, "Now it works")
        assert col.wait(1)
    finally:
        svc.stop()
    assert col.results[-1].text == "[gemma] Now it works"


def test_reconfigure_recreates_engine():
    created = []

    def factory():
        t = FakeTranslator("opus")
        created.append(t)
        return t

    col = Collector()
    svc = TranslationService({"opus": factory}, "opus", on_result=col.on_result)
    svc.start()
    try:
        svc.submit(1, "a")
        assert col.wait(1)
        svc.reconfigure("opus")
        svc.submit(2, "b")
        assert col.wait(2)
    finally:
        svc.stop()
    assert len(created) == 2
    assert created[0].loaded is False
