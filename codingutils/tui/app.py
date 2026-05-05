from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional
from .widgets.console import ConsoleView
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, Label
from rich.cells import cell_len
from .plugin_api import ModuleContext, PluginSpec
from .plugin_manager import PluginManager
from .task_manager import TaskManager
from .output import OutputHub, install_global_routers
from .widgets.module_list import ModuleList, ModuleItem
from .widgets.command_line import CommandLinePanel
from .console_screen import ConsoleScreen
from rich.cells import cell_len
from textual import events
from codingutils.tui.widgets.resize_handle import ResizeHandle



DEFAULT_CSS = """
#workspace {
    width: 1fr;
}
"""


class CodingUtilsTUI(App):
    TITLE = "CodingUtils TUI"
    BINDINGS = [
        ("ctrl+o", "toggle_console", "Console"),
        ("ctrl+q", "quit", "Quit"),

        ("ctrl+left", "sidebar_narrower", "Sidebar -"),
        ("ctrl+right", "sidebar_wider", "Sidebar +"),
        ("ctrl+0", "sidebar_autosize", "Sidebar auto"),
    ]
    def __init__(self, plugin_dirs: Optional[list[Path]] = None) -> None:
        super().__init__()
        self.plugin_dirs = plugin_dirs or [
            Path.cwd() / "modules",
            Path(__file__).resolve().parent / "builtin_modules",
        ]

        self.hub: OutputHub = OutputHub(self)
        self.tasks: TaskManager = TaskManager(self.hub)
        self.plugin_manager = PluginManager(self.plugin_dirs)

        self.sidebar_width: int = 24

        self.plugins: list[PluginSpec] = []
        self.plugin_widgets: Dict[str, object] = {}

        self.module_list = ModuleList()
        self.workspace = Vertical(id="workspace")
        self.command_line_panel: Optional[CommandLinePanel] = None

        self.sidebar_width: int = 24
        self.sidebar_mode: str = "auto"  # "auto" | "manual"

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            yield self.module_list
            yield ResizeHandle()
            yield self.workspace
        yield Footer()


    def _autosize_sidebar(self) -> None:
        if not self.plugins:
            self.sidebar_width = 24
            return
        max_name = max(cell_len(p.meta.name) for p in self.plugins)
        self.sidebar_width = max(16, min(max_name + 4, 60))

    def _apply_sidebar_width(self) -> None:
        self.module_list.styles.width = self.sidebar_width

    def action_sidebar_wider(self) -> None:
        self.sidebar_width = min(120, self.sidebar_width + 2)
        self._apply_sidebar_width()
        self.notify(f"Sidebar width: {self.sidebar_width}")

    def action_sidebar_narrower(self) -> None:
        self.sidebar_width = max(12, self.sidebar_width - 2)
        self._apply_sidebar_width()
        self.notify(f"Sidebar width: {self.sidebar_width}")

    def action_sidebar_autosize(self) -> None:
        self._autosize_sidebar()
        self._apply_sidebar_width()
        self.notify(f"Sidebar autosized: {self.sidebar_width}")


    async def on_mount(self) -> None:
        install_global_routers(self, self.hub)

        await self._load_plugins()
        self.module_list.focus()
        self._autosize_sidebar()
        self._apply_sidebar_width()

        dummy_ctx = ModuleContext(app=self, plugin=self.plugins[0], tasks=self.tasks, hub=self.hub) if self.plugins else None
        if dummy_ctx:
            self.command_line_panel = CommandLinePanel(dummy_ctx)
            await self.mount(self.command_line_panel)
            self.command_line_panel.hide()

    async def _load_plugins(self) -> None:
        self.plugins, errors = self.plugin_manager.discover()

        self.module_list.clear()
        for p in sorted(self.plugins, key=lambda x: x.meta.name.lower()):
            await self.module_list.append(ModuleItem(p))

        if errors:
            err_console = ConsoleView(id="plugin_errors")
            await self.workspace.mount(err_console)

            err_console.write("Some plugins failed to load:\n\n")
            for e in errors:
                err_console.write(f"{e.path}\n")
                err_console.write(f"module={e.module_name}\n")
                err_console.write(f"error={e.error}\n")
                if e.traceback:
                    err_console.write("traceback:\n")
                    err_console.write(e.traceback)
                err_console.write("\n" + ("-" * 60) + "\n\n")

            err_console.focus()
        if self.sidebar_mode == "auto":
            self._autosize_sidebar()
        self._apply_sidebar_width()

    async def on_list_view_selected(self, event: ModuleList.Selected) -> None:
        item = event.item
        if not isinstance(item, ModuleItem):
            return
        await self._activate_plugin(item.plugin)

    async def _activate_plugin(self, plugin: PluginSpec) -> None:
        self.workspace.remove_children()

        ctx = ModuleContext(app=self, plugin=plugin, tasks=self.tasks, hub=self.hub)
        widget = plugin.create_ui(ctx)
        await self.workspace.mount(widget)

        if self.command_line_panel:
            self.command_line_panel.ctx = ctx

    def action_toggle_console(self) -> None:
        if isinstance(self.screen, ConsoleScreen):
            self.pop_screen()
        else:
            self.push_screen(ConsoleScreen(self.tasks))

    def toggle_command_line(self) -> None:
        if not self.command_line_panel:
            return
        if self.command_line_panel.display:
            self.command_line_panel.hide()
            self.module_list.focus()
        else:
            self.command_line_panel.show()

    def _sidebar_max_width(self) -> int:
        # оставим рабочей области минимум 40 колонок
        min_workspace = 40
        max_w = max(12, self.size.width - min_workspace)
        # плюс ограничим разумно, чтобы sidebar не съедал весь экран
        return min(max_w, max(20, int(self.size.width * 0.65)))

    def _autosize_sidebar(self) -> None:
        if not self.plugins:
            self.sidebar_width = 24
            return
        max_name = max(cell_len(p.meta.name) for p in self.plugins)
        wanted = max_name + 4  # padding/selection
        self.sidebar_width = max(16, min(wanted, self._sidebar_max_width()))

    def _apply_sidebar_width(self) -> None:
        self.module_list.styles.width = self.sidebar_width

    def set_sidebar_width(self, width: int, *, manual: bool) -> None:
        width = int(width)
        width = max(12, min(width, self._sidebar_max_width()))
        self.sidebar_width = width
        if manual:
            self.sidebar_mode = "manual"
        self._apply_sidebar_width()

    def on_resize(self, event: events.Resize) -> None:
        # clamp width в любом режиме
        if self.sidebar_mode == "auto":
            self._autosize_sidebar()
        else:
            self.sidebar_width = max(12, min(self.sidebar_width, self._sidebar_max_width()))
        self._apply_sidebar_width()


def main() -> None:
    app = CodingUtilsTUI()
    app.run()
