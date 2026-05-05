from __future__ import annotations

import difflib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

from codingutils.common_utils import FileContentDetector
from codingutils.comment_extractor import CommentScanner, CommentStyle, CommentMatch

from .models import CleanerSettings
from .decisions import decision_key
from .scan_engine import make_context, make_signature, comment_style_for_file, is_full_line_prefix_whitespace


@dataclass(slots=True)
class PreviewResult:
    rel_path: str
    file_path: Path
    changed: bool
    diff_text: str
    removed_count: int
    missing_keys: int
    error: str = ""


@dataclass(slots=True)
class ApplyResult:
    rel_path: str
    file_path: Path
    changed: bool
    removed_count: int
    missing_keys: int
    backup_path: Optional[Path] = None
    error: str = ""


def _is_excluded(raw: str, prefixes: List[str]) -> bool:
    for p in prefixes:
        if p and raw.startswith(p):
            return True
    return False


def _is_full_line_match(lines: List[str], m: CommentMatch) -> bool:
    """Is comment the only thing on its line(s), ignoring whitespace?"""
    try:
        if lines[m.start_line - 1][: m.start_col].strip():
            return False
        # end line suffix
        end_line = lines[m.end_line - 1]
        if end_line[m.end_col :].strip():
            return False
        # for multi-line block: intermediate lines are inside comment anyway
        return True
    except Exception:
        return False


def _group_keys_for_line_matches(
    lines: List[str],
    line_matches: List[CommentMatch],
    *,
    prefixes: List[str],
    cell_index: Optional[int],
) -> Tuple[Dict[int, str], Set[str], Set[int]]:
    """
    Build mapping line_no -> group_decision_key for eligible consecutive full-line line-comments.
    Returns:
      line_to_group_key,
      group_keys_set,
      full_line_drop_lines (lines that are safe to drop if preserve_line_count=False)
    """
    eligible: Dict[int, CommentMatch] = {}
    for m in line_matches:
        if is_full_line_prefix_whitespace(lines, m):  # full-line line-comment (prefix whitespace only)
            eligible[m.start_line] = m

    sorted_lines = sorted(eligible.keys())
    line_to_group_key: Dict[int, str] = {}
    group_keys: Set[str] = set()
    drop_lines: Set[int] = set()

    i = 0
    while i < len(sorted_lines):
        run = [sorted_lines[i]]
        j = i + 1
        while j < len(sorted_lines) and sorted_lines[j] == run[-1] + 1:
            run.append(sorted_lines[j])
            j += 1

        if len(run) >= 2:
            ms = [eligible[ln] for ln in run]
            start = ms[0]
            end = ms[-1]

            excluded = any(_is_excluded(m.raw, prefixes) for m in ms)
            # signature of the group
            text = "\n".join(m.text for m in ms)
            before_txt, after_txt = make_context(lines, start.start_line, end.end_line, before=2, after=2)
            sig = make_signature("line_group", text, before_txt, after_txt, cell_index)
            key = decision_key(sig, cell_index)

            if not excluded:
                group_keys.add(key)

            for ln in run:
                line_to_group_key[ln] = key
                drop_lines.add(ln)  # full-line comments -> safe to drop if asked

        else:
            # single eligible line-comment -> not a group; dropping handled per match
            pass

        i = j

    return line_to_group_key, group_keys, drop_lines


