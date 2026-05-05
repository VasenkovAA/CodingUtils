from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Deque, Optional

from textual.widgets import TextArea

from ..clipboard import copy_text


@dataclass(slots=True)
class ConsoleConfig:
    max_lines: int = 3000


class ConsoleView(TextArea):
    """
    Console backed by TextArea:
    - supports selection with mouse/keyboard inside TUI
    - F2 copies selection (or all if no selection)
    - Shift+F2 copies all
    - supports \\r (tqdm-like line updates)
    """

    can_focus = True

    BINDINGS = [
        ("f2", "copy", "Copy"),
        ("shift+f2", "copy_all", "Copy all"),
        ("ctrl+l", "clear", "Clear"),
    ]

    def __init__(self, *, config: Optional[ConsoleConfig] = None, id: str | None = None) -> None:
        super().__init__("", id=id)
        self.config = config or ConsoleConfig()

        # TextArea settings
        self.read_only = True
        self.show_line_numbers = False
        self.wrap = True  # мягкий перенос
        # косметика: не показываем caret
        self.styles.caret_color = "transparent"

        self._lines: Deque[str] = deque()
        self._partial: str = ""

    def _get_text(self) -> str:
        content = "\n".join(self._lines)
        if self._partial:
            content = content + ("\n" if content else "") + self._partial
        return content

    def clear(self) -> None:
        self._lines.clear()
        self._partial = ""
        self.text = ""

    def action_clear(self) -> None:
        self.clear()

    def _get_selected_text(self) -> str:
        # Textual TextArea API может отличаться — делаем аккуратно
        try:
            # в некоторых версиях есть свойство
            selected = getattr(self, "selected_text", "")
            if selected:
                return str(selected)
        except Exception:
            pass

        try:
            # в некоторых версиях есть метод
            m = getattr(self, "get_selected_text", None)
            if callable(m):
                selected = m()
                if selected:
                    return str(selected)
        except Exception:
            pass

        return ""

    def action_copy(self) -> None:
        selected = self._get_selected_text()
        text = selected if selected else self._get_text()
        if not text:
            return
        ok, method = copy_text(self.app, text)
        try:
            self.app.notify(f"Copied ({method})" if ok else f"Copy failed ({method})")  # type: ignore[attr-defined]
        except Exception:
            pass

    def action_copy_all(self) -> None:
        text = self._get_text()
        if not text:
            return
        ok, method = copy_text(self.app, text)
        try:
            self.app.notify(f"Copied all ({method})" if ok else f"Copy failed ({method})")  # type: ignore[attr-defined]
        except Exception:
            pass

    def write(self, text: str) -> None:
        if not text:
            return

        for ch in text:
            if ch == "\r":
                self._partial = ""
                continue
            if ch == "\n":
                self._lines.append(self._partial)
                self._partial = ""
                continue
            self._partial += ch

        while len(self._lines) > self.config.max_lines:
            self._lines.popleft()

        self.text = self._get_text()

        # прокрутка вниз (если есть)
        try:
            self.scroll_end(animate=False)  # type: ignore[attr-defined]
        except Exception:
            pass