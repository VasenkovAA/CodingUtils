from __future__ import annotations

import copy
import json
import time
from pathlib import Path
from typing import Dict, Optional, Set

from rich.text import Text

from textual import events
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.widget import Widget
from textual.widgets import (
    Button,
    Checkbox,
    Input,
    Label,
    Rule,
    Static,
    TabbedContent,
    TabPane,
    TextArea,
    Tree,
    ListView,
    ListItem,
)

from textual.widgets.tree import TreeNode

from codingutils.tui.plugin_api import ModuleContext, RunSession
from codingutils.tui.widgets.console import ConsoleView

from .models import CleanerSettings, ScanResult, FileRecord, CommentItem
from .decisions import load_decisions, save_decisions
from .scan_engine import scan_project, ScanCacheEntry
from .selectable_tree import SelectableDirectoryTree
from .apply_engine import preview_diff_file, apply_file
from .export_engine import export_report


MAX_DISPLAY_LINES = 12
MAX_COLS = 180


def _format_comment_text(text: str) -> str:
    lines = (text or "").splitlines() or [""]
    out: list[str] = []
    for line in lines[:MAX_DISPLAY_LINES]:
        if len(line) > MAX_COLS:
            line = line[: MAX_COLS - 1] + "…"
        out.append(line)
    if len(lines) > MAX_DISPLAY_LINES:
        out.append("…")
    return "\n".join("  " + l for l in out)


class CommentDeleteChanged(Message):
    """Posted when a comment's delete flag changes (toggle / space / click)."""

    bubble = True

    def __init__(self, item: CommentItem) -> None:
        self.item = item
        super().__init__()


class DeleteIndicator(Static):
    """
    Visible mark for delete (plain strings — Rich Text in Static can fail to paint).
    Click toggles; Space is handled by CommentListView on the row.
    """

    DEFAULT_CSS = """
    DeleteIndicator {
        width: 7;
        min-width: 7;
        height: auto;
        min-height: 2;
        padding: 0 1;
        margin: 0 1 0 0;
        text-style: bold;
        content-align: center middle;
    }
    """

    def __init__(self, row: "CommentRow") -> None:
        super().__init__("")
        self.row = row
        self._refresh()

    def _refresh(self) -> None:
        it = self.row.item
        if it.excluded:
            self.update("—")
            self.styles.opacity = 0.55
        else:
            self.styles.opacity = 1.0
            # ☐/☑ already draw the box + tick — no extra border (avoids double frame)
            self.update("☑" if it.delete else "☐")

    def on_click(self, event: events.Click) -> None:
        it = self.row.item
        if it.excluded:
            return
        it.delete = not it.delete
        self._refresh()
        self.row.post_message(CommentDeleteChanged(it))
        event.stop()


class CommentRow(ListItem):
    """
    One comment row: left = delete indicator, right = meta + body (multiline-friendly).
    Row click does not toggle; indicator click or Space does.
    """

    DEFAULT_CSS = """
    CommentRow {
        height: auto;
        padding: 0 0;
        margin: 0 0 1 0;
    }
    CommentRow > Horizontal {
        height: auto;
        align: left top;
    }
    CommentRow Vertical {
        height: auto;
        width: 1fr;
    }
    CommentRow .comment-meta {
        text-style: bold;
        color: $accent 85%;
        height: auto;
    }
    CommentRow .comment-body {
        height: auto;
        margin-top: 0;
    }
    """

    def __init__(self, item: CommentItem) -> None:
        super().__init__()
        self.item = item
        self.indicator = DeleteIndicator(self)

        new_tag = " NEW" if item.is_new and not item.excluded else ""
        cell = f" cell={item.cell_index}" if item.cell_index is not None else ""
        loc = f" L{item.start_line}" if item.start_line == item.end_line else f" L{item.start_line}-{item.end_line}"
        meta = f"{new_tag} [{item.kind}]{cell}{loc}"
        body = _format_comment_text(item.text)

        self.lbl_meta = Label(meta, markup=False, classes="comment-meta")
        self.lbl_body = Label(body, markup=False, classes="comment-body")
        if item.excluded:
            self.lbl_meta.styles.opacity = 0.55
            self.lbl_body.styles.opacity = 0.55

    def compose(self):
        with Horizontal():
            yield self.indicator
            with Vertical():
                yield self.lbl_meta
                yield self.lbl_body

    def toggle_delete(self) -> None:
        if self.item.excluded:
            return
        self.item.delete = not self.item.delete
        self.indicator._refresh()
        self.post_message(CommentDeleteChanged(self.item))


