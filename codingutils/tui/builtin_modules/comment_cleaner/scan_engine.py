from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from codingutils.common_utils import (
    FilterConfig,
    FileContentDetector,
    FileSystemWalker,
    FileType,
    GitIgnoreParser,
    get_relative_path,
)
from codingutils.comment_extractor import CommentMatch, CommentScanner, CommentStyle

from .decisions import DecisionsDB, decision_key
from .models import CleanerSettings, CommentItem, FileRecord, ScanResult, NodeSelectMode

try:
    from langdetect import detect, LangDetectException  # type: ignore
    LANGDETECT_AVAILABLE = True
except Exception:
    LANGDETECT_AVAILABLE = False
    detect = None
    LangDetectException = Exception


# -------- Public helpers used by apply_engine --------
def make_context(lines: List[str], start_line: int, end_line: int, *, before: int = 2, after: int = 2) -> Tuple[str, str]:
    s = max(1, start_line - before)
    e = min(len(lines), end_line + after)
    before_txt = "".join(lines[s - 1 : start_line - 1])
    after_txt = "".join(lines[end_line : e])
    return before_txt, after_txt


def make_signature(kind: str, text: str, before_txt: str, after_txt: str, cell_index: Optional[int]) -> str:
    cell = "None" if cell_index is None else str(int(cell_index))
    blob = f"{kind}\ncell={cell}\n{text}\n--before--\n{before_txt}\n--after--\n{after_txt}"
    return hashlib.sha1(blob.encode("utf-8", errors="ignore")).hexdigest()


def comment_style_for_file(settings: CleanerSettings, file_path: Path, *, ext_override: Optional[str] = None) -> CommentStyle:
    if settings.syntax_mode == "custom":
        line = (settings.custom_line_marker or "").strip()
        blocks: List[Tuple[str, str]] = []
        if settings.custom_block_start.strip() and settings.custom_block_end.strip():
            blocks.append((settings.custom_block_start.strip(), settings.custom_block_end.strip()))
        if settings.custom_alt_block_start.strip() and settings.custom_alt_block_end.strip():
            blocks.append((settings.custom_alt_block_start.strip(), settings.custom_alt_block_end.strip()))
        return CommentStyle(line_markers=(line,) if line else (), block_markers=tuple(blocks))

    ext = ext_override or file_path.suffix
    style = CommentStyle.from_extension(ext)
    if not style.line_markers and not style.block_markers:
        return CommentStyle(line_markers=("#",), block_markers=())
    return style


def is_full_line_prefix_whitespace(lines: List[str], m: CommentMatch) -> bool:
    try:
        prefix = lines[m.start_line - 1][: m.start_col]
    except Exception:
        return False
    return prefix.strip() == ""


# -------- internal helpers --------
@dataclass(slots=True)
class ScanCacheEntry:
    mtime: float
    settings_fingerprint: str
    items: List[CommentItem]


