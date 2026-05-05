from __future__ import annotations

import sys
import threading
import contextvars
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

from textual.app import App


_current_run_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("current_run_id", default=None)


class OutputHub:
    """
    Hub: связывает (run_id, stream_name) -> consumers (в UI потоке).
    emit() можно вызывать из worker потока.
    """

    def __init__(self, app: App) -> None:
        self.app = app
        self._lock = threading.Lock()
        self._subs: Dict[Tuple[str, str], List[Callable[[str], None]]] = {}

    def subscribe(self, run_id: str, stream: str, consumer: Callable[[str], None]) -> None:
        key = (run_id, stream)
        with self._lock:
            self._subs.setdefault(key, []).append(consumer)

    def emit(self, run_id: str, stream: str, text: str) -> None:
        # UI обновления только из UI thread
        self.app.call_from_thread(self._emit_ui, run_id, stream, text)

    def _emit_ui(self, run_id: str, stream: str, text: str) -> None:
        key = (run_id, stream)
        with self._lock:
            consumers = list(self._subs.get(key, []))
        for c in consumers:
            try:
                c(text)
            except Exception:
                # не валим приложение из-за ошибок consumer
                pass

    def make_sink(self, run_id: str, stream: str) -> "TextSink":
        return TextSink(self, run_id, stream)


@dataclass(slots=True)
class TextSink:
    hub: OutputHub
    run_id: str
    stream: str

    def write(self, s: str) -> int:
        if not s:
            return 0
        self.hub.emit(self.run_id, self.stream, s)
        return len(s)

    def flush(self) -> None:
        return


class StreamRouter:
    """
    Глобальный sys.stdout/sys.stderr, который маршрутизирует вывод в hub
    по contextvars(_current_run_id) для текущего потока.
    """

    def __init__(self, hub: OutputHub, stream_name: str, fallback) -> None:
        self.hub = hub
        self.stream_name = stream_name
        self.fallback = fallback

    def write(self, s: str) -> int:
        run_id = _current_run_id.get()
        if run_id:
            self.hub.emit(run_id, self.stream_name, s)
            return len(s)
        # если не в контексте run — пишем в fallback (обычно оригинальный stdout)
        try:
            return self.fallback.write(s)
        except Exception:
            return len(s)

    def flush(self) -> None:
        try:
            self.fallback.flush()
        except Exception:
            pass


class RunIOContext:
    """
    Контекст для worker-потока: устанавливает current_run_id,
    чтобы print()/logging/progress шли в нужный run.
    """

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self._token = None

    def __enter__(self):
        self._token = _current_run_id.set(self.run_id)
        return self

    def __exit__(self, exc_type, exc, tb):
        if self._token is not None:
            _current_run_id.reset(self._token)
        return False


def install_global_routers(app: App, hub: OutputHub) -> None:
    """Ставим глобальные sys.stdout/sys.stderr на роутеры."""
    sys.stdout = StreamRouter(hub, "stdout", fallback=sys.__stdout__)  # type: ignore[assignment]
    sys.stderr = StreamRouter(hub, "stderr", fallback=sys.__stderr__)  # type: ignore[assignment]
