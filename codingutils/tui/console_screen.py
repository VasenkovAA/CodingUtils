from __future__ import annotations

import getpass
import json
import shlex
import socket
import sys
from pathlib import Path
from typing import Optional

from textual import events
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Input, Label

from .task_manager import TaskManager
from .widgets.console import ConsoleView


class ConsoleScreen(Screen):
    """Full-screen bash-like console (not PTY)."""

    DEFAULT_CSS = """
    ConsoleScreen {
        layout: vertical;
    }
    #console_full {
        height: 1fr;
    }   
    #cmdline {
        height: auto;
        background: transparent;
        border-top: solid $accent 30%;
    }
    #prompt {
        padding: 0 1;
        color: $text 80%;
    }
    #cmd {
        width: 1fr;
    }
    """

    BINDINGS = [
        ("escape", "close", "Close"),
        ("ctrl+d", "close", "Close"),
        ("ctrl+c", "stop", "Stop"),
        ("ctrl+l", "clear", "Clear"),
    ]

    def __init__(self, tasks: TaskManager, *, start_cwd: Optional[Path] = None) -> None:
        super().__init__()
        self.tasks = tasks
        self.cwd = (start_cwd or Path.cwd()).resolve()

        self.console = ConsoleView(id="console_full")
        self.prompt = Label("", id="prompt")
        self.input = Input(placeholder="Type command…", id="cmd")

        self._prompt_text: str = ""
        self._active_run_id: Optional[str] = None

        self._history: list[str] = []
        self._hist_pos: int = 0

    def compose(self) -> ComposeResult:
        with Vertical():
            yield self.console
            with Horizontal(id="cmdline"):
                yield self.prompt
                yield self.input

    async def on_mount(self) -> None:
        self._update_prompt()
        self.console.write("Console: Esc/Ctrl+D close, Ctrl+C stop, Ctrl+L clear\n\n")
        self.input.focus()
        self.set_interval(0.15, self._poll_active_run)
        self.console.write(f"Logged in as {getpass.getuser()}@{socket.gethostname().split('.')[0]}\n")
        self.console.write("Esc/Ctrl+D close, Ctrl+C stop, Ctrl+L clear\n\n")

    def _update_prompt(self) -> None:
        user = getpass.getuser()
        host = socket.gethostname().split(".")[0]
        self._prompt_text = f"{user}@{host}:{self.cwd}$ "
        self.prompt.update(self._prompt_text)

    def action_close(self) -> None:
        self.app.pop_screen()

    def action_clear(self) -> None:
        self.console.clear()

    def action_stop(self) -> None:
        if self._active_run_id:
            self.tasks.stop(self._active_run_id)
            self.console.write("\n[stop requested]\n")

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        cmd = (event.value or "").strip()
        self.input.value = ""
        if not cmd:
            return

        self._history.append(cmd)
        self._hist_pos = len(self._history)

        # echo like bash prompt
        self.console.write(f"{self._prompt_text}{cmd}\n")

        # builtins
        if cmd in ("exit", "quit"):
            self.action_close()
            return

        if cmd == "pwd":
            self.console.write(str(self.cwd) + "\n")
            return

        if cmd.startswith("cd"):
            await self._handle_cd(cmd)
            return

        if cmd == "clear":
            self.console.clear()
            return

        if cmd.startswith(":"):
            self._handle_internal(cmd)
            return

        if self._active_run_id:
            self.console.write("[busy] command is running; stop it with Ctrl+C\n")
            return

        # subprocess
        h = self.tasks.start_subprocess("__console__", cmd, shell=True, cwd=str(self.cwd))
        self._active_run_id = h.run_id
        h.session.bind("stdout", self.console.write)
        h.session.bind("stderr", self.console.write)

    async def _handle_cd(self, cmd: str) -> None:
        parts = shlex.split(cmd)
        if len(parts) == 1:
            target = Path.home()
        else:
            target = Path(parts[1])
            if not target.is_absolute():
                target = self.cwd / target

        try:
            target = target.resolve()
            if not target.exists() or not target.is_dir():
                self.console.write(f"cd: no such directory: {target}\n")
                return
            self.cwd = target
            self._update_prompt()
        except Exception as e:
            self.console.write(f"cd: error: {e!r}\n")

    def _handle_internal(self, cmd: str) -> None:
        if cmd == ":help":
            self.console.write("Internal commands:\n")
            self.console.write("  :help\n  :tasks\n")
            return

        if cmd == ":tasks":
            runs = self.tasks.list_runs()
            self.console.write("Runs:\n")
            for rid, h in runs.items():
                self.console.write(f"  {rid} plugin={h.plugin_id} status={h.status} code={h.exit_code}\n")
            return

        self.console.write(f"Unknown internal command: {cmd}\n")

    def _poll_active_run(self) -> None:
        if not self._active_run_id:
            return
        h = self.tasks.list_runs().get(self._active_run_id)
        if not h:
            self._active_run_id = None
            return
        if h.status in ("done", "failed", "cancelled"):
            self.console.write(f"\n[exit {h.exit_code} status={h.status}]\n")
            self._active_run_id = None
            self._update_prompt()

    async def on_key(self, event: events.Key) -> None:
        # history navigation only when input focused
        if self.app.focused is not self.input:
            return

        if event.key == "up":
            if not self._history:
                return
            self._hist_pos = max(0, self._hist_pos - 1)
            self.input.value = self._history[self._hist_pos]
            event.prevent_default()

        elif event.key == "down":
            if not self._history:
                return
            self._hist_pos = min(len(self._history), self._hist_pos + 1)
            self.input.value = "" if self._hist_pos >= len(self._history) else self._history[self._hist_pos]
            event.prevent_default()