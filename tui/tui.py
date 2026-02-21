# tui/tui.py
from __future__ import annotations

import os
import sys
import asyncio
import getpass
import socket
from datetime import datetime
from pathlib import Path

if __name__ == "__main__" and __package__ is None:
    sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.reactive import reactive
from textual.screen import Screen
from textual.widgets import (
    Button,
    Footer,
    Input,
    Label,
    Select,
    Static,
    TabbedContent,
    TabPane,
    TextArea,
    Tree,
)
from textual.widgets.tree import TreeNode

from tui.plugins_base import ToolPlugin, tool_registry
import tui.plugins  # noqa: F401


# =========================================================
# Header
# =========================================================

class AppHeader(Horizontal):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._user_host = self._compute_user_host()

    @staticmethod
    def _compute_user_host() -> str:
        # user
        try:
            user = getpass.getuser() or "user"
        except Exception:
            user = "user"

        # host/ip
        host_display = "localhost"
        try:
            hostname = socket.gethostname() or "localhost"

            ip = None
            for family, _, _, _, sockaddr in socket.getaddrinfo(hostname, None):
                if family == socket.AF_INET:
                    addr = sockaddr[0]
                    if not addr.startswith("127."):
                        ip = addr
                        break
            if ip:
                host_display = ip
            else:
                host_display = hostname or "localhost"
        except Exception:
            pass

        return f"{user}@{host_display}"

    def compose(self) -> ComposeResult:
        yield Label("[b]CodingUtils[/] [dim]v2.0.0[/]", id="app-title")
        yield Label(self._user_host, id="app-user-host")


# =========================================================
# Method selector
# =========================================================

class CommandSelector(Select):
    def __init__(self) -> None:
        metas = tool_registry.metas()
        if metas:
            options = [(m.label, m.id) for m in metas]
            initial = options[0][1]
            allow_blank = False
            has_tools = True
        else:
            options = [("No tools available", "")]
            initial = ""
            allow_blank = True
            has_tools = False

        super().__init__(
            options,
            value=initial,
            allow_blank=allow_blank,
            id="method-selector",
        )

        if not has_tools:
            try:
                self.disabled = True
            except Exception:
                pass


# =========================================================
# Command bar
# =========================================================

class CommandBar(Horizontal):
    def compose(self) -> ComposeResult:
        yield CommandSelector()
        yield Input(id="url-input")
        yield Button("Send", variant="primary", id="send-button")
        yield Static("", id="response-status")


# =========================================================
# File system tree
# =========================================================

class FileSystemTree(Tree):
    def __init__(self, root_path: Path):
        super().__init__(root_path.name, id="collection-tree")
        self.root_path = root_path.resolve()
        self.loaded_paths = set()

    def on_mount(self) -> None:
        self.root.data = self.root_path
        asyncio.create_task(self.load_children(self.root))

    async def on_tree_node_expanded(self, event: Tree.NodeExpanded) -> None:
        node = event.node
        if node.data and node.data not in self.loaded_paths:
            await self.load_children(node)

    async def load_children(self, node: TreeNode) -> None:
        path = node.data
        if not path or not path.is_dir():
            return

        self.loaded_paths.add(path)
        node.remove_children()

        try:
            items = await asyncio.to_thread(lambda: list(path.iterdir()))
            items.sort(key=lambda x: (not x.is_dir(), x.name.lower()))

            for item in items:
                if item.name.startswith("."):
                    continue

                if item.is_dir():
                    child = node.add(item.name)
                    child.data = item
                    child.add_leaf("...")
                else:
                    leaf = node.add_leaf(item.name)
                    leaf.data = item

        except PermissionError:
            node.add_leaf("Permission denied")
        except Exception as e:
            node.add_leaf(f"Error: {e}")


class FileBrowser(VerticalScroll):
    def compose(self) -> ComposeResult:
        yield Label("[b]File System[/]", classes="section-title")
        yield FileSystemTree(Path.cwd())


# =========================================================
# Outputs & Logs
# =========================================================

class OutputsArea(TextArea):
    def __init__(self) -> None:
        super().__init__(
            text="Output will appear here...",
            read_only=True,
            language="text",
            id="outputs-area",
        )


