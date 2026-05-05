from __future__ import annotations

import os
import platform
import shutil
import subprocess
from typing import Optional, Tuple


def _run_copy(cmd: list[str], text: str) -> bool:
    try:
        subprocess.run(
            cmd,
            input=text,
            text=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
            timeout=2,
        )
        return True
    except Exception:
        return False


def copy_text_system(text: str) -> Tuple[bool, str]:
    """Try to copy to *system* clipboard. Returns (ok, method)."""
    if not text:
        return False, "empty"

    sysname = platform.system().lower()

    # macOS
    if sysname == "darwin":
        if shutil.which("pbcopy"):
            return _run_copy(["pbcopy"], text), "pbcopy"

    # Windows
    if sysname == "windows":
        # 'clip' exists on most Windows
        if shutil.which("clip"):
            return _run_copy(["clip"], text), "clip"
        # PowerShell fallback
        if shutil.which("powershell"):
            return _run_copy(["powershell", "-NoProfile", "-Command", "Set-Clipboard"], text), "powershell:Set-Clipboard"

    # Linux / *nix
    if sysname == "linux":
        # Wayland
        if os.environ.get("WAYLAND_DISPLAY") and shutil.which("wl-copy"):
            return _run_copy(["wl-copy"], text), "wl-copy"

        # X11
        if os.environ.get("DISPLAY"):
            if shutil.which("xclip"):
                # xclip wants selection arg
                ok = _run_copy(["xclip", "-selection", "clipboard"], text)
                return ok, "xclip"
            if shutil.which("xsel"):
                ok = _run_copy(["xsel", "--clipboard", "--input"], text)
                return ok, "xsel"

    return False, "no-backend"


def copy_text(app, text: str) -> Tuple[bool, str]:
    """
    Copy text to clipboard:
    1) system clipboard via external tools
    2) fallback to Textual OSC52
    Returns (ok, method).
    """
    ok, method = copy_text_system(text)
    if ok:
        return True, method

    # fallback: Textual OSC52
    try:
        app.copy_to_clipboard(text)  # Textual 8.x
        return True, "osc52"
    except Exception:
        return False, "failed"