class CleanerForwardMixin:
    """Forward module hotkeys when a nested widget (list/tree) holds focus."""

    _cleaner: "CommentCleanerUI"

    def action_fwd_scan(self) -> None:
        self._cleaner.action_scan()

    def action_fwd_stop(self) -> None:
        self._cleaner.action_stop()

    def action_fwd_diff(self) -> None:
        self._cleaner.action_preview_diff()

    def action_fwd_apply(self) -> None:
        self._cleaner.action_apply()

    def action_fwd_save(self) -> None:
        self._cleaner.action_save_decisions()

    def action_fwd_export(self) -> None:
        self._cleaner.action_export()

    def action_fwd_cmd(self) -> None:
        self._cleaner.action_cmd()

    def action_fwd_all(self) -> None:
        self._cleaner.action_select_all_file()

    def action_fwd_new(self) -> None:
        self._cleaner.action_select_new_only_file()

    def action_fwd_inv(self) -> None:
        self._cleaner.action_invert_file()


_FWD_BINDINGS = [
    ("f5", "fwd_scan", "Scan"),
    ("f6", "fwd_stop", "Stop"),
    ("f7", "fwd_diff", "Preview diff"),
    ("f8", "fwd_apply", "Apply"),
    ("ctrl+s", "fwd_save", "Save decisions"),
    ("ctrl+e", "fwd_export", "Export"),
    ("ctrl+o", "fwd_cmd", "Console"),
    ("a", "fwd_all", "Select all (file)"),
    ("n", "fwd_new", "Select new only (file)"),
    ("i", "fwd_inv", "Invert (file)"),
]