def _strip_text_with_keys(
    *,
    lines: List[str],
    style: CommentStyle,
    settings: CleanerSettings,
    delete_keys: Set[str],
    prefixes: List[str],
    cell_index: Optional[int],
) -> Tuple[List[str], int, int]:
    """
    Returns (out_lines, removed_count, missing_keys_count)
    Uses CommentScanner remove=True and should_remove based on decision_key(signature).
    """
    scanner = CommentScanner(style, exclude_comment_pattern=None)

    # pre-scan matches to build group mapping
    _out0, matches0, _ = scanner.scan_and_strip(
        lines,
        remove=False,
        should_remove=lambda _m: False,
        cell_index=cell_index,
    )

    line_matches = [m for m in matches0 if m.kind == "line"]
    block_matches = [m for m in matches0 if m.kind == "block"]

    line_to_group_key, _group_keys, drop_lines_from_groups = _group_keys_for_line_matches(
        lines, line_matches, prefixes=prefixes, cell_index=cell_index
    )

    encountered_keys: Set[str] = set()
    removed_count = 0
    drop_lines: Set[int] = set(drop_lines_from_groups)

    def should_remove(m: CommentMatch) -> bool:
        nonlocal removed_count
        raw = m.raw
        if _is_excluded(raw, prefixes):
            return False

        # determine key
        if m.kind == "line" and m.start_line in line_to_group_key:
            key = line_to_group_key[m.start_line]
            encountered_keys.add(key)
            do = key in delete_keys
            if do:
                removed_count += 1
            return do

        before_txt, after_txt = make_context(lines, m.start_line, m.end_line, before=2, after=2)
        sig = make_signature(m.kind, m.text, before_txt, after_txt, cell_index)
        key = decision_key(sig, cell_index)
        encountered_keys.add(key)

        do = key in delete_keys
        if do:
            removed_count += 1
            # mark droppable lines if full-line
            if _is_full_line_match(lines, m):
                for ln in range(m.start_line, m.end_line + 1):
                    drop_lines.add(ln)
        return do

    out_lines, _matches_removed, _removed_count_from_scanner = scanner.scan_and_strip(
        lines,
        remove=True,
        should_remove=should_remove,
        cell_index=cell_index,
    )

    # If preserve_line_count=False: drop full-line comment lines completely
    if not settings.preserve_line_count and drop_lines:
        new_out: List[str] = []
        for idx, line in enumerate(out_lines, start=1):
            if idx in drop_lines and line.strip() == "":
                continue
            new_out.append(line)
        out_lines = new_out

    missing = len(delete_keys - encountered_keys)
    return out_lines, removed_count, missing


def _unified_diff(rel_path: str, before: str, after: str) -> str:
    a = before.splitlines(keepends=True)
    b = after.splitlines(keepends=True)
    diff = difflib.unified_diff(a, b, fromfile=rel_path + ":before", tofile=rel_path + ":after")
    return "".join(diff)


def _backup_target(backup_dir: Path, rel_path: str) -> Path:
    rel = Path(rel_path)
    return (backup_dir / rel).with_name(rel.name + ".bak")


def _next_backup_version(p: Path) -> Path:
    i = 1
    while True:
        cand = Path(str(p) + f".{i}")
        if not cand.exists():
            return cand
        i += 1


