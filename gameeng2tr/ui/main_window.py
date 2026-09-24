"""Kontrol penceresi."""

from __future__ import annotations

import os
import subprocess
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSlider,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .. import __version__, paths
from ..config import ENGINE_GEMMA, ENGINE_OPUS
from ..controller import STATE_TEXT, Controller
from ..ocr import LABELS as OCR_LABELS
from ..translate import LABELS as ENGINE_LABELS
from ..translate.service import STATE_ERROR, TranslationResult

POSITION_LABELS = {
    "over": "İngilizce altyazının üstüne yaz (gizler)",
    "above": "Altyazının yukarısında göster",
    "below": "Altyazının aşağısında göster",
}


def open_path(path) -> None:
    path = str(path)
    if sys.platform == "win32":
        os.startfile(path)  # noqa: S606
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


class MainWindow(QMainWindow):
    def __init__(self, controller: Controller):
        super().__init__()
        self.c = controller
        self.s = controller.settings
        self.setWindowTitle(f"gameeng2tr {__version__} • Oyun Altyazı Çevirmeni (EN → TR)")
        self.resize(620, 720)

        tabs = QTabWidget()
        tabs.addTab(self._build_main_tab(), "Ana")
        tabs.addTab(self._build_settings_tab(), "Ayarlar")
        tabs.addTab(self._build_history_tab(), "Geçmiş")
        self.setCentralWidget(tabs)

        c = controller
        c.running_changed.connect(self._on_running_changed)
        c.status.connect(self.status_label.setText)
        c.error.connect(self._on_error)
        c.metrics.connect(self._on_metrics)
        c.ocr_ready.connect(lambda label: self.ocr_label.setText(f"OCR: {label}"))
        c.engine_state.connect(self._on_engine_state)
        c.engine_changed.connect(self._sync_engine_radio)
        c.translation_result.connect(self._on_translation)
        c.region_changed.connect(self._update_region_label)
        c.overlay_hidden_changed.connect(self._sync_overlay_hidden)

        for name in (ENGINE_OPUS, ENGINE_GEMMA):
            self._on_engine_state(name, c.service.state(name), "")
        self._update_region_label()

    # ------------------------------------------------------------------ Ana
    def _build_main_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        self.start_button = QPushButton()
        self.start_button.setMinimumHeight(48)
        font = self.start_button.font()
        font.setPointSize(font.pointSize() + 3)
        font.setBold(True)
        self.start_button.setFont(font)
        self.start_button.clicked.connect(self.c.toggle)
        layout.addWidget(self.start_button)

        self.status_label = QLabel("Hazır. Oyunu açın ve Başlat'a basın.")
        self.status_label.setWordWrap(True)
        self.ocr_label = QLabel("OCR: -")
        self.metrics_label = QLabel("OCR: - ms • Çeviri: - ms")
        layout.addWidget(self.status_label)
        row = QHBoxLayout()
        row.addWidget(self.ocr_label)
        row.addStretch()
        row.addWidget(self.metrics_label)
        layout.addLayout(row)

        # Motor seçimi
        engine_box = QGroupBox("Çeviri motoru")
        engine_layout = QVBoxLayout(engine_box)
        self.engine_group = QButtonGroup(self)
        self.engine_radios: dict[str, QRadioButton] = {}
        self.engine_state_labels: dict[str, QLabel] = {}
        descriptions = {
            ENGINE_OPUS: "Çok hızlı (~0,1 sn), işlemcide çalışır, oyunun FPS'ini etkilemez.",
            ENGINE_GEMMA: "Daha doğal Türkçe, Ollama üzerinden. GPU'da ~3,5 GB VRAM kullanır (AMD kartlarda Vulkan ile).",
        }
        for name in (ENGINE_OPUS, ENGINE_GEMMA):
            radio = QRadioButton(ENGINE_LABELS[name])
            radio.setChecked(self.s.engine == name)
            radio.toggled.connect(lambda checked, n=name: checked and self.c.set_engine(n))
            self.engine_group.addButton(radio)
            state = QLabel()
            head = QHBoxLayout()
            head.addWidget(radio)
            head.addStretch()
            head.addWidget(state)
            engine_layout.addLayout(head)
            desc = QLabel(descriptions[name])
            desc.setStyleSheet("color: gray; margin-left: 22px;")
            desc.setWordWrap(True)
            engine_layout.addWidget(desc)
            self.engine_radios[name] = radio
            self.engine_state_labels[name] = state
        self.engine_error = QLabel()
        self.engine_error.setWordWrap(True)
        self.engine_error.setStyleSheet("color: #d32f2f;")
        self.engine_error.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.engine_error.hide()
        engine_layout.addWidget(self.engine_error)
        layout.addWidget(engine_box)

        # Bölge
        region_box = QGroupBox("Altyazı bölgesi")
        region_layout = QHBoxLayout(region_box)
        self.region_label = QLabel()
        select = QPushButton("Bölge seç...")
        select.clicked.connect(self.c.select_region)
        reset = QPushButton("Varsayılan")
        reset.clicked.connect(lambda: self.c.set_region([0.12, 0.80, 0.88, 0.97]))
        region_layout.addWidget(self.region_label, 1)
        region_layout.addWidget(select)
        region_layout.addWidget(reset)
        layout.addWidget(region_box)

        # Anlık altyazı
        live_box = QGroupBox("Son altyazı")
        live_layout = QVBoxLayout(live_box)
        self.live_en = QLabel("-")
        self.live_en.setWordWrap(True)
        self.live_en.setStyleSheet("color: gray;")
        self.live_tr = QLabel("-")
        self.live_tr.setWordWrap(True)
        bold = QFont(self.live_tr.font())
        bold.setBold(True)
        self.live_tr.setFont(bold)
        live_layout.addWidget(self.live_en)
        live_layout.addWidget(self.live_tr)
        layout.addWidget(live_box)

        # Deneme
        test_box = QGroupBox("Deneme çevirisi")
        test_layout = QVBoxLayout(test_box)
        test_row = QHBoxLayout()
        self.test_input = QLineEdit("You shouldn't have come back here, Foundling.")
        test_button = QPushButton("Çevir")
        test_button.clicked.connect(self._translate_test)
        self.test_input.returnPressed.connect(self._translate_test)
        test_row.addWidget(self.test_input, 1)
        test_row.addWidget(test_button)
        self.test_output = QLabel("")
        self.test_output.setWordWrap(True)
        self.test_output.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        test_layout.addLayout(test_row)
        test_layout.addWidget(self.test_output)
        layout.addWidget(test_box)

        s = self.s
        hotkeys = QLabel(
            f"<b>Oyun içi kısayollar</b><br>"
            f"{s.hotkey_toggle.upper()}: başlat / durdur &nbsp;•&nbsp; "
            f"{s.hotkey_engine.upper()}: motor değiştir<br>"
            f"{s.hotkey_overlay.upper()}: çeviriyi gizle / göster &nbsp;•&nbsp; "
            f"{s.hotkey_region.upper()}: bölge seç"
        )
        hotkeys.setWordWrap(True)
        layout.addWidget(hotkeys)
        layout.addStretch()
        self._on_running_changed(False)
        return page

    # -------------------------------------------------------------- Ayarlar
    def _build_settings_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        s = self.s

        # Görünüm
        view_box = QGroupBox("Görünüm")
        form = QFormLayout(view_box)
        self.position_combo = QComboBox()
        for key, label in POSITION_LABELS.items():
            self.position_combo.addItem(label, key)
        self.position_combo.setCurrentIndex(list(POSITION_LABELS).index(s.overlay_position))
        self.position_combo.currentIndexChanged.connect(lambda: self._set("overlay_position", self.position_combo.currentData(), refresh=True))
        form.addRow("Konum", self.position_combo)

        font_size = QSpinBox()
        font_size.setRange(12, 96)
        font_size.setValue(s.font_size)
        font_size.valueChanged.connect(lambda v: self._set("font_size", v, refresh=True))
        form.addRow("Yazı boyutu (px)", font_size)

        opacity = QSlider(Qt.Orientation.Horizontal)
        opacity.setRange(0, 100)
        opacity.setValue(int(s.background_opacity * 100))
        opacity.valueChanged.connect(lambda v: self._set("background_opacity", v / 100, refresh=True))
        form.addRow("Arka plan koyuluğu", opacity)

        badge = QCheckBox("Çevirinin köşesinde motor adını göster")
        badge.setChecked(s.show_engine_badge)
        badge.toggled.connect(lambda v: self._set("show_engine_badge", v, refresh=True))
        form.addRow(badge)

        self.hide_overlay = QCheckBox("Çeviriyi gizle")
        self.hide_overlay.setChecked(False)
        self.hide_overlay.toggled.connect(self._on_hide_toggled)
        form.addRow(self.hide_overlay)

        monitor = QComboBox()
        for i, screen in enumerate(QGuiApplication.screens()):
            geo = screen.geometry()
            monitor.addItem(f"{i + 1}: {screen.name()} ({geo.width()}x{geo.height()})", i)
        monitor.setCurrentIndex(min(s.monitor, monitor.count() - 1))
        monitor.currentIndexChanged.connect(lambda: self._set("monitor", monitor.currentData(), refresh=True, reset=True))
        form.addRow("Monitör", monitor)
        layout.addWidget(view_box)

        # OCR
        ocr_box = QGroupBox("Metin tanıma (OCR)")
        form = QFormLayout(ocr_box)
        ocr_combo = QComboBox()
        for key, label in OCR_LABELS.items():
            ocr_combo.addItem(label, key)
        ocr_combo.setCurrentIndex(list(OCR_LABELS).index(s.ocr_backend))
        ocr_combo.currentIndexChanged.connect(lambda: self._set("ocr_backend", ocr_combo.currentData(), reset=True))
        form.addRow("OCR motoru", ocr_combo)

        fps = QDoubleSpinBox()
        fps.setRange(1, 20)
        fps.setDecimals(0)
        fps.setValue(s.capture_fps)
        fps.valueChanged.connect(lambda v: self._set("capture_fps", float(v)))
        form.addRow("Tarama sıklığı (kare/sn)", fps)

        stable = QSpinBox()
        stable.setRange(1, 6)
        stable.setValue(s.stable_frames)
        stable.valueChanged.connect(lambda v: self._set("stable_frames", v, reset=True))
        form.addRow("Sabit kalma (kare)", stable)

        contrast = QCheckBox("Yüksek kontrast (beyaz altyazıyı arka plandan ayır)")
        contrast.setChecked(s.high_contrast)
        contrast.toggled.connect(lambda v: self._set("high_contrast", v, reset=True))
        form.addRow(contrast)

        speaker = QCheckBox("\"İsim: cümle\" biçiminde konuşmacı adını çevirme")
        speaker.setChecked(s.split_speaker)
        speaker.toggled.connect(self._on_speaker_toggled)
        form.addRow(speaker)
        layout.addWidget(ocr_box)

        # Motor ayarları
        engine_box = QGroupBox("Motor ayarları")
        form = QFormLayout(engine_box)
        opus_device = QComboBox()
        opus_device.addItem("CPU (önerilen, GPU oyuna kalır)", "cpu")
        opus_device.addItem("NVIDIA GPU (CUDA)", "cuda")
        opus_device.setCurrentIndex(0 if s.opus_device == "cpu" else 1)
        opus_device.currentIndexChanged.connect(lambda: self._set_engine_opt("opus_device", opus_device.currentData(), ENGINE_OPUS))
        form.addRow("Opus-MT cihazı", opus_device)

        gemma_model = QLineEdit(s.gemma_model)
        gemma_model.editingFinished.connect(lambda: self._set_engine_opt("gemma_model", gemma_model.text().strip() or "translategemma:4b", ENGINE_GEMMA))
        form.addRow("Gemma modeli (Ollama)", gemma_model)

        gemma_cpu = QCheckBox("Gemma'yı sadece CPU'da çalıştır (yavaş ama VRAM kullanmaz)")
        gemma_cpu.setChecked(s.gemma_cpu_only)
        gemma_cpu.toggled.connect(lambda v: self._set_engine_opt("gemma_cpu_only", v, ENGINE_GEMMA))
        form.addRow(gemma_cpu)

        keep = QCheckBox("Opus'a geçince Gemma'yı bellekte tut (geri geçiş anında olur)")
        keep.setChecked(s.gemma_keep_loaded)
        keep.toggled.connect(lambda v: self._set("gemma_keep_loaded", v))
        form.addRow(keep)
        layout.addWidget(engine_box)

        autostart = QCheckBox("Uygulama açılınca çeviriyi otomatik başlat")
        autostart.setChecked(s.autostart)
        autostart.toggled.connect(lambda v: self._set("autostart", v))
        layout.addWidget(autostart)

        buttons = QHBoxLayout()
        glossary = QPushButton("Sözlüğü aç")
        glossary.clicked.connect(lambda: open_path(paths.glossary_path()))
        reload_glossary = QPushButton("Sözlüğü yeniden yükle")
        reload_glossary.clicked.connect(self.c.reload_glossary)
        data = QPushButton("Veri klasörünü aç")
        data.clicked.connect(lambda: open_path(paths.data_dir()))
        buttons.addWidget(glossary)
        buttons.addWidget(reload_glossary)
        buttons.addWidget(data)
        layout.addLayout(buttons)
        layout.addStretch()
        return page

    # --------------------------------------------------------------- Geçmiş
    def _build_history_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.history = QListWidget()
        self.history.setWordWrap(True)
        self.history.setAlternatingRowColors(True)
        layout.addWidget(self.history)
        clear = QPushButton("Temizle")
        clear.clicked.connect(self.history.clear)
        layout.addWidget(clear, alignment=Qt.AlignmentFlag.AlignRight)
        return page

    # ------------------------------------------------------------ yardımcı
    def _set(self, key: str, value, refresh: bool = False, reset: bool = False) -> None:
        setattr(self.s, key, value)
        self.s.validate()
        self.c.save_later()
        if refresh:
            self.c.overlay.refresh()
        if reset:
            self.c.pipeline.reset()

    def _set_engine_opt(self, key: str, value, engine: str) -> None:
        if getattr(self.s, key) == value:
            return
        setattr(self.s, key, value)
        self.c.reconfigure_engine(engine)

    def _on_speaker_toggled(self, value: bool) -> None:
        self._set("split_speaker", value)
        self.c.service.split_speaker_names = value
        self.c.service.cache.clear()

    def _on_hide_toggled(self, hidden: bool) -> None:
        if hidden != self.c.overlay.user_hidden:
            self.c.set_overlay_hidden(hidden)

    def _sync_overlay_hidden(self, hidden: bool) -> None:
        self.hide_overlay.blockSignals(True)
        self.hide_overlay.setChecked(hidden)
        self.hide_overlay.blockSignals(False)

    def _update_region_label(self) -> None:
        l, t, r, b = self.s.region
        self.region_label.setText(f"Sol %{l * 100:.0f}, üst %{t * 100:.0f}, sağ %{r * 100:.0f}, alt %{b * 100:.0f}")

    def _on_running_changed(self, running: bool) -> None:
        self.start_button.setText("■  Durdur" if running else "▶  Başlat")

    def _on_error(self, message: str) -> None:
        self.status_label.setText(message)

    def _on_metrics(self, metrics: dict) -> None:
        text = metrics.get("ocr_text", "")
        if text:
            self.live_en.setText(text)
        self.metrics_label.setText(
            f"OCR: {metrics.get('ocr_ms', 0):.0f} ms • Çeviri: {self.c.last_translation_ms:.0f} ms"
        )

    def _on_engine_state(self, name: str, state: str, message: str) -> None:
        label = self.engine_state_labels[name]
        text = STATE_TEXT.get(state, state)
        if state == "ready" and message:
            text = f"{text} • {message}"
            if message.startswith("CPU:") or "+ CPU" in message:
                state = "loading"  # turuncu: çalışıyor ama beklenenden yavaş
        label.setText(text)
        label.setToolTip(message)
        color = {"ready": "#2e7d32", "loading": "#ef6c00", "error": "#d32f2f"}.get(state, "gray")
        label.setStyleSheet(f"color: {color}; font-weight: bold;")
        if name == self.s.engine:
            if state == STATE_ERROR and message:
                self.engine_error.setText(message)
                self.engine_error.show()
            elif state != STATE_ERROR:
                self.engine_error.hide()

    def _sync_engine_radio(self, name: str) -> None:
        radio = self.engine_radios[name]
        if not radio.isChecked():
            radio.blockSignals(True)
            radio.setChecked(True)
            radio.blockSignals(False)
        self.engine_error.hide()

    def _translate_test(self) -> None:
        text = self.test_input.text().strip()
        if text:
            self.test_output.setText("Çevriliyor...")
            self.c.translate_manual(text)

    def _on_translation(self, result: TranslationResult) -> None:
        engine = "Opus" if result.engine == ENGINE_OPUS else "Gemma"
        info = f"{engine}, {result.ms:.0f} ms{' (önbellek)' if result.cached else ''}"
        if result.tag == "manual":
            self.test_output.setText(f"{result.text}\n({info})")
            return
        self.live_en.setText(result.source)
        self.live_tr.setText(result.text)
        self.history.insertItem(0, f"{result.source}\n→ {result.text}   [{info}]")
        while self.history.count() > 300:
            self.history.takeItem(self.history.count() - 1)

    def closeEvent(self, event):
        if self.c.running:
            answer = QMessageBox.question(self, "Çıkış", "Çeviri çalışıyor. Uygulama kapatılsın mı?")
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        event.accept()
