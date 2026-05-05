from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from rich.text import Text
from textual.widgets import DirectoryTree

from .models import NodeSelectMode


@dataclass(slots=True)
class TreeSelection:
    modes: Dict[Path, NodeSelectMode]

    def get(self, p: Path) -> NodeSelectMode:
        return self.modes.get(p, NodeSelectMode.NONE)

    def set(self, p: Path, mode: NodeSelectMode) -> None:
        if mode == NodeSelectMode.NONE:
            self.modes.pop(p, None)
        else:
            self.modes[p] = mode


class SelectableDirectoryTree(DirectoryTree):
    """
    Space cycles:
      dir:  NONE -> FLAT -> RECURSIVE -> NONE
      file: NONE -> FLAT -> NONE

    R toggles recursion (dir):
      NONE/FLAT -> RECURSIVE
      RECURSIVE -> FLAT
    """

    BINDINGS = [
        ("space", "cycle", "Cycle selection"),
        ("r", "toggle_recursive", "Toggle recursion"),
    ]

    def __init__(self, root: str | Path, *, id: Optional[str] = None) -> None:
        super().__init__(str(root), id=id)
        self.selection = TreeSelection(modes={})

    @staticmethod
    def _node_path(data: Any) -> Optional[Path]:
        # Textual 8 DirectoryTree uses DirEntry(path=Path(...), loaded=...)
        if data is None:
            return None
        if hasattr(data, "path"):
            try:
                return Path(getattr(data, "path"))
            except Exception:
                return None
        if isinstance(data, Path):
            return data
        if isinstance(data, str):
            return Path(data)
        return None

    def _cursor_path(self) -> Optional[Path]:
        node = getattr(self, "cursor_node", None)
        if node is None:
            return None
        return self._node_path(getattr(node, "data", None))

    def _force_redraw(self) -> None:
        try:
            self._clear_line_cache()  # internal textual method
        except Exception:
            pass
        self.refresh(repaint=True)

    def action_cycle(self) -> None:
        p = self._cursor_path()
        if not p:
            return

        cur = self.selection.get(p)

        if p.is_file():
            # file: NONE <-> FLAT
            new = NodeSelectMode.FLAT if cur == NodeSelectMode.NONE else NodeSelectMode.NONE
            self.selection.set(p, new)
            self._force_redraw()
            return

        # dir: NONE -> FLAT -> RECURSIVE -> NONE
        if cur == NodeSelectMode.NONE:
            new = NodeSelectMode.FLAT
        elif cur == NodeSelectMode.FLAT:
            new = NodeSelectMode.RECURSIVE
        else:
            new = NodeSelectMode.NONE

        self.selection.set(p, new)
        self._force_redraw()

    def action_toggle_recursive(self) -> None:
        p = self._cursor_path()
        if not p:
            return
        if p.is_file():
            self.selection.set(p, NodeSelectMode.FLAT)
            self._force_redraw()
            return

        cur = self.selection.get(p)
        new = NodeSelectMode.FLAT if cur == NodeSelectMode.RECURSIVE else NodeSelectMode.RECURSIVE
        self.selection.set(p, new)
        self._force_redraw()

    def _badge_for(self, path: Path) -> Text:
        mode = self.selection.get(path)
        if mode == NodeSelectMode.NONE:
            return Text("[ ] ", style="dim")
        if mode == NodeSelectMode.FLAT:
            return Text("[✓] ", style="green")
        return Text("[R] ", style="bright_green")

    def render_label(self, node, base_style, style):
        label = super().render_label(node, base_style, style)
        p = self._node_path(getattr(node, "data", None))
        if p is None:
            return label
        badge = self._badge_for(p)
        if isinstance(label, Text):
            return Text.assemble(badge, label)
        return Text.assemble(badge, Text(str(label)))

    def get_selected(self) -> Dict[Path, NodeSelectMode]:
        return dict(self.selection.modes)