def make_backup(src: Path, *, backup_dir: Path, rel_path: str, overwrite: bool) -> Optional[Path]:
    if not src.exists():
        return None
    target = _backup_target(backup_dir, rel_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if overwrite:
            try:
                target.unlink()
            except Exception:
                target = _next_backup_version(target)
        else:
            target = _next_backup_version(target)
    shutil.copy2(src, target)
    return target


def preview_diff_file(
    file_path: Path,
    rel_path: str,
    settings: CleanerSettings,
    delete_keys: Set[str],
) -> PreviewResult:
    prefixes = [p for p in settings.exclude_comment_prefixes if p.strip()]

    try:
        if file_path.suffix.lower() == ".ipynb":
            before = file_path.read_text(encoding="utf-8", errors="replace")
            after, removed, missing = _process_ipynb_preview(before, file_path, rel_path, settings, delete_keys, prefixes)
        else:
            enc = FileContentDetector.detect_encoding(file_path)
            before = file_path.read_text(encoding=enc, errors="replace")
            lines = before.splitlines(keepends=True)
            style = comment_style_for_file(settings, file_path)
            out_lines, removed, missing = _strip_text_with_keys(
                lines=lines, style=style, settings=settings, delete_keys=delete_keys, prefixes=prefixes, cell_index=None
            )
            after = "".join(out_lines)

        changed = before != after
        diff_text = _unified_diff(rel_path, before, after) if changed else ""
        # size limit
        if diff_text and (len(diff_text.encode("utf-8")) > settings.diff_max_kb_per_file * 1024):
            diff_text = f"[diff too large for {rel_path}]\n"

        return PreviewResult(
            rel_path=rel_path,
            file_path=file_path,
            changed=changed,
            diff_text=diff_text,
            removed_count=removed,
            missing_keys=missing,
        )
    except Exception as e:
        return PreviewResult(rel_path=rel_path, file_path=file_path, changed=False, diff_text="", removed_count=0, missing_keys=0, error=repr(e))


def apply_file(
    file_path: Path,
    rel_path: str,
    settings: CleanerSettings,
    delete_keys: Set[str],
) -> ApplyResult:
    prefixes = [p for p in settings.exclude_comment_prefixes if p.strip()]
    backup_path: Optional[Path] = None

    try:
        if settings.make_backups:
            backup_path = make_backup(
                file_path,
                backup_dir=settings.backup_dir,
                rel_path=rel_path,
                overwrite=settings.overwrite_backups,
            )

        if file_path.suffix.lower() == ".ipynb":
            before = file_path.read_text(encoding="utf-8", errors="replace")
            after, removed, missing = _process_ipynb_preview(before, file_path, rel_path, settings, delete_keys, prefixes)
            changed = before != after
            if changed:
                file_path.write_text(after, encoding="utf-8")
            return ApplyResult(rel_path=rel_path, file_path=file_path, changed=changed, removed_count=removed, missing_keys=missing, backup_path=backup_path)

        enc = FileContentDetector.detect_encoding(file_path)
        before = file_path.read_text(encoding=enc, errors="replace")
        lines = before.splitlines(keepends=True)
        style = comment_style_for_file(settings, file_path)

        out_lines, removed, missing = _strip_text_with_keys(
            lines=lines, style=style, settings=settings, delete_keys=delete_keys, prefixes=prefixes, cell_index=None
        )
        after = "".join(out_lines)
        changed = before != after

        if changed:
            file_path.write_text(after, encoding=enc)

        return ApplyResult(
            rel_path=rel_path,
            file_path=file_path,
            changed=changed,
            removed_count=removed,
            missing_keys=missing,
            backup_path=backup_path,
        )
    except Exception as e:
        return ApplyResult(rel_path=rel_path, file_path=file_path, changed=False, removed_count=0, missing_keys=0, backup_path=backup_path, error=repr(e))


def _process_ipynb_preview(
    nb_text: str,
    file_path: Path,
    rel_path: str,
    settings: CleanerSettings,
    delete_keys: Set[str],
    prefixes: List[str],
) -> Tuple[str, int, int]:
    """
    Apply stripping to code cells and return new notebook json string.
    """
    try:
        nb = json.loads(nb_text)
    except Exception:
        return nb_text, 0, 0

    cells = nb.get("cells", [])
    if not isinstance(cells, list):
        return nb_text, 0, 0

    removed_total = 0
    missing_total = 0
    modified = False

    for idx, cell in enumerate(cells):
        if not isinstance(cell, dict) or cell.get("cell_type") != "code":
            continue
        src = cell.get("source", "")
        src_is_list = isinstance(src, list)

        if src_is_list:
            cell_text = "".join(str(x) for x in src)
        else:
            cell_text = str(src)

        lines = cell_text.splitlines(keepends=True)
        style = comment_style_for_file(settings, file_path, ext_override=".py")  # best-effort

        out_lines, removed, missing = _strip_text_with_keys(
            lines=lines,
            style=style,
            settings=settings,
            delete_keys=delete_keys,
            prefixes=prefixes,
            cell_index=idx,
        )
        new_text = "".join(out_lines)

        removed_total += removed
        missing_total += missing

        if new_text != cell_text:
            modified = True
            if src_is_list:
                # keep list-of-lines representation
                cell["source"] = new_text.splitlines(keepends=True)
            else:
                cell["source"] = new_text

    if not modified:
        return nb_text, removed_total, missing_total

    return json.dumps(nb, ensure_ascii=False, indent=1), removed_total, missing_total