from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from textual import events
from textual.widget import Widget


@dataclass(slots=True)
class DragState:
    dragging: bool = False
    start_x: int = 0
    start_width: int = 0


class ResizeHandle(Widget):
    """Vertical draggable divider to resize sidebar."""

    DEFAULT_CSS = """
    ResizeHandle {
        width: 1;
        background: $accent 30%;
    }
    ResizeHandle:hover {
        background: $accent 60%;
    }
    """

    can_focus = False

    def __init__(self, *, id: str | None = "sidebar_resize_handle") -> None:
        super().__init__(id=id)
        self._drag = DragState()

    def on_mouse_down(self, event: events.MouseDown) -> None:
        if event.button != 1:
            return
        self._drag.dragging = True
        self._drag.start_x = event.screen_x
        self._drag.start_width = int(getattr(self.app, "sidebar_width", 24))
        self.capture_mouse()
        event.stop()

    def on_mouse_move(self, event: events.MouseMove) -> None:
        if not self._drag.dragging:
            return

        delta = event.screen_x - self._drag.start_x
        new_width = self._drag.start_width + delta

        setter = getattr(self.app, "set_sidebar_width", None)
        if callable(setter):
            setter(new_width, manual=True)

        event.stop()

    def on_mouse_up(self, event: events.MouseUp) -> None:
        if not self._drag.dragging:
            return
        self._drag.dragging = False
        self.release_mouse()
        event.stop()

    def on_double_click(self, event: events.DoubleClick) -> None:
        # dblclick -> autosize
        autosize = getattr(self.app, "action_sidebar_autosize", None)
        if callable(autosize):
            autosize()
        event.stop()