def _fingerprint_settings(s: CleanerSettings) -> str:
    blob = json.dumps(
        {
            "include": s.include_patterns,
            "recursive_default": s.recursive_default,
            "max_depth": s.max_depth,
            "exclude_dirs": s.exclude_dirs,
            "exclude_names": s.exclude_names,
            "exclude_path_patterns": s.exclude_path_patterns,
            "use_gitignore": s.use_gitignore,
            "custom_gitignore": str(s.custom_gitignore) if s.custom_gitignore else "",
            "ignore_gitignore": s.ignore_gitignore,
            "syntax_mode": s.syntax_mode,
            "custom": [
                s.custom_line_marker,
                s.custom_block_start,
                s.custom_block_end,
                s.custom_alt_block_start,
                s.custom_alt_block_end,
            ],
            "exclude_prefixes": s.exclude_comment_prefixes,
            "langdetect": s.use_langdetect,
            "lang": s.langdetect_language,
            "min_len": s.min_langdetect_len,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()


def _normalize_for_langdetect(text: str) -> str:
    import re
    s = re.sub(r"\b(def|class|function|var|let|const|import|from|return|if|else)\b", " ", text, flags=re.I)
    s = re.sub(r"[^\w\s]+", " ", s, flags=re.UNICODE)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _detect_lang(s: CleanerSettings, text: str) -> str:
    if not s.use_langdetect:
        return ""
    if not LANGDETECT_AVAILABLE:
        return ""
    cleaned = _normalize_for_langdetect(text)
    if len(cleaned) < int(s.min_langdetect_len):
        return ""
    try:
        return str(detect(cleaned)).lower()  # type: ignore[misc]
    except LangDetectException:
        return ""


def _is_excluded(raw_comment: str, prefixes: List[str]) -> bool:
    for p in prefixes:
        if p and raw_comment.startswith(p):
            return True
    return False


def _group_line_comments(
    lines: List[str],
    matches: List[CommentMatch],
    *,
    prefixes: List[str],
    file_path: Path,
    rel_path: str,
    cell_index: Optional[int],
    settings: CleanerSettings,
    decisions: DecisionsDB,
) -> List[CommentItem]:
    block_matches: List[CommentMatch] = []
    line_matches: List[CommentMatch] = []

    for m in matches:
        if m.kind == "block":
            block_matches.append(m)
        else:
            line_matches.append(m)

    eligible: Dict[int, CommentMatch] = {}
    inline: List[CommentMatch] = []

    for m in line_matches:
        if is_full_line_prefix_whitespace(lines, m):
            eligible[m.start_line] = m
        else:
            inline.append(m)

    items: List[CommentItem] = []
    sorted_lines = sorted(eligible.keys())
    used_lines: set[int] = set()

    def make_item(m: CommentMatch, kind: str, text: str, raw: str, start_line: int, end_line: int, start_col: int, end_col: int) -> CommentItem:
        excluded = _is_excluded(raw, prefixes)
        before_txt, after_txt = make_context(lines, start_line, end_line, before=2, after=2)
        sig = make_signature(kind, text, before_txt, after_txt, cell_index)
        key = decision_key(sig, cell_index)
        delete = bool(decisions.decisions.get(rel_path, {}).get(key, False))
        if excluded:
            delete = False
        lang = _detect_lang(settings, text)
        return CommentItem(
            id=f"{rel_path}:{cell_index}:{start_line}:{start_col}:{kind}",
            file_path=file_path,
            rel_path=rel_path,
            cell_index=cell_index,
            kind=kind,
            start_line=start_line,
            start_col=start_col,
            end_line=end_line,
            end_col=end_col,
            raw=raw,
            text=text,
            signature=sig,
            decision_key=key,
            excluded=excluded,
            excluded_reason="prefix" if excluded else "",
            lang=lang,
            is_new=not delete,
            delete=delete,
        )

    i = 0
    while i < len(sorted_lines):
        line_no = sorted_lines[i]
        if line_no in used_lines:
            i += 1
            continue

        run = [line_no]
        j = i + 1
        while j < len(sorted_lines) and sorted_lines[j] == run[-1] + 1:
            run.append(sorted_lines[j])
            j += 1

        if len(run) >= 2:
            ms = [eligible[ln] for ln in run]
            used_lines.update(run)

            start = ms[0]
            end = ms[-1]

            raw = "\n".join(m.raw.rstrip("\n") for m in ms) + "\n"
            text = "\n".join(m.text for m in ms)

            items.append(
                make_item(
                    start,
                    "line_group",
                    text=text,
                    raw=raw,
                    start_line=start.start_line,
                    end_line=end.end_line,
                    start_col=start.start_col,
                    end_col=end.end_col,
                )
            )
        else:
            m = eligible[line_no]
            used_lines.add(line_no)
            items.append(make_item(m, "line", m.text, m.raw, m.start_line, m.end_line, m.start_col, m.end_col))

        i = j

    for m in inline:
        items.append(make_item(m, "line", m.text, m.raw, m.start_line, m.end_line, m.start_col, m.end_col))

    for m in block_matches:
        items.append(make_item(m, "block", m.text, m.raw, m.start_line, m.end_line, m.start_col, m.end_col))

    items.sort(key=lambda x: (x.start_line, x.start_col, x.kind))
    return items


def scan_text_file(
    file_path: Path,
    settings: CleanerSettings,
    decisions: DecisionsDB,
    *,
    rel_path: str,
    prefixes: List[str],
) -> List[CommentItem]:
    if FileContentDetector.detect_file_type(file_path) != FileType.TEXT:
        return []

    enc = FileContentDetector.detect_encoding(file_path)
    text = file_path.read_text(encoding=enc, errors="replace")
    lines = text.splitlines(keepends=True)

    style = comment_style_for_file(settings, file_path)
    scanner = CommentScanner(style, exclude_comment_pattern=None)

    _out_lines, matches, _ = scanner.scan_and_strip(
        lines, remove=False, should_remove=lambda _m: False, cell_index=None
    )

    return _group_line_comments(
        lines,
        matches,
        prefixes=prefixes,
        file_path=file_path,
        rel_path=rel_path,
        cell_index=None,
        settings=settings,
        decisions=decisions,
    )


def scan_project(
    settings: CleanerSettings,
    decisions: DecisionsDB,
    *,
    cache: Dict[Path, ScanCacheEntry],
    log: Optional[callable] = None,
    cancelled_event=None,
) -> ScanResult:
    prefixes = [p for p in settings.exclude_comment_prefixes if p.strip()]
    roots, rec_map = build_roots_and_recursion(settings)

    walker = _build_walker(settings, roots)
    recursive_arg = {k.resolve(): v for k, v in rec_map.items()} if rec_map else settings.recursive_default
    files = walker.find_files(roots, recursive=recursive_arg)

    settings_fp = _fingerprint_settings(settings)
    results: Dict[str, FileRecord] = {}
    total_comments = 0
    errors: List[str] = []

    for idx, f in enumerate(files, 1):
        if cancelled_event is not None and getattr(cancelled_event, "is_set", lambda: False)():
            break

        rel = get_relative_path(f)
        if log and idx % 100 == 0:
            log(f"[scan] {idx}/{len(files)}: {rel}\n")

        try:
            mtime = f.stat().st_mtime
        except Exception:
            mtime = -1.0

        items: List[CommentItem]
        if settings.incremental_by_mtime:
            ce = cache.get(f)
            if ce and ce.mtime == mtime and ce.settings_fingerprint == settings_fp:
                items = ce.items
            else:
                items = scan_text_file(f, settings, decisions, rel_path=rel, prefixes=prefixes)
                cache[f] = ScanCacheEntry(mtime=mtime, settings_fingerprint=settings_fp, items=items)
        else:
            items = scan_text_file(f, settings, decisions, rel_path=rel, prefixes=prefixes)

        if not items:
            continue

        fr = FileRecord(file_path=f, rel_path=rel)
        fr.comments = items
        fr.total = len(items)
        fr.excluded = sum(1 for x in items if x.excluded)
        fr.to_delete = sum(1 for x in items if x.delete)
        fr.new = sum(1 for x in items if x.is_new and not x.excluded)
        fr.visible_count = min(settings.page_size, len(items))

        results[rel] = fr
        total_comments += fr.total

    return ScanResult(files=results, total_files=len(results), total_comments=total_comments, scan_errors=errors)


def _build_walker(settings: CleanerSettings, roots: List[Path]) -> FileSystemWalker:
    config = FilterConfig(
        directories=[str(p) for p in roots],
        include_pattern=settings.include_patterns,
        recursive=settings.recursive_default,
        exclude_dirs=set(settings.exclude_dirs),
        exclude_names=set(settings.exclude_names),
        exclude_patterns=set(settings.exclude_path_patterns),
        max_depth=settings.max_depth,
        use_gitignore=False,
        custom_gitignore=None,
    )

    parser: Optional[GitIgnoreParser] = None
    if settings.use_gitignore and not settings.ignore_gitignore:
        root_dir = roots[0].resolve() if roots else Path.cwd().resolve()
        parser = GitIgnoreParser(root_dir=root_dir)
        if settings.custom_gitignore:
            parser.load_from_file(settings.custom_gitignore)
        else:
            parser.load_from_file()

    return FileSystemWalker(config, parser)


def build_roots_and_recursion(settings: CleanerSettings) -> Tuple[List[Path], Dict[Path, bool]]:
    roots: List[Path] = []
    rec_map: Dict[Path, bool] = {}

    for p, mode in settings.selected_paths.items():
        try:
            rp = p.resolve()
        except Exception:
            rp = Path(p)

        if mode == NodeSelectMode.NONE:
            continue

        roots.append(rp)

        if rp.is_dir():
            rec_map[rp] = (mode == NodeSelectMode.RECURSIVE)

    if not roots:
        roots = [Path.cwd().resolve()]
        rec_map[roots[0]] = bool(settings.recursive_default)

    return roots, rec_map