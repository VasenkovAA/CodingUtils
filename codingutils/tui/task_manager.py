from __future__ import annotations

import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional

from .plugin_api import RunHandle, RunSession
from .output import OutputHub, RunIOContext


@dataclass(slots=True)
class TaskManager:
    hub: OutputHub

    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    _runs: Dict[str, RunHandle] = field(default_factory=dict, init=False, repr=False)

    def list_runs(self) -> Dict[str, RunHandle]:
        with self._lock:
            return dict(self._runs)

    def start_threaded(self, plugin_id: str, target: Callable[[RunSession], int]) -> RunHandle:
        run_id = uuid.uuid4().hex[:12]
        cancelled = threading.Event()
        session = RunSession(run_id=run_id, plugin_id=plugin_id, cancelled=cancelled, hub=self.hub)
        handle = RunHandle(run_id=run_id, plugin_id=plugin_id, session=session, status="running")

        def runner() -> None:
            try:
                with RunIOContext(run_id):
                    code = int(target(session))
                handle.exit_code = code
                handle.status = "cancelled" if cancelled.is_set() else "done"
            except Exception as e:
                handle.status = "failed"
                handle.error = repr(e)
                handle.exit_code = 1

        t = threading.Thread(target=runner, daemon=True, name=f"run-{plugin_id}-{run_id}")
        handle.thread = t

        with self._lock:
            self._runs[run_id] = handle

        t.start()
        return handle

    def start_subprocess(self, plugin_id: str, command: str, *, shell: bool = True, cwd: Optional[str] = None) -> RunHandle:
        run_id = uuid.uuid4().hex[:12]
        cancelled = threading.Event()
        session = RunSession(run_id=run_id, plugin_id=plugin_id, cancelled=cancelled, hub=self.hub)
        handle = RunHandle(run_id=run_id, plugin_id=plugin_id, session=session, status="running")

        def pump(pipe, stream_name: str) -> None:
            sink = session.stream(stream_name)
            try:
                for line in iter(pipe.readline, ""):
                    if not line:
                        break
                    sink.write(line)
                    if cancelled.is_set():
                        break
            except Exception:
                pass

        def runner() -> None:
            try:
                with RunIOContext(run_id):
                    p = subprocess.Popen(
                        command,
                        shell=shell,
                        cwd=cwd,
                        text=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        bufsize=1,
                        universal_newlines=True,
                    )
                    handle.popen = p

                    th_out = threading.Thread(target=pump, args=(p.stdout, "stdout"), daemon=True)
                    th_err = threading.Thread(target=pump, args=(p.stderr, "stderr"), daemon=True)
                    th_out.start()
                    th_err.start()

                    while True:
                        if cancelled.is_set():
                            try:
                                p.terminate()
                            except Exception:
                                pass
                            break

                        rc = p.poll()
                        if rc is not None:
                            handle.exit_code = int(rc)
                            break
                        time.sleep(0.05)

                    handle.status = "cancelled" if cancelled.is_set() else "done"
            except Exception as e:
                handle.status = "failed"
                handle.error = repr(e)
                handle.exit_code = 1

        t = threading.Thread(target=runner, daemon=True, name=f"proc-{plugin_id}-{run_id}")
        handle.thread = t

        with self._lock:
            self._runs[run_id] = handle

        t.start()
        return handle

    def stop(self, run_id: str) -> None:
        with self._lock:
            h = self._runs.get(run_id)
        if not h:
            return
        h.status = "stopping"
        h.session.cancelled.set()