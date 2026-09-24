from __future__ import annotations

from abc import ABC, abstractmethod


class TranslatorError(RuntimeError):
    pass


class Translator(ABC):
    name = "translator"
    label = "Çevirmen"

    @abstractmethod
    def load(self) -> None:
        """Modeli belleğe yükler (uzun sürebilir, arka plan iş parçacığında çağrılır)."""

    @abstractmethod
    def translate(self, text: str) -> str:
        """Tek bir altyazıyı İngilizceden Türkçeye çevirir."""

    def unload(self) -> None:
        """Modeli bellekten/VRAM'den çıkarır."""

    @property
    def loaded(self) -> bool:
        return True
