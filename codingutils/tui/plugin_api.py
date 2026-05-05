from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional, Protocol

from textual.app import App
from textual.widget import Widget


@dataclass(frozen=True, slots=True)
class PluginMeta:
    id: str
    name: str
    version: str = ""
    description: str = ""


@dataclass(frozen=True, slots=True)
class PluginSpec:
    meta: PluginMeta
    path: Path
    module_name: str
    create_ui: Callable[["ModuleContext"], Widget]


class SupportsWrite(Protocol):
    def write(self, s: str) -> int: ...
    def flush(self) -> None: ...


@dataclass(slots=True)
class RunSession:
    """Общий объект сессии запуска: доступен и worker-потоку, и UI."""
    run_id: str
    plugin_id: str
    cancelled: "threading.Event"
    hub: "OutputHub"

    def stream(self, name: str) -> SupportsWrite:
        """File-like sink: писать можно из любого потока."""
        return self.hub.make_sink(self.run_id, name)

    def bind(self, name: str, consumer: Callable[[str], None]) -> None:
        """UI thread: подписать consumer на поток name."""
        self.hub.subscribe(self.run_id, name, consumer)


@dataclass(slots=True)
class RunHandle:
    run_id: str
    plugin_id: str
    session: RunSession
    thread: Optional["threading.Thread"] = None
    popen: Any = None  # subprocess.Popen | None
    status: str = "running"  # running|done|failed|cancelled|stopping
    exit_code: Optional[int] = None
    error: Optional[str] = None


@dataclass(slots=True)
class ModuleContext:
    app: App
    plugin: PluginSpec
    tasks: "TaskManager"
    hub: "OutputHub"

    def open_command_line(self) -> None:
        # app должен иметь метод toggle_command_line()
        if hasattr(self.app, "toggle_command_line"):
            self.app.toggle_command_line()  # type: ignore[attr-defined]
