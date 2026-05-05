from __future__ import annotations

from textual.containers import Vertical
from textual.widgets import Input, Label, Button
from textual.widget import Widget
from textual.reactive import reactive

from .console import ConsoleView
from ..plugin_api import ModuleContext


class CommandLinePanel(Widget):
    DEFAULT_CSS = """
    CommandLinePanel {
        height: 40%;
        dock: bottom;
        background: $panel;
        border-top: heavy $accent;
    }
    """

    visible_panel = reactive(False)

    def __init__(self, ctx: ModuleContext, id: str | None = "command_line") -> None:
        super().__init__(id=id)
        self.ctx = ctx
        self.input = Input(placeholder="Command (':help' for internal)...")
        self.console = ConsoleView()
        self.hint = Label("Enter = run, Esc = close, Ctrl+C = stop текущей команды (если будет добавлено)")

        self._active_run_id: str | None = None

    def compose(self):
        with Vertical():
            yield self.hint
            yield self.input
            yield self.console

    def show(self) -> None:
        self.display = True
        self.input.focus()

    def hide(self) -> None:
        self.display = False

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        cmd = (event.value or "").strip()
        if not cmd:
            return
        self.input.value = ""

        if cmd.startswith(":"):
            await self._run_internal(cmd)
            return

        # OS command
        self.console.write(f"$ {cmd}\n")
        h = self.ctx.tasks.start_subprocess("__cmdline__", cmd, shell=True)
        self._active_run_id = h.run_id
        h.session.bind("stdout", self.console.write)
        h.session.bind("stderr", self.console.write)

    async def _run_internal(self, cmd: str) -> None:
        if cmd in (":help",):
            self.console.write("Internal commands:\n")
            self.console.write("  :help\n  :modules\n  :tasks\n")
            return

        if cmd == ":modules":
            # покажем просто подсказку; список модулей уже слева
            self.console.write("Modules are visible in the left panel.\n")
            return

        if cmd == ":tasks":
            runs = self.ctx.tasks.list_runs()
            self.console.write("Runs:\n")
            for rid, h in runs.items():
                self.console.write(f"  {rid} plugin={h.plugin_id} status={h.status} code={h.exit_code}\n")
            return

        self.console.write(f"Unknown internal command: {cmd}\n")