class CommentListView(CleanerForwardMixin, ListView):
    """
    Space toggles delete on the highlighted row.
    F5–F8 etc. are forwarded: ListView keeps focus so parent bindings would not run.
    """

    BINDINGS = [("space", "toggle", "Toggle delete"), *_FWD_BINDINGS]

    def __init__(self, cleaner: CommentCleanerUI, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._cleaner = cleaner

    def action_toggle(self) -> None:
        row = self.highlighted_child
        if not isinstance(row, CommentRow):
            return
        row.toggle_delete()


class FilesTree(CleanerForwardMixin, Tree):
    """File tree with the same hotkey forwarding as CommentListView."""

    BINDINGS = list(_FWD_BINDINGS)

    def __init__(self, cleaner: CommentCleanerUI, label: str = "Files", *, id: str | None = None) -> None:
        super().__init__(label, id=id)
        self._cleaner = cleaner


class DiffFilesList(CleanerForwardMixin, ListView):
    """Diff file list: forward hotkeys when this list is focused."""

    BINDINGS = list(_FWD_BINDINGS)

    def __init__(self, cleaner: CommentCleanerUI, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._cleaner = cleaner


class DiffRow(ListItem):
    def __init__(self, rel_path: str) -> None:
        super().__init__()
        self.rel_path = rel_path
        self.lbl = Label(rel_path)

    def compose(self):
        yield self.lbl


class CommentCleanerUI(Widget):
    DEFAULT_CSS = """
    CommentCleanerUI { height: 1fr; }

    #toolbar {
        height: auto;
        padding: 0 1;
        border-bottom: solid $accent 30%;
    }

    #tabs { height: 1fr; }
    TabPane { height: 1fr; }

    #settings_scroll { height: 1fr; padding: 0 1; }

    #settings_scroll Checkbox {
        margin: 0 0 1 0;
    }

    .section_title {
        margin-top: 1;
        text-style: bold;
        color: $accent;
    }

    #paths_tree {
        height: 18;
        border: round $accent 30%;
    }

    #excl_dirs, #excl_names, #excl_paths, #excl_prefixes {
        height: 6;
    }

    /* Results */
    #results_root { height: 1fr; }
    #files_tree { height: 1fr; border: round $accent 20%; }

    #comments_header { height: auto; }
    #comments_info { width: 1fr; }
    #load_more, #show_context { width: auto; }

    #comments_list { height: 1fr; border: round $accent 20%; padding: 0 0; }
    #context_view { height: 10; }

    /* Diff */
    #diff_root { height: 1fr; }
    #diff_files { height: 1fr; border: round $accent 20%; }
    #diff_view { height: 1fr; border: round $accent 20%; }

    #cc_console { height: 1fr; }
    """

    BINDINGS = [
        ("f5", "scan", "Scan"),
        ("f6", "stop", "Stop"),
        ("f7", "preview_diff", "Preview diff"),
        ("f8", "apply", "Apply"),
        ("ctrl+s", "save_decisions", "Save decisions"),
        ("ctrl+e", "export", "Export report"),
        ("ctrl+o", "cmd", "Console"),
        ("a", "select_all_file", "Select all (file)"),
        ("n", "select_new_only_file", "Select new only (file)"),
        ("i", "invert_file", "Invert (file)"),
    ]

    def __init__(self, ctx: ModuleContext) -> None:
        super().__init__()
        self.ctx = ctx
        self.settings = CleanerSettings()

        self._scan_handle = None
        self._diff_handle = None
        self._apply_handle = None

        self._scan_result: Optional[ScanResult] = None
        self._current_file_rel: Optional[str] = None

        self._scan_cache: Dict[Path, ScanCacheEntry] = {}
        self._file_nodes: Dict[str, TreeNode] = {}
        self._diffs: Dict[str, str] = {}
        self._last_preview_fp: Optional[str] = None
        self._pre_apply_diff_pending: bool = False

        self.console = ConsoleView(id="cc_console")
        self.lbl_status = Label("Idle", id="scan_status")

        # Settings widgets
        self.paths_tree = SelectableDirectoryTree(Path.cwd(), id="paths_tree")

        self.input_include = Input(value="*", placeholder='Include patterns, e.g. "*.py *.js"', id="include")
        self.cb_recursive = Checkbox("Recursive default", value=True, id="recursive")
        self.input_max_depth = Input(placeholder="Max depth (empty = none)", id="max_depth")

        self.ta_excl_dirs = TextArea("", id="excl_dirs")
        self.ta_excl_names = TextArea("", id="excl_names")
        self.ta_excl_paths = TextArea("", id="excl_paths")
        self.ta_excl_prefixes = TextArea("", id="excl_prefixes")

        self.cb_langdetect = Checkbox("Use langdetect", value=False, id="langdetect")
        self.input_lang = Input(placeholder="lang (ru/en/..)", id="lang")
        self.input_lang_min = Input(value="20", placeholder="min len", id="lang_min")

        self.cb_preserve_lines = Checkbox("Preserve line count on delete", value=False, id="preserve_lines")
        self.cb_incremental = Checkbox("Incremental by mtime (in-memory)", value=False, id="incremental")

        self.cb_preview_diff = Checkbox("Enable preview diff", value=True, id="enable_diff")
        self.cb_preview_before_apply = Checkbox(
            "Show diff before apply (1st F8 = diff, 2nd F8 = write files)",
            value=self.settings.preview_diff_before_apply,
            id="preview_before_apply",
        )
        self.input_diff_kb = Input(value=str(self.settings.diff_max_kb_per_file), id="diff_kb")

        self.cb_backups = Checkbox("Make backups", value=False, id="make_backups")
        self.input_backup_dir = Input(value=str(self.settings.backup_dir), id="backup_dir")
        self.cb_overwrite_bak = Checkbox("Overwrite backups", value=False, id="overwrite_bak")

        self.input_decisions_path = Input(value=str(self.settings.decisions_path), id="decisions_path")
        self.input_export_path = Input(value=str(self.settings.export_path), id="export_path")

        # Results widgets (hotkeys forwarded while these have focus — see CleanerForwardMixin)
        self.files_tree = FilesTree(self, "Files", id="files_tree")
        self.comments_list = CommentListView(self, id="comments_list")
        self.lbl_comments_info = Label("No file selected", id="comments_info")
        self.btn_load_more = Button("More", id="load_more")
        self.btn_show_context = Button("Ctx", id="show_context")

        self.context_view = TextArea("", id="context_view")
        self.context_view.read_only = True
        self.context_view.show_line_numbers = False

        # Diff widgets
        self.diff_files = DiffFilesList(self, id="diff_files")
        self.diff_view = TextArea("", id="diff_view")
        self.diff_view.read_only = True
        self.diff_view.show_line_numbers = False

    def compose(self):
        with Vertical():
            with Horizontal(id="toolbar"):
                yield Button("Scan (F5)", id="scan")
                yield Button("Stop (F6)", id="stop")
                yield Button("Diff (F7)", id="diff")
                yield Button("Apply (F8)", id="apply")
                yield Button("Save (Ctrl+S)", id="save")
                yield Button("Export (Ctrl+E)", id="export")
                yield self.lbl_status

            with TabbedContent(id="tabs"):
                with TabPane("Settings", id="tab_settings"):
                    with VerticalScroll(id="settings_scroll"):
                        yield Label("Paths", classes="section_title")
                        yield Rule()
                        yield Label("Space cycles: none → flat → recursive → none.  R toggles recursion.")
                        yield self.paths_tree

                        yield Label("Discovery filters", classes="section_title")
                        yield Rule()
                        yield self.input_include
                        yield self.cb_recursive
                        yield self.input_max_depth

                        yield Label("Excludes", classes="section_title")
                        yield Rule()
                        yield Label("Exclude dirs (one per line):")
                        yield self.ta_excl_dirs
                        yield Label("Exclude names/wildcards (one per line):")
                        yield self.ta_excl_names
                        yield Label("Exclude path patterns (one per line):")
                        yield self.ta_excl_paths

                        yield Label("Comment excludes", classes="section_title")
                        yield Rule()
                        yield Label("Exclude comment prefixes (one per line):")
                        yield self.ta_excl_prefixes

                        yield Label("Language detection", classes="section_title")
                        yield Rule()
                        yield self.cb_langdetect
                        yield self.input_lang
                        yield self.input_lang_min

                        yield Label("Behavior", classes="section_title")
                        yield Rule()
                        yield self.cb_preserve_lines
                        yield self.cb_incremental

                        yield Label("Diff / Apply", classes="section_title")
                        yield Rule()
                        yield self.cb_preview_diff
                        yield self.cb_preview_before_apply
                        yield Label("Diff limit KB per file:")
                        yield self.input_diff_kb
                        yield self.cb_backups
                        yield Label("Backup dir:")
                        yield self.input_backup_dir
                        yield self.cb_overwrite_bak

                        yield Label("Persistence", classes="section_title")
                        yield Rule()
                        yield Label("Decisions file path:")
                        yield self.input_decisions_path

                        yield Label("Export", classes="section_title")
                        yield Rule()
                        yield Label("Export path (.txt/.json/.jsonl):")
                        yield self.input_export_path

                with TabPane("Results", id="tab_results"):
                    with Horizontal(id="results_root"):
                        yield self.files_tree
                        with Vertical():
                            with Horizontal(id="comments_header"):
                                yield self.lbl_comments_info
                                yield self.btn_load_more
                                yield self.btn_show_context
                            yield self.comments_list
                            yield self.context_view

                with TabPane("Diff", id="tab_diff"):
                    with Horizontal(id="diff_root"):
                        yield self.diff_files
                        yield self.diff_view

                with TabPane("Console", id="tab_console"):
                    yield self.console

    # -------- events --------
    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "scan":
            self.action_scan()
        elif bid == "stop":
            self.action_stop()
        elif bid == "diff":
            self.action_preview_diff()
        elif bid == "apply":
            self.action_apply()
        elif bid == "save":
            self.action_save_decisions()
        elif bid == "export":
            self.action_export()
        elif bid == "load_more":
            self._load_more_comments()
        elif bid == "show_context":
            self._show_context()

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        self._handle_file_tree_event(event)

    def on_tree_node_highlighted(self, event: Tree.NodeHighlighted) -> None:
        self._handle_file_tree_event(event)

    def _handle_file_tree_event(self, event) -> None:
        tree = getattr(event, "control", None) or getattr(event, "tree", None)
        if tree is not self.files_tree:
            return
        data = getattr(event.node, "data", None)
        if isinstance(data, str) and self._scan_result and data in self._scan_result.files:
            self._select_file(data)

    def on_comment_delete_changed(self, event: CommentDeleteChanged) -> None:
        if not self._scan_result:
            return
        item = event.item
        if item.excluded:
            return
        self._last_preview_fp = None
        fr = self._scan_result.files.get(item.rel_path)
        if fr:
            self._recalc_file_counters(fr)
            self._update_file_node(fr.rel_path)
            self._update_comments_header(fr)

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if event.list_view is self.diff_files:
            row = event.list_view.highlighted_child
            if isinstance(row, DiffRow):
                self.diff_view.text = self._diffs.get(row.rel_path, "")

    # -------- actions --------
    def action_cmd(self) -> None:
        self.ctx.open_command_line()

    def action_stop(self) -> None:
        for h in (self._scan_handle, self._diff_handle, self._apply_handle):
            if h and h.status == "running":
                self.ctx.tasks.stop(h.run_id)
        self.lbl_status.update("Stopping...")

    def action_scan(self) -> None:
        if self._any_running():
            self.console.write("[busy] stop running task first\n")
            return

        self._sync_settings_from_ui()
        try:
            decisions = load_decisions(self.settings.decisions_path)
        except Exception as e:
            self.console.write(f"[decisions] load failed: {e!r}\n")
            return

        snapshot = copy.deepcopy(self.settings)
        self.lbl_status.update("Scanning...")
        self.console.write("[scan] started\n")

        self._scan_handle = self.ctx.tasks.start_threaded(
            self.ctx.plugin.meta.id,
            lambda session: self._scan_worker(session, snapshot, decisions),
        )
        self._scan_handle.session.bind("log", self.console.write)

    def _scan_worker(self, session: RunSession, snapshot: CleanerSettings, decisions_db) -> int:
        log = session.stream("log")
        start = time.time()
        try:
            res = scan_project(snapshot, decisions_db, cache=self._scan_cache, log=log.write, cancelled_event=session.cancelled)
        except Exception as e:
            log.write(f"[scan] failed: {e!r}\n")
            return 1
        elapsed = time.time() - start
        log.write(f"\n[scan] done: files={res.total_files} comments={res.total_comments} in {elapsed:.2f}s\n")
        self.ctx.app.call_from_thread(self._on_scan_result, res)
        return 0

    def _on_scan_result(self, res: ScanResult) -> None:
        self._scan_result = res
        self._current_file_rel = None
        self._last_preview_fp = None

        if res.total_files == 0:
            self.lbl_status.update("Scan done: no comments found")
        else:
            self.lbl_status.update(f"Scan done: files={res.total_files} comments={res.total_comments}")

        self._rebuild_files_tree()
        self._clear_comments_view()

        if res.files:
            first_rel = sorted(res.files.keys())[0]
            self._select_file(first_rel)
            self.comments_list.focus()

    def action_save_decisions(self) -> None:
        if not self._scan_result:
            self.console.write("[decisions] nothing to save\n")
            return
        self._sync_settings_from_ui()
        out: Dict[str, Dict[str, bool]] = {}
        for rel, fr in self._scan_result.files.items():
            marked = {c.decision_key: True for c in fr.comments if c.delete and not c.excluded}
            if marked:
                out[rel] = marked
        save_decisions(self.settings.decisions_path, out)
        self.console.write(f"[decisions] saved: files={len(out)} -> {self.settings.decisions_path}\n")

    def action_export(self) -> None:
        if not self._scan_result:
            self.console.write("[export] nothing to export\n")
            return
        self._sync_settings_from_ui()
        try:
            export_report(self.settings.export_path, self._scan_result)
            self.console.write(f"[export] saved: {self.settings.export_path}\n")
        except Exception as e:
            self.console.write(f"[export] failed: {e!r}\n")

    def action_preview_diff(self) -> None:
        if self._any_running():
            self.console.write("[busy] stop running task first\n")
            return
        if not self._scan_result:
            self.console.write("[diff] scan first\n")
            return

        self._sync_settings_from_ui()
        if not self.settings.enable_preview_diff:
            self.console.write("[diff] preview diff disabled\n")
            return

        delete_map = self._build_delete_map()
        if not delete_map:
            self.console.write("[diff] nothing selected for deletion\n")
            return

        self._pre_apply_diff_pending = False
        snapshot = copy.deepcopy(self.settings)
        self.lbl_status.update("Diff preview...")
        self.console.write("[diff] started\n")

        self._diff_handle = self.ctx.tasks.start_threaded(
            self.ctx.plugin.meta.id,
            lambda session: self._diff_worker(session, snapshot, delete_map),
        )
        self._diff_handle.session.bind("log", self.console.write)

    def _diff_worker(self, session: RunSession, snapshot: CleanerSettings, delete_map: Dict[str, Set[str]]) -> int:
        log = session.stream("log")
        diffs: Dict[str, str] = {}
        preview_fp = self._fingerprint_delete_map(delete_map)

        items = list(delete_map.items())
        for i, (rel, keys) in enumerate(items, 1):
            if session.cancelled.is_set():
                log.write("[diff] cancelled\n")
                break

            fr = self._scan_result.files.get(rel) if self._scan_result else None
            if not fr:
                continue

            pr = preview_diff_file(fr.file_path, rel, snapshot, keys)
            if pr.error:
                log.write(f"[diff] {rel}: ERROR {pr.error}\n")
                continue
            if pr.changed and pr.diff_text:
                diffs[rel] = pr.diff_text

            if i % 20 == 0:
                log.write(f"[diff] {i}/{len(items)}...\n")

        self.ctx.app.call_from_thread(self._on_diff_ready, diffs, preview_fp)
        log.write(f"[diff] done. files_with_diff={len(diffs)}\n")
        return 0

    def _on_diff_ready(self, diffs: Dict[str, str], preview_fp: str) -> None:
        self._diffs = diffs
        self._last_preview_fp = preview_fp
        self.diff_files.clear()
        self.diff_view.text = ""
        for rel in sorted(diffs.keys()):
            self.diff_files.append(DiffRow(rel))
        self.lbl_status.update(f"Diff ready: files={len(diffs)}")
        if diffs:
            first = sorted(diffs.keys())[0]
            self.diff_view.text = diffs[first]
        self._switch_to_diff_tab()
        if self._pre_apply_diff_pending:
            self._pre_apply_diff_pending = False
            self._toast("Review the Diff tab, then press F8 again to write files.")

    def action_apply(self) -> None:
        if self._any_running():
            self.console.write("[busy] stop running task first\n")
            self._toast("Busy: stop the current task (F6) first.", warn=True)
            return
        if not self._scan_result:
            self.console.write("[apply] scan first\n")
            self._toast("Apply: run Scan (F5) first.", warn=True)
            return

        self._sync_settings_from_ui()
        delete_map = self._build_delete_map()
        if not delete_map:
            self.console.write("[apply] nothing selected for deletion\n")
            self._toast("Apply: select comments to delete (☐/☑ or Space).", warn=True)
            return

        snapshot = copy.deepcopy(self.settings)
        fp = self._fingerprint_delete_map(delete_map)

        if self.settings.preview_diff_before_apply:
            if fp != self._last_preview_fp:
                self._pre_apply_diff_pending = True
                self.lbl_status.update("Diff before apply...")
                self.console.write("[apply] building diff first (show diff before apply)\n")
                self._diff_handle = self.ctx.tasks.start_threaded(
                    self.ctx.plugin.meta.id,
                    lambda session: self._diff_worker(session, snapshot, delete_map),
                )
                self._diff_handle.session.bind("log", self.console.write)
                return

        self.lbl_status.update("Applying...")
        self.console.write("[apply] started\n")

        self._apply_handle = self.ctx.tasks.start_threaded(
            self.ctx.plugin.meta.id,
            lambda session: self._apply_worker(session, snapshot, delete_map),
        )
        self._apply_handle.session.bind("log", self.console.write)

    def _apply_worker(self, session: RunSession, snapshot: CleanerSettings, delete_map: Dict[str, Set[str]]) -> int:
        log = session.stream("log")
        total = len(delete_map)
        changed = 0
        errors = 0
        missing_total = 0

        for i, (rel, keys) in enumerate(delete_map.items(), 1):
            if session.cancelled.is_set():
                log.write("[apply] cancelled\n")
                break

            fr = self._scan_result.files.get(rel) if self._scan_result else None
            if not fr:
                continue

            ar = apply_file(fr.file_path, rel, snapshot, keys)
            if ar.error:
                errors += 1
                log.write(f"[apply] {rel}: ERROR {ar.error}\n")
                continue

            missing_total += ar.missing_keys
            if ar.changed:
                changed += 1

            if i % 20 == 0:
                log.write(f"[apply] {i}/{total}...\n")

        log.write(f"[apply] done. changed_files={changed}/{total} errors={errors} missing_keys={missing_total}\n")
        self.ctx.app.call_from_thread(self._on_apply_done, changed, total, errors)
        return 0

    def _on_apply_done(self, changed: int, total: int, errors: int) -> None:
        self._last_preview_fp = None
        self.lbl_status.update(f"Apply done: changed={changed}/{total} errors={errors} — rescanning...")
        self._scan_cache.clear()
        self.console.write("[scan] started (auto after apply)\n")
        self.set_timer(0.02, self._auto_rescan_after_apply)

    def _auto_rescan_after_apply(self) -> None:
        if self._any_running():
            self.set_timer(0.05, self._auto_rescan_after_apply)
            return
        self.action_scan()

    # -------- comment ops --------
    def action_select_all_file(self) -> None:
        self._bulk_current_file("all")

    def action_select_new_only_file(self) -> None:
        self._bulk_current_file("new_only")

    def action_invert_file(self) -> None:
        self._bulk_current_file("invert")

    # -------- internal helpers --------
    def _toast(self, msg: str, *, warn: bool = False) -> None:
        try:
            self.app.notify(msg, severity="warning" if warn else "information")
        except Exception:
            pass

    @staticmethod
    def _fingerprint_delete_map(dm: Dict[str, Set[str]]) -> str:
        payload = sorted((rel, sorted(keys)) for rel, keys in dm.items())
        return json.dumps(payload, ensure_ascii=False)

    def _switch_to_diff_tab(self) -> None:
        try:
            tabs = self.query_one("#tabs", TabbedContent)
            tabs.active = "tab_diff"
        except Exception:
            pass
        try:
            self.diff_files.focus()
        except Exception:
            pass

    def _any_running(self) -> bool:
        for h in (self._scan_handle, self._diff_handle, self._apply_handle):
            if h and h.status == "running":
                return True
        return False

    def _build_delete_map(self) -> Dict[str, Set[str]]:
        out: Dict[str, Set[str]] = {}
        assert self._scan_result is not None
        for rel, fr in self._scan_result.files.items():
            keys = {c.decision_key for c in fr.comments if c.delete and not c.excluded}
            if keys:
                out[rel] = keys
        return out

    def _try_clear_children(self, node: TreeNode) -> None:
        try:
            node.remove_children()
        except Exception:
            node.children.clear()

    def _rebuild_files_tree(self) -> None:
        root = self.files_tree.root
        self._try_clear_children(root)
        self._file_nodes.clear()

        if not self._scan_result or not self._scan_result.files:
            root.set_label(Text("Files (empty)", style="dim"))
            self.files_tree.refresh()
            return

        root.set_label(Text("Files", style="bold"))
        folder_nodes: Dict[tuple[str, ...], TreeNode] = {(): root}

        for rel, fr in sorted(self._scan_result.files.items(), key=lambda kv: kv[0]):
            parts = tuple(rel.split("/"))
            parent = root
            for depth in range(0, len(parts) - 1):
                key = parts[: depth + 1]
                if key in folder_nodes:
                    parent = folder_nodes[key]
                else:
                    node = parent.add(parts[depth], data=None, expand=False)
                    folder_nodes[key] = node
                    parent = node

            node = parent.add(self._file_label(fr), data=rel, expand=False)
            self._file_nodes[rel] = node

        root.expand()
        self.files_tree.refresh()

    def _file_label(self, fr: FileRecord) -> Text:
        counters = f"[t={fr.total} d={fr.to_delete} new={fr.new} excl={fr.excluded}]"
        style = "yellow" if fr.to_delete > 0 else "white"
        return Text(f"{fr.rel_path}  {counters}", style=style)

    def _update_file_node(self, rel: str) -> None:
        if not self._scan_result:
            return
        fr = self._scan_result.files.get(rel)
        node = self._file_nodes.get(rel)
        if fr and node:
            node.set_label(self._file_label(fr))
            self.files_tree.refresh()

    def _clear_comments_view(self) -> None:
        self.comments_list.clear()
        self.lbl_comments_info.update("No file selected")
        self.btn_load_more.disabled = True
        self.context_view.text = ""

    def _update_comments_header(self, fr: FileRecord) -> None:
        name = Path(fr.rel_path).name
        self.lbl_comments_info.update(
            f"{name}  {fr.visible_count}/{fr.total}  del={fr.to_delete} new={fr.new} excl={fr.excluded}"
        )
        self.btn_load_more.disabled = fr.visible_count >= fr.total

    def _select_file(self, rel: str) -> None:
        if not self._scan_result:
            return
        self._current_file_rel = rel
        fr = self._scan_result.files[rel]
        self._rebuild_comments_list(fr)
        self.comments_list.focus()

    def _rebuild_comments_list(self, fr: FileRecord) -> None:
        self.comments_list.clear()
        for c in fr.comments[: fr.visible_count]:
            self.comments_list.append(CommentRow(c))
        self._update_comments_header(fr)

    def _load_more_comments(self) -> None:
        if not self._scan_result or not self._current_file_rel:
            return
        fr = self._scan_result.files[self._current_file_rel]
        if fr.visible_count >= fr.total:
            self.console.write("[comments] no more to load\n")
            return
        fr.visible_count = min(fr.total, fr.visible_count + self.settings.page_size)
        self._rebuild_comments_list(fr)

    def _recalc_file_counters(self, fr: FileRecord) -> None:
        fr.to_delete = sum(1 for x in fr.comments if x.delete)
        fr.excluded = sum(1 for x in fr.comments if x.excluded)
        fr.new = sum(1 for x in fr.comments if x.is_new and not x.excluded)
        fr.total = len(fr.comments)

    def _bulk_current_file(self, mode: str) -> None:
        if not self._scan_result or not self._current_file_rel:
            return
        self._last_preview_fp = None
        fr = self._scan_result.files[self._current_file_rel]
        for c in fr.comments:
            if c.excluded:
                continue
            if mode == "all":
                c.delete = True
            elif mode == "new_only":
                c.delete = bool(c.is_new)
            elif mode == "invert":
                c.delete = not c.delete

        self._recalc_file_counters(fr)
        self._update_file_node(fr.rel_path)
        self._rebuild_comments_list(fr)

    def _show_context(self) -> None:
        row = self.comments_list.highlighted_child
        if not isinstance(row, CommentRow):
            return
        c = row.item
        try:
            text = c.file_path.read_text(encoding="utf-8", errors="replace")
            lines = text.splitlines()
            start = max(1, c.start_line - 5)
            end = min(len(lines), c.end_line + 5)
            out = []
            for ln in range(start, end + 1):
                prefix = ">> " if c.start_line <= ln <= c.end_line else "   "
                out.append(f"{prefix}{ln:5d}: {lines[ln-1]}")
            self.context_view.text = "\n".join(out)
        except Exception as e:
            self.context_view.text = f"Failed to load context: {e!r}"

    # -------- settings sync --------
    def _sync_settings_from_ui(self) -> None:
        s = self.settings
        s.selected_paths = self.paths_tree.get_selected()
        s.include_patterns = (self.input_include.value or "*").strip() or "*"

        md = (self.input_max_depth.value or "").strip()
        s.max_depth = int(md) if md.isdigit() else None

        s.exclude_dirs = [x.strip() for x in self.ta_excl_dirs.text.splitlines() if x.strip()]
        s.exclude_names = [x.strip() for x in self.ta_excl_names.text.splitlines() if x.strip()]
        s.exclude_path_patterns = [x.strip() for x in self.ta_excl_paths.text.splitlines() if x.strip()]
        s.exclude_comment_prefixes = [x.strip() for x in self.ta_excl_prefixes.text.splitlines() if x.strip()]

        s.use_langdetect = bool(self.cb_langdetect.value)
        s.langdetect_language = (self.input_lang.value or "").strip()
        ml = (self.input_lang_min.value or "").strip()
        if ml.isdigit():
            s.min_langdetect_len = int(ml)

        s.preserve_line_count = bool(self.cb_preserve_lines.value)
        s.incremental_by_mtime = bool(self.cb_incremental.value)

        s.enable_preview_diff = bool(self.cb_preview_diff.value)
        s.preview_diff_before_apply = bool(self.cb_preview_before_apply.value)
        kb = (self.input_diff_kb.value or "").strip()
        if kb.isdigit():
            s.diff_max_kb_per_file = int(kb)

        s.make_backups = bool(self.cb_backups.value)
        s.backup_dir = Path((self.input_backup_dir.value or "").strip() or ".codingutils/backups")
        s.overwrite_backups = bool(self.cb_overwrite_bak.value)

        dp = (self.input_decisions_path.value or "").strip()
        s.decisions_path = Path(dp) if dp else Path(".codingutils/comment_cleaner.json")

        ep = (self.input_export_path.value or "").strip()
        s.export_path = Path(ep) if ep else Path(".codingutils/comment_cleaner_report.json")