
from __future__ import annotations

import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Optional, Type

from textual.widget import Widget


@dataclass(frozen=True)
class ToolMeta:
    """Метаданные инструмента, отображаемые в селекторе."""
    id: str
    label: str
    description: str = ""


class ToolPlugin(ABC):
    """
    Базовый класс плагина.

    Плагин:
    - хранит своё состояние;
    - сам строит панель с опциями;
    - умеет собрать CLI‑строку (превью);
    - умеет себя выполнить.
    """

    meta: ToolMeta

    def __init__(self, screen: "MainScreen") -> None: #noqa F821

        self.screen = screen



    @abstractmethod
    def create_options_panel(self) -> Widget:
        """
        Вернуть корневой виджет с опциями (вкладки, инпуты и т.п.).
        Этот виджет будет смонтирован внутри OptionsEditor.
        """
        raise NotImplementedError



    def build_cli_preview(self) -> str:
        """Собрать CLI‑строку на основе текущего состояния (по умолчанию только ID)."""
        return self.meta.id



    @abstractmethod
    async def run(self) -> None:
        """
        Выполнить инструмент с текущей конфигурацией.
        Плагин сам логирует ошибки и результат.
        """
        raise NotImplementedError



    def on_selected(self) -> None:
        """Вызывается, когда этот инструмент выбирают в селекторе."""
        pass

    def on_state_changed(self) -> None:
        """
        Плагин должен вызывать это при изменении своего состояния,
        чтобы обновить строку CLI‑превью.
        """
        if hasattr(self.screen, "update_cli_bar"):
            self.screen.update_cli_bar()


class ToolRegistry:
    """Реестр типов плагинов (по одному экземпляру на экран)."""

    def __init__(self) -> None:
        self._plugin_classes: Dict[str, Type[ToolPlugin]] = {}

    def register(self, plugin_cls: Type[ToolPlugin]) -> None:
        meta = getattr(plugin_cls, "meta", None)
        if meta is None or not isinstance(meta, ToolMeta):
            raise ValueError(f"{plugin_cls} must define class attribute 'meta: ToolMeta'")
        self._plugin_classes[meta.id] = plugin_cls

    def create_all(self, screen: "MainScreen") -> Dict[str, ToolPlugin]: #noqa F821
        """Создать экземпляр каждого плагина для конкретного экрана.

        Ошибки инициализации отдельных плагинов логируем в stderr,
        но не ломаем всё приложение.
        """
        plugins: Dict[str, ToolPlugin] = {}
        for pid, cls in self._plugin_classes.items():
            try:
                plugins[pid] = cls(screen)
            except Exception as e:
                print(f"[TUI] Failed to initialize plugin '{pid}': {e!r}", file=sys.stderr)
        return plugins

    def metas(self) -> List[ToolMeta]:
        """Список метаданных всех зарегистрированных плагинов."""
        return [cls.meta for cls in self._plugin_classes.values()]

    def get(self, tool_id: str) -> Optional[Type[ToolPlugin]]:
        return self._plugin_classes.get(tool_id)



tool_registry = ToolRegistry()
