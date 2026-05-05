from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from textual.containers import Horizontal, Vertical, Container
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import (
    Button,
    DirectoryTree,
    Label,
    ProgressBar,
    TabbedContent,
    TabPane,
)

from codingutils.tui.plugin_api import ModuleContext, RunSession
from codingutils.tui.widgets.console import ConsoleView


PLUGIN_META = {
    "id": "builtin.showcase",
    "name": "Showcase (engine demo)",
    "version": "1.0.0",
    "description": "Demonstrates custom UI, multiple consoles/streams, multiple progress bars, directory tree, subprocess run, stop, hotkeys.",
}


# -----------------------------
# Helpers: UI event protocol
# -----------------------------
def _ev_progress(pid: str, current: int, total: int, message: str = "") -> str:
    return json.dumps({"type": "progress", "id": pid, "current": current, "total": total, "message": message}) + "\n"


def _ev_status(text: str) -> str:
    return json.dumps({"type": "status", "text": text}) + "\n"


@dataclass
class ProgressState:
    total: int = 100
    current: int = 0
    message: str = ""


class ShowcaseUI(Widget):
    """
    Showcase module:
    - Left: DirectoryTree (select files/dirs)
    - Right: Tabs with multiple consoles
    - Bottom: Multiple progress bars + status
    - Run: threaded worker sending:
        - stream "main" -> main console
        - stream "debug" -> debug console
        - stream "events" -> updates progress bars/status in UI
        - plus normal print()/sys.stderr output routed via sys.stdout/sys.stderr streams
    - Also supports subprocess demo in parallel with module run
    """

    BINDINGS = [
        ("f5", "run", "Run (thread)"),
        ("f6", "stop", "Stop run"),
        ("f7", "subprocess", "Run subprocess"),
        ("f8", "stop_subprocess", "Stop subprocess"),
        ("ctrl+l", "clear", "Clear consoles"),
        ("ctrl+o", "cmd", "Command line"),
    ]

    running = reactive(False)
    proc_running = reactive(False)

    def __init__(self, ctx: ModuleContext) -> None:
        super().__init__()
        self.ctx = ctx

        # consoles (module decides placement)
        self.console_main = ConsoleView(id="console_main")
        self.console_debug = ConsoleView(id="console_debug")
        self.console_proc = ConsoleView(id="console_proc")

        # progress bars (multiple)
        self.pb_overall = ProgressBar(total=100, show_percentage=True, id="pb_overall")
        self.pb_inner = ProgressBar(total=50, show_percentage=True, id="pb_inner")

        self.lbl_status = Label("Idle", id="status")

        self.dir_tree = DirectoryTree(str(Path.cwd()), id="tree")

        self._run_handle = None
        self._proc_handle = None

        # progress state (optional)
        self._p_overall = ProgressState(total=100)
        self._p_inner = ProgressState(total=50)

    # ---------- UI layout ----------
    def compose(self):
        # Top controls
        with Vertical():
            yield Label("Showcase module: custom UI, multi-console, multi-progress, streams, tree, subprocess", id="title")

            with Horizontal(id="toolbar"):
                yield Button("Run (F5)", id="run")
                yield Button("Stop (F6)", id="stop")
                yield Button("Subprocess (F7)", id="proc")
                yield Button("Stop proc (F8)", id="proc_stop")
                yield Button("Clear (Ctrl+L)", id="clear")
                yield Button("CmdLine (Ctrl+O)", id="cmd")

            # Main area: left tree, right tabs
            with Horizontal(id="main_area"):
                with Container(id="left"):
                    yield Label("Directory tree:", id="tree_label")
                    yield self.dir_tree

                with Container(id="right"):
                    with TabbedContent(id="tabs"):
                        with TabPane("Main console", id="tab_main"):
                            yield self.console_main
                        with TabPane("Debug console", id="tab_debug"):
                            yield self.console_debug
                        with TabPane("Subprocess console", id="tab_proc"):
                            yield self.console_proc

            # Bottom: multiple progress bars + status
            with Container(id="progress_area"):
                yield Label("Overall:", id="lbl_overall")
                yield self.pb_overall
                yield Label("Inner:", id="lbl_inner")
                yield self.pb_inner
                yield self.lbl_status

    # ---------- events ----------
    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "run":
            self.action_run()
        elif bid == "stop":
            self.action_stop()
        elif bid == "proc":
            self.action_subprocess()
        elif bid == "proc_stop":
            self.action_stop_subprocess()
        elif bid == "clear":
            self.action_clear()
        elif bid == "cmd":
            self.action_cmd()

    def on_directory_tree_file_selected(self, event: DirectoryTree.FileSelected) -> None:
        self.console_debug.write(f"[tree] file selected: {event.path}\n")

    def on_directory_tree_directory_selected(self, event: DirectoryTree.DirectorySelected) -> None:
        self.console_debug.write(f"[tree] dir selected: {event.path}\n")

    # ---------- actions ----------
    def action_cmd(self) -> None:
        self.ctx.open_command_line()

    def action_clear(self) -> None:
        self.console_main.clear()
        self.console_debug.clear()
        self.console_proc.clear()
        self.lbl_status.update("Cleared")

    def action_run(self) -> None:
        if self._run_handle and self._run_handle.status == "running":
            self.console_debug.write("[run] already running\n")
            return

        self.console_debug.write("[run] starting threaded job\n")
        self.lbl_status.update("Running (thread)...")
        self.running = True

        # start worker thread
        self._run_handle = self.ctx.tasks.start_threaded(self.ctx.plugin.meta.id, self._worker)

        # bind streams to consoles
        # - explicit custom streams
        self._run_handle.session.bind("main", self.console_main.write)
        self._run_handle.session.bind("debug", self.console_debug.write)
        self._run_handle.session.bind("events", self._on_events_stream)

        # - also bind global stdout/stderr routed by StreamRouter
        self._run_handle.session.bind("stdout", self.console_main.write)
        self._run_handle.session.bind("stderr", self.console_debug.write)

        # reset progress bars
        self.pb_overall.total = 100
        self.pb_overall.progress = 0
        self.pb_inner.total = 50
        self.pb_inner.progress = 0

    def action_stop(self) -> None:
        if not self._run_handle:
            return
        self.console_debug.write("[run] stop requested\n")
        self.ctx.tasks.stop(self._run_handle.run_id)
        self.lbl_status.update("Stopping (thread)...")

    def action_subprocess(self) -> None:
        if self._proc_handle and self._proc_handle.status == "running":
            self.console_debug.write("[proc] already running\n")
            return

        self.console_debug.write("[proc] starting subprocess demo\n")
        self.proc_running = True

        # Cross-platform-ish subprocess demo: run python itself, unbuffered
        # Note: since TaskManager uses shell=True, keep command as a string.
        code = (
            "import sys,time\n"
            "print('subprocess: start')\n"
            "sys.stdout.flush()\n"
            "for i in range(101):\n"
            "    sys.stdout.write('\\rsubprocess progress %d%%' % i)\n"
            "    sys.stdout.flush()\n"
            "    time.sleep(0.03)\n"
            "print('\\nsubprocess: done')\n"
        )
        cmd = f"{sys.executable} -u -c {json.dumps(code)}"

        self._proc_handle = self.ctx.tasks.start_subprocess(self.ctx.plugin.meta.id, cmd, shell=True)

        self._proc_handle.session.bind("stdout", self.console_proc.write)
        self._proc_handle.session.bind("stderr", self.console_proc.write)

    def action_stop_subprocess(self) -> None:
        if not self._proc_handle:
            return
        self.console_debug.write("[proc] stop requested\n")
        self.ctx.tasks.stop(self._proc_handle.run_id)

    # ---------- worker logic ----------
    def _worker(self, session: RunSession) -> int:
        main = session.stream("main")
        dbg = session.stream("debug")
        ev = session.stream("events")

        main.write("Worker: started\n")
        dbg.write("Debug: preparing...\n")

        # show that normal print() is also routed into this run (stdout)
        print("print(): hello from worker (stdout)")

        # show that stderr is also routed
        sys.stderr.write("sys.stderr: hello from worker (stderr)\n")

        # demonstrate listing a few files
        try:
            cwd = Path.cwd()
            main.write(f"\nCWD: {cwd}\n")
            for p in list(cwd.iterdir())[:15]:
                main.write(f" - {p.name}\n")
        except Exception as e:
            dbg.write(f"Failed to list cwd: {e!r}\n")

        ev.write(_ev_status("Thread job running..."))

        total = 100
        for i in range(total + 1):
            if session.cancelled.is_set():
                dbg.write("\nCancelled by user\n")
                ev.write(_ev_status("Cancelled"))
                return 130

            # tqdm-like line (carriage return) into main stream
            main.write(f"\rMain progress line: {i:3d}%")

            # two progress bars updated via events stream
            ev.write(_ev_progress("overall", i, total, f"overall step {i}/{total}"))

            # inner progress cycles 0..50
            inner_total = 50
            inner_cur = i % (inner_total + 1)
            ev.write(_ev_progress("inner", inner_cur, inner_total, f"inner {inner_cur}/{inner_total}"))

            if i % 10 == 0:
                dbg.write(f"\n[debug] checkpoint i={i}\n")

            time.sleep(0.03)

        main.write("\nWorker: done\n")
        ev.write(_ev_status("Done"))
        return 0

    # ---------- UI event stream consumer (runs in UI thread) ----------
    def _on_events_stream(self, text: str) -> None:
        """
        Receives JSON lines from worker and updates UI elements.
        This callback is called in UI thread (OutputHub uses call_from_thread).
        """
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                self.console_debug.write(f"[events] bad json: {line}\n")
                continue

            t = obj.get("type")
            if t == "status":
                self.lbl_status.update(str(obj.get("text", "")))
                continue

            if t == "progress":
                pid = str(obj.get("id", ""))
                cur = int(obj.get("current", 0))
                total = int(obj.get("total", 100))
                msg = str(obj.get("message", ""))

                if pid == "overall":
                    self.pb_overall.total = max(1, total)
                    self.pb_overall.progress = max(0, min(cur, total))
                    # optional: show message
                    # self.console_debug.write(f"[overall] {msg}\n")
                elif pid == "inner":
                    self.pb_inner.total = max(1, total)
                    self.pb_inner.progress = max(0, min(cur, total))
                else:
                    # unknown progress id -> log to debug
                    self.console_debug.write(f"[events] unknown progress id={pid}: {msg}\n")


def create_ui(ctx: ModuleContext) -> Widget:
    return ShowcaseUI(ctx)