class LogsArea(VerticalScroll):
    def __init__(self) -> None:
        super().__init__(id="logs-area")

    def compose(self) -> ComposeResult:
        yield Label("[b]Execution Logs[/]", classes="logs-header")

    def add_log(self, level: str, message: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self.mount(Static(f"[{level}] {ts} {message}"))
        self.scroll_end()


class ResponseArea(Container):
    def compose(self) -> ComposeResult:
        with TabbedContent(initial="outputs"):
            with TabPane("Outputs", id="outputs"):
                yield OutputsArea()
            with TabPane("Logs", id="logs"):
                yield LogsArea()
            with TabPane("Details", id="details"):
                yield Static("No details", id="details-placeholder")

    def set_details_widget(self, widget: Static | None) -> None:
        pane = self.query_one("#details", TabPane)
        pane.remove_children()
        if widget is None:
            pane.mount(Static("No details", id="details-placeholder"))
        else:
            pane.mount(widget)


# =========================================================
# Options editor (подменяется плагином)
# =========================================================

class OptionsEditor(Container):
    """Контейнер с опциями текущего плагина."""

    def compose(self) -> ComposeResult:
        yield Static("No tool selected", id="options-placeholder")

    def on_mount(self) -> None:
        self.update_editor()

    def update_editor(self) -> None:
        """Пересоздать панель опций под текущий инструмент."""
        self.remove_children()
        screen: MainScreen = self.app.screen  # type: ignore[name-defined]
        tool = screen.current_tool
        if tool is None:
            self.mount(Static("No tools registered"))
            return
        try:
            panel = tool.create_options_panel()
        except Exception as e:
            self.mount(Static(f"Failed to create options panel: {e!r}", classes="error"))
            return
        self.mount(panel)


# =========================================================
# App body
# =========================================================

class AppBody(Horizontal):
    def compose(self) -> ComposeResult:
        yield FileBrowser(classes="section")
        with Vertical(id="main-content"):
            yield OptionsEditor(classes="section")
            yield ResponseArea(classes="section")


# =========================================================
# Main screen (STATE OWNER – только выбор плагина)
# =========================================================

class MainScreen(Screen):

    selected_tool_id = reactive("")

    BINDINGS = [
        Binding("ctrl+j", "send_request", "Send"),
        Binding("ctrl+q", "quit", "Quit"),
    ]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.plugins: dict[str, ToolPlugin] = {}

    def compose(self) -> ComposeResult:
        yield AppHeader()
        yield CommandBar()
        yield AppBody()
        yield Footer()

    def on_mount(self) -> None:
        _ = self.current_tool
        self.query_one(OptionsEditor).update_editor()
        self.update_cli_bar()

    # ---------- свойства ----------

    @property
    def current_tool(self) -> ToolPlugin | None:
        if not self.plugins:
            self.plugins = tool_registry.create_all(self)
            if self.plugins and not self.selected_tool_id:
                self.selected_tool_id = next(iter(self.plugins))
        return self.plugins.get(self.selected_tool_id)

    # ---------- реакции ----------

    def watch_selected_tool_id(self, _: str) -> None:
        self.update_cli_bar()

    def update_cli_bar(self) -> None:
        """Обновить строку с CLI‑превью."""
        url_input = self.query_one("#url-input", Input)
        tool = self.current_tool
        url_input.value = tool.build_cli_preview() if tool else ""

    # ---------- обработчики событий ----------

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "method-selector":
            self.selected_tool_id = event.value
            tool = self.current_tool
            if tool is not None:
                tool.on_selected()
            options = self.query_one(OptionsEditor)
            options.update_editor()

    # ---------- actions ----------

    async def action_send_request(self) -> None:
        logs = self.query_one("#logs-area", LogsArea)
        url_value = self.query_one("#url-input", Input).value

        tool = self.current_tool
        if tool is None:
            logs.add_log("ERROR", "No tools available to run.")
            return

        logs.add_log("INFO", f"Run: {url_value}")

        try:
            await tool.run()
        except Exception as e:
            logs.add_log("ERROR", f"Tool '{self.selected_tool_id}' failed: {e!r}")


# =========================================================
# App
# =========================================================

class PostingReplicaApp(App):
    CSS_PATH = "styles.css"
    TITLE = "CodingUtils TUI"

    def on_mount(self) -> None:
        self.push_screen(MainScreen())


def main() -> None:
    app = PostingReplicaApp()
    app.run()


if __name__ == "__main__":
    main()
