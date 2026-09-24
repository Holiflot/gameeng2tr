"""Uygulama giriş noktası."""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

from . import __version__, paths
from .config import Settings


def setup_logging() -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    try:
        handlers.append(RotatingFileHandler(paths.log_path(), maxBytes=2_000_000, backupCount=2, encoding="utf-8"))
    except OSError:
        pass
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
    )


def main() -> int:
    setup_logging()
    log = logging.getLogger("gameeng2tr")
    log.info("gameeng2tr %s başlıyor", __version__)

    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    from .controller import Controller
    from .ui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("gameeng2tr")
    app.setQuitOnLastWindowClosed(False)

    settings = Settings.load()
    controller = Controller(settings)
    window = MainWindow(controller)
    # Overlay pencereleri açık kalsa da ana pencere kapanınca uygulama kapanır.
    window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
    window.destroyed.connect(app.quit)
    app.aboutToQuit.connect(controller.shutdown)
    window.show()
    controller.boot()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
