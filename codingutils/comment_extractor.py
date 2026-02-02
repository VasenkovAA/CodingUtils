"""
comment_extractor — advanced comment extractor/remover.

Features:
- File discovery via FileSystemWalker (+ optional gitignore)
- Detect line and block comments (incl. multi-line blocks)
- Preview mode: shows what would be removed, does not change files
- Optional language filter via langdetect
- Export found comments to .txt/.json/.jsonl
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from codingutils.common_utils import (
    FilterConfig,
    FileContentDetector,
    FileSystemWalker,
    FileType,
    GitIgnoreParser,
    ProgressReporter,
    get_relative_path,
    safe_write,
)

try:
    from langdetect import detect, LangDetectException
    LANGDETECT_AVAILABLE = True
except ImportError:
    LANGDETECT_AVAILABLE = False
    detect = None
    LangDetectException = Exception


logger = logging.getLogger(__name__)






@dataclass(slots=True)
class CommentExtractorConfig(FilterConfig):
    """
    comment_symbols override format (optional):
      - "//"            -> line comment only
      - "/* */"         -> block comment only
      - "// /* */"      -> line + block
    """

    comment_symbols: Optional[str] = None
    exclude_comment_pattern: Optional[str] = None
    language_filter: Optional[str] = None

    remove_comments: bool = False
    preview_mode: bool = False

    export_file: Optional[Path] = None
    log_file: Optional[Path] = None

    use_cache: bool = True
    min_langdetect_len: int = 20


    keep_backups: bool = False
    backup_dir: Optional[Path] = None
    overwrite_backups: bool = False

    def __post_init__(self) -> None:

        FilterConfig.__post_init__(self)

        if self.language_filter and not LANGDETECT_AVAILABLE:
            logger.warning("langdetect not available. Install with: pip install langdetect")


        if self.backup_dir is not None:
            self.keep_backups = True






@dataclass(slots=True)
class CommentMatch:
    kind: str
    start_line: int
    start_col: int
    end_line: int
    end_col: int
    raw: str
    text: str
    cell_index: Optional[int] = None


@dataclass(slots=True)
class CommentStyle:
    line_markers: Tuple[str, ...] = ()
    block_markers: Tuple[Tuple[str, str], ...] = ()

    @staticmethod
    def from_extension(ext: str) -> "CommentStyle":
        style = FileContentDetector.get_comment_style(Path(f"dummy{ext}")) or {}
        lines: Tuple[str, ...] = (style["line"],) if style.get("line") else ()
        blocks: List[Tuple[str, str]] = []
        if style.get("block"):
            blocks.append(tuple(style["block"]))
        if style.get("alt_block"):
            blocks.append(tuple(style["alt_block"]))
        return CommentStyle(line_markers=lines, block_markers=tuple(blocks))

    @staticmethod
    def from_override(spec: str) -> "CommentStyle":
        parts = spec.strip().split()
        if not parts:
            return CommentStyle()
        if len(parts) == 1:
            return CommentStyle(line_markers=(parts[0],), block_markers=())
        if len(parts) == 2:
            return CommentStyle(line_markers=(), block_markers=((parts[0], parts[1]),))
        return CommentStyle(line_markers=(parts[0],), block_markers=((parts[1], parts[2]),))






class _StringScanner:
    """Find tokens outside simple single-line strings."""
    QUOTES = ('"', "'", "`")

    @classmethod
    def find_next_token_outside_strings(
        cls,
        line: str,
        start: int,
        tokens: Sequence[str],
    ) -> Tuple[int, Optional[str]]:
        if not tokens:
            return -1, None

        in_str = False
        quote: Optional[str] = None
        i = start

        while i < len(line):
            ch = line[i]

            if in_str and ch == "\\":
                i += 2
                continue

            if ch in cls.QUOTES:
                if not in_str:
                    in_str = True
                    quote = ch
                elif quote == ch:
                    in_str = False
                    quote = None
                i += 1
                continue

            if not in_str:
                for tok in tokens:
                    if tok and line.startswith(tok, i):
                        return i, tok

            i += 1

        return -1, None






class CommentScanner:
    """
    Extract and optionally strip comments.

    Supports:
    - multiple comments per line (e.g. block then line)
    - multi-line block comments
    - exclude_comment_pattern (prefix applied to raw comment starting at marker position)

    Behavior on unclosed block comment:
    - remove=True: treat until EOF as comment and strip it, preserving line count
    - remove=False: keep original content, but emit warning
    """

    def __init__(self, style: CommentStyle, *, exclude_comment_pattern: Optional[str] = None) -> None:
        self.style = style
        self.exclude_comment_pattern = exclude_comment_pattern


        self._in_block = False
        self._block_end_tok = ""
        self._block_start_line = 0
        self._block_start_col = 0
        self._block_prefix_before_start = ""
        self._block_original_lines: List[str] = []
        self._block_raw_parts: List[str] = []

    def scan_and_strip(
        self,
        lines: Iterable[str],
        *,
        remove: bool,
        should_remove: "callable[[CommentMatch], bool]",
        cell_index: Optional[int] = None,
    ) -> Tuple[List[str], List[CommentMatch], int]:
        out_lines: List[str] = []
        matches: List[CommentMatch] = []
        removed_count = 0

        for line_no, raw_line in enumerate(lines, 1):
            if self._in_block:
                flushed, new_matches, removed_delta = self._process_line_in_block(
                    line_no, raw_line, remove=remove, should_remove=should_remove, cell_index=cell_index
                )
                out_lines.extend(flushed)
                matches.extend(new_matches)
                removed_count += removed_delta
                continue

            flushed, new_matches, removed_delta = self._process_line_no_block(
                line_no, raw_line, remove=remove, should_remove=should_remove, cell_index=cell_index
            )
            out_lines.extend(flushed)
            matches.extend(new_matches)
            removed_count += removed_delta


        if self._in_block:
            logger.warning("Unclosed block comment starting at line %d", self._block_start_line)
            if remove:

                out_lines.append(self._block_prefix_before_start.rstrip() + "\n")
                out_lines.extend(["\n"] * max(0, len(self._block_original_lines) - 1))
            else:
                out_lines.extend(self._block_original_lines)
            self._reset_block_state()

        return out_lines, matches, removed_count

    def _process_line_no_block(
        self,
        line_no: int,
        raw_line: str,
        *,
        remove: bool,
        should_remove: "callable[[CommentMatch], bool]",
        cell_index: Optional[int] = None,
    ) -> Tuple[List[str], List[CommentMatch], int]:
        nl = "\n" if raw_line.endswith("\n") else ""
        line = raw_line[:-1] if nl else raw_line

        tokens: List[str] = []
        tokens.extend(self.style.line_markers)
        tokens.extend([s for s, _e in self.style.block_markers])

        out = line
        i = 0
        matches: List[CommentMatch] = []
        removed = 0

        while i < len(out):
            pos, tok = _StringScanner.find_next_token_outside_strings(out, i, tokens)
            if pos == -1 or tok is None:
                break


            if tok in self.style.line_markers:
                raw_comment = out[pos:]
                if self._is_excluded(raw_comment):

                    return [raw_line], matches, removed

                m = CommentMatch(
                    kind="line",
                    start_line=line_no,
                    start_col=pos,
                    end_line=line_no,
                    end_col=len(out),
                    raw=raw_comment,
                    text=self._clean_comment_text(raw_comment, kind="line"),
                    cell_index=cell_index,
                )
                matches.append(m)

                if remove and should_remove(m):
                    removed += 1
                    out = out[:pos].rstrip()
                    break

                i = pos + len(tok)
                continue


            end_tok = self._end_for_start(tok)
            if not end_tok:
                i = pos + len(tok)
                continue

            end_pos = out.find(end_tok, pos + len(tok))
            if end_pos != -1:
                end_col = end_pos + len(end_tok)
                raw_comment = out[pos:end_col]

                if self._is_excluded(raw_comment):
                    i = end_col
                    continue

                m = CommentMatch(
                    kind="block",
                    start_line=line_no,
                    start_col=pos,
                    end_line=line_no,
                    end_col=end_col,
                    raw=raw_comment,
                    text=self._clean_comment_text(raw_comment, kind="block"),
                    cell_index=cell_index,
                )
                matches.append(m)

                if remove and should_remove(m):
                    removed += 1
                    out = out[:pos] + out[end_col:]
                    i = pos
                else:
                    i = end_col
                continue


            self._enter_block_state(
                end_tok=end_tok,
                line_no=line_no,
                start_col=pos,
                raw_line=raw_line,
                prefix=out[:pos],
                comment_part=(out[pos:] + nl),
            )
            return [], matches, removed

        return [out + nl], matches, removed

    def _process_line_in_block(
        self,
        line_no: int,
        raw_line: str,
        *,
        remove: bool,
        should_remove: "callable[[CommentMatch], bool]",
        cell_index: Optional[int] = None,
    ) -> Tuple[List[str], List[CommentMatch], int]:
        nl = "\n" if raw_line.endswith("\n") else ""
        line = raw_line[:-1] if nl else raw_line

        self._block_original_lines.append(raw_line)

        end_pos = line.find(self._block_end_tok)
        if end_pos == -1:
            self._block_raw_parts.append(raw_line)
            return [], [], 0

        end_col = end_pos + len(self._block_end_tok)
        self._block_raw_parts.append(line[:end_col])
        remainder = line[end_col:] + nl

        raw_comment = "".join(self._block_raw_parts)
        excluded = self._is_excluded(raw_comment)

        m = CommentMatch(
            kind="block",
            start_line=self._block_start_line,
            start_col=self._block_start_col,
            end_line=line_no,
            end_col=end_col,
            raw=raw_comment,
            text=self._clean_comment_text(raw_comment, kind="block"),
            cell_index=cell_index,
        )

        flushed: List[str] = []
        matches: List[CommentMatch] = []
        removed = 0

        if not excluded:
            matches.append(m)

        do_remove = remove and (not excluded) and should_remove(m)

        if do_remove:
            removed = 1
            flushed.append(self._block_prefix_before_start.rstrip() + "\n")

            middle_count = (line_no - self._block_start_line) - 1
            flushed.extend(["\n"] * max(0, middle_count))


            rem_lines, rem_matches, rem_removed = self._process_line_no_block(
                line_no, remainder, remove=True, should_remove=should_remove, cell_index=cell_index
            )
            flushed.extend(rem_lines)
            matches.extend(rem_matches)
            removed += rem_removed
        else:
            flushed.extend(self._block_original_lines)

        self._reset_block_state()
        return flushed, matches, removed

    def _enter_block_state(
        self,
        *,
        end_tok: str,
        line_no: int,
        start_col: int,
        raw_line: str,
        prefix: str,
        comment_part: str,
    ) -> None:
        self._in_block = True
        self._block_end_tok = end_tok
        self._block_start_line = line_no
        self._block_start_col = start_col
        self._block_prefix_before_start = prefix
        self._block_original_lines = [raw_line]
        self._block_raw_parts = [comment_part]

    def _reset_block_state(self) -> None:
        self._in_block = False
        self._block_end_tok = ""
        self._block_start_line = 0
        self._block_start_col = 0
        self._block_prefix_before_start = ""
        self._block_original_lines = []
        self._block_raw_parts = []

    def _end_for_start(self, start_tok: str) -> str:
        for s, e in self.style.block_markers:
            if s == start_tok:
                return e
        return ""

    def _is_excluded(self, raw_comment: str) -> bool:
        if not self.exclude_comment_pattern:
            return False
        return raw_comment.startswith(self.exclude_comment_pattern)

    @staticmethod
    def _clean_comment_text(raw: str, *, kind: str) -> str:
        s = raw.strip()
        if kind == "line":
            s = re.sub(r"^\s*(#|//|--)\s?", "", s)
            return s.strip()

        s = re.sub(r"^\s*(/\*|<!--|\"\"\"|''')\s?", "", s)
        s = re.sub(r"\s*(\*/|-->|\"\"\"|''')\s*$", "", s)
        return s.strip()






class CommentProcessor:
    """
    Process files and extract/remove comments.
    
    Added support for Jupyter notebooks with automatic kernel language detection.
    """
    KERNEL_LANGUAGE_TO_EXTENSION = {
        'python': '.py',
        'python3': '.py',
        'python2': '.py',
        'ipython': '.py',
        'ir': '.r',
        'r': '.r',
        'julia': '.jl',
        'julia-1.0': '.jl',
        'julia-1.6': '.jl',
        'scala': '.scala',
        'java': '.java',
        'c++': '.cpp',
        'c++11': '.cpp',
        'c++14': '.cpp',
        'c++17': '.cpp',
        'c++20': '.cpp',
        'cling-cpp11': '.cpp',
        'cling-cpp14': '.cpp',
        'cling-cpp17': '.cpp',
        'javascript': '.js',
        'typescript': '.ts',
        'go': '.go',
        'rust': '.rs',
        'ruby': '.rb',
        'bash': '.sh',
        'sh': '.sh',
        'sql': '.sql',
        'octave': '.m',
        'matlab': '.m',
        'php': '.php',
        'perl': '.pl',
        'haskell': '.hs',
        'clojure': '.clj',
        'groovy': '.groovy',
        'kotlin': '.kt',
        'swift': '.swift',
        'csharp': '.cs',
        'fsharp': '.fs',
    }

    def __init__(self, config: CommentExtractorConfig) -> None:
        self.config = config
        self.file_walker = self._create_walker(config)


        self._cache: Optional[Dict[str, Tuple[float, Tuple[int, List[CommentMatch]]]]] = (
            {} if config.use_cache else None
        )

        if self.config.language_filter and not LANGDETECT_AVAILABLE:
            logger.warning("Language filter requested but langdetect is not installed; filter will be ignored.")

        if self.config.backup_dir is not None:
            self.config.backup_dir = Path(self.config.backup_dir).resolve()

    @staticmethod
    def _create_walker(config: CommentExtractorConfig) -> FileSystemWalker:
        parser: Optional[GitIgnoreParser] = None
        if config.use_gitignore or config.custom_gitignore:
            root_dir = Path(config.directories[0]).resolve() if config.directories else Path.cwd().resolve()
            parser = GitIgnoreParser(root_dir=root_dir)
            if config.custom_gitignore:
                parser.load_from_file(config.custom_gitignore)
            else:
                parser.load_from_file()
        return FileSystemWalker(config, parser)

    def find_files(self) -> List[Path]:
        roots = [Path(d).resolve() for d in (self.config.directories or ["."])]
        files = self.file_walker.find_files(roots, recursive=self.config.recursive)

        stats = self.file_walker.stats
        logger.info("Found %d files to process", len(files))
        logger.info(
            "Excluded %d files and %d directories",
            stats.get("files_excluded", 0),
            stats.get("directories_excluded", 0),
        )
        return files

    def process_files(self) -> Dict[str, Any]:
        files = self.find_files()
        if not files:
            logger.warning("No files found matching criteria")
            return {"total_files": 0, "total_comments": 0, "removed_comments": 0, "comments": []}

        self._log_configuration()

        total_removed = 0
        total_comments = 0
        all_comments: List[Dict[str, Any]] = []

        with ProgressReporter(total=len(files), description="Extracting comments") as progress:
            for p in files:
                try:
                    removed, matches = self.process_file(p)
                    total_removed += removed
                    total_comments += len(matches)

                    rel = get_relative_path(p)
                    for m in matches:
                        cell_info = f" [cell {m.cell_index}]" if m.cell_index is not None else ""
                        logger.info("%s:%d%s: %s", rel, m.start_line, cell_info, m.text)
                        all_comments.append(
                            {
                                "file": str(p),
                                "relative_path": rel,
                                "kind": m.kind,
                                "start_line": m.start_line,
                                "start_col": m.start_col,
                                "end_line": m.end_line,
                                "end_col": m.end_col,
                                "text": m.text,
                                "raw": m.raw,
                                "cell_index": m.cell_index,
                            }
                        )
                except Exception as e:
                    logger.error("Failed to process %s: %s", p, e)

                progress.update(1)

        self._log_summary(total_removed, total_comments, len(files))

        if self.config.export_file and all_comments:
            self._export_comments(all_comments, Path(self.config.export_file))

        return {
            "total_files": len(files),
            "total_comments": total_comments,
            "removed_comments": total_removed,
            "comments": all_comments,
        }

    def process_file(self, file_path: Path) -> Tuple[int, List[CommentMatch]]:
        """
        Process a file to extract/remove comments.
        
        Special handling for .ipynb files with automatic kernel language detection.
        """
        if file_path.suffix.lower() == '.ipynb':
            return self._process_ipynb_file(file_path)

        if FileContentDetector.detect_file_type(file_path) != FileType.TEXT:
            logger.debug("Skipping non-text file: %s", file_path)
            return 0, []

        cache_key = str(file_path)
        try:
            mtime = file_path.stat().st_mtime
        except Exception:
            mtime = -1.0

        if self._cache is not None and cache_key in self._cache:
            cached_mtime, cached_result = self._cache[cache_key]
            if cached_mtime == mtime:
                return cached_result

        encoding = FileContentDetector.detect_encoding(file_path)
        try:
            with open(file_path, "r", encoding=encoding, errors="strict") as f:
                lines = f.readlines()
        except UnicodeDecodeError:
            logger.warning("Decoding failed with %s for %s, falling back to latin-1", encoding, file_path)
            encoding = "latin-1"
            with open(file_path, "r", encoding=encoding, errors="replace") as f:
                lines = f.readlines()

        style = (
            CommentStyle.from_override(self.config.comment_symbols)
            if self.config.comment_symbols
            else CommentStyle.from_extension(file_path.suffix)
        )
        if not style.line_markers and not style.block_markers:
            style = CommentStyle(line_markers=("#",), block_markers=())

        if self.config.remove_comments and file_path.suffix.lower() == ".py" and style.block_markers:
            logger.warning("Removing block comments in .py may remove docstrings: %s", file_path)

        scanner = CommentScanner(style, exclude_comment_pattern=self.config.exclude_comment_pattern)

        def should_remove(m: CommentMatch) -> bool:
            if not self.config.remove_comments:
                return False
            return self._should_remove_comment(m.text)


        remove_flag = bool(self.config.remove_comments)

        out_lines, matches, removed_count = scanner.scan_and_strip(
            lines,
            remove=remove_flag,
            should_remove=should_remove,
        )

        if removed_count > 0 and self.config.remove_comments and not self.config.preview_mode:
            backup_path = None
            try:

                if self.config.keep_backups:
                    backup_path = self._create_persistent_backup(file_path)

                ok = safe_write(
                    file_path,
                    "".join(out_lines),
                    encoding=encoding,
                    backup=False,
                )
                if not ok:

                    if backup_path and backup_path.exists():
                        try:
                            shutil.copy2(backup_path, file_path)
                        except Exception:
                            pass
                    raise RuntimeError(f"Failed to write updated file: {file_path}")
            except Exception:

                if backup_path and backup_path.exists():
                    try:
                        shutil.copy2(backup_path, file_path)
                    except Exception:
                        pass
                raise

        result = (removed_count, matches)
        if self._cache is not None:
            self._cache[cache_key] = (mtime, result)
        return result
    

    def _get_kernel_language(self, notebook_data: dict) -> str:
        """
        Extract kernel language from Jupyter notebook metadata.
        
        Returns the language name in lowercase.
        """
        lang_info = notebook_data.get('metadata', {}).get('language_info', {})
        if 'name' in lang_info:
            return lang_info['name'].lower()
        
        kernelspec = notebook_data.get('metadata', {}).get('kernelspec', {})
        if 'language' in kernelspec:
            return kernelspec['language'].lower()
        
        if 'name' in kernelspec:
            kernel_name = kernelspec['name'].lower()
            if 'python' in kernel_name:
                return 'python'
            elif kernel_name.startswith('ir'):
                return 'r'
            elif 'julia' in kernel_name:
                return 'julia'
            elif 'scala' in kernel_name:
                return 'scala'
        
        logger.debug("Could not determine kernel language, defaulting to Python")
        return 'python'
    
    def _process_ipynb_file(self, file_path: Path) -> Tuple[int, List[CommentMatch]]:
        """
        Process a Jupyter notebook file.
        
        Automatically detects the kernel language and uses appropriate comment patterns.
        Only processes code cells.
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                notebook = json.load(f)
        except json.JSONDecodeError as e:
            logger.error("Invalid JSON in .ipynb file %s: %s", file_path, e)
            return 0, []
        except Exception as e:
            logger.error("Failed to read .ipynb file %s: %s", file_path, e)
            return 0, []
        
        kernel_lang = self._get_kernel_language(notebook)
        extension = self.KERNEL_LANGUAGE_TO_EXTENSION.get(kernel_lang, '.py')
        
        logger.debug("Detected kernel language '%s' for %s, using comment style for '%s'", 
                    kernel_lang, file_path.name, extension)
        
        style = (
            CommentStyle.from_override(self.config.comment_symbols)
            if self.config.comment_symbols
            else CommentStyle.from_extension(extension)
        )
        
        if not style.line_markers and not style.block_markers:
            logger.warning("No comment style found for language '%s', defaulting to '#'", kernel_lang)
            style = CommentStyle(line_markers=('#',), block_markers=())
        
        if self.config.remove_comments and kernel_lang in ('python', 'python3', 'python2', 'ipython') and style.block_markers:
            logger.warning("Removing block comments in Python notebook may remove docstrings: %s", file_path)
        
        all_matches = []
        total_removed = 0
        modified = False
        
        cells = notebook.get('cells', [])
        for cell_idx, cell in enumerate(cells):
            if cell.get('cell_type') != 'code':
                continue
            
            source = cell.get('source', [])
            
            if isinstance(source, str):
                lines = source.splitlines(keepends=True)
            elif isinstance(source, list):
                lines = []
                for line in source:
                    if isinstance(line, str):
                        if not line.endswith('\n'):
                            line += '\n'
                        lines.append(line)
                    else:
                        lines.append(str(line) + '\n')
            else:
                logger.warning("Unexpected source type in cell %d: %s", cell_idx, type(source))
                continue
            
            if not lines:
                continue
            
            scanner = CommentScanner(style, exclude_comment_pattern=self.config.exclude_comment_pattern)
            
            def should_remove(m: CommentMatch) -> bool:
                if not self.config.remove_comments:
                    return False
                return self._should_remove_comment(m.text)
            
            out_lines, matches, removed_count = scanner.scan_and_strip(
                lines,
                remove=bool(self.config.remove_comments),
                should_remove=should_remove,
                cell_index=cell_idx,
            )
            
            all_matches.extend(matches)
            total_removed += removed_count
            
            if removed_count > 0 and self.config.remove_comments and not self.config.preview_mode:
                modified = True
                if isinstance(source, str):
                    cell['source'] = ''.join(out_lines)
                else:
                    cell['source'] = out_lines
        
        if modified and not self.config.preview_mode:
            backup_path = None
            try:
                if self.config.keep_backups:
                    backup_path = self._create_persistent_backup(file_path)
                
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(notebook, f, ensure_ascii=False, indent=1)
                
                logger.info("Modified notebook saved: %s", file_path)
                
            except Exception as e:
                logger.error("Failed to write modified notebook %s: %s", file_path, e)
                if backup_path and backup_path.exists():
                    try:
                        shutil.copy2(backup_path, file_path)
                        logger.info("Restored from backup: %s", backup_path)
                    except Exception as restore_error:
                        logger.error("Failed to restore from backup: %s", restore_error)
                raise
        
        return total_removed, all_matches





    def _backup_base_dir(self) -> Path:

        if self.config.directories:
            return Path(self.config.directories[0]).resolve()
        return Path.cwd().resolve()

    def _default_adjacent_backup_path(self, file_path: Path) -> Path:

        return file_path.with_name(file_path.name + ".bak")

    def _target_backup_path(self, file_path: Path) -> Path:
        if self.config.backup_dir is None:
            return self._default_adjacent_backup_path(file_path)

        base = self._backup_base_dir()
        src = file_path.resolve()
        try:
            rel = src.relative_to(base)
        except Exception:
            rel = Path(src.name)

        target = (self.config.backup_dir / rel).with_name(rel.name + ".bak")
        return target

    @staticmethod
    def _next_versioned_backup_path(p: Path) -> Path:

        i = 1
        while True:
            candidate = Path(str(p) + f".{i}")
            if not candidate.exists():
                return candidate
            i += 1

    def _create_persistent_backup(self, file_path: Path) -> Optional[Path]:
        if not file_path.exists():
            return None

        target = self._target_backup_path(file_path)
        target.parent.mkdir(parents=True, exist_ok=True)

        if target.exists():
            if self.config.overwrite_backups:
                try:
                    target.unlink()
                except Exception:

                    target = self._next_versioned_backup_path(target)
            else:
                target = self._next_versioned_backup_path(target)

        shutil.copy2(file_path, target)
        logger.debug("Backup created: %s", target)
        return target





    def _should_remove_comment(self, comment_text: str) -> bool:
        if not self.config.language_filter:
            return True
        if not LANGDETECT_AVAILABLE:
            return True

        cleaned = self._normalize_for_langdetect(comment_text)
        if len(cleaned) < int(self.config.min_langdetect_len):
            return True

        try:
            lang = detect(cleaned)
            return lang == self.config.language_filter
        except LangDetectException:
            return True

    @staticmethod
    def _normalize_for_langdetect(text: str) -> str:
        s = re.sub(r"\b(def|class|function|var|let|const|import|from|return|if|else)\b", " ", text, flags=re.I)
        s = re.sub(r"[^\w\s]+", " ", s, flags=re.UNICODE)
        s = re.sub(r"\s+", " ", s).strip()
        return s





    def _export_comments(self, comments: List[Dict[str, Any]], export_path: Path) -> None:
        export_path = Path(export_path)
        export_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            suf = export_path.suffix.lower()
            if suf == ".json":
                payload = {
                    "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "total_comments": len(comments),
                    "comments": comments,
                }
                with open(export_path, "w", encoding="utf-8") as f:
                    json.dump(payload, f, ensure_ascii=False, indent=2)
                logger.info("Comments exported to: %s", export_path)
                return

            if suf == ".jsonl":
                with open(export_path, "w", encoding="utf-8") as f:
                    for c in comments:
                        f.write(json.dumps(c, ensure_ascii=False) + "\n")
                logger.info("Comments exported to: %s", export_path)
                return


            with open(export_path, "w", encoding="utf-8") as f:
                f.write("EXTRACTED COMMENTS REPORT\n")
                f.write(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Total comments: {len(comments)}\n")
                f.write("=" * 60 + "\n\n")

                by_file: Dict[str, List[Dict[str, Any]]] = {}
                for c in comments:
                    by_file.setdefault(c["relative_path"], []).append(c)

                for rel_path, items in sorted(by_file.items()):
                    f.write(f"\nFILE: {rel_path}\n")
                    f.write("-" * 40 + "\n")
                    for c in items:
                        cell_info = f" [cell {c['cell_index']}]" if c.get('cell_index') is not None else ""
                        f.write(f"{c['kind']} {c['start_line']}:{c['start_col']}{cell_info}: {c['text']}\n")
                    f.write(f"\nTotal in file: {len(items)}\n")

                f.write("\n" + "=" * 60 + "\n")
                f.write(f"Total files: {len(by_file)}\n")
                f.write(f"Total comments: {len(comments)}\n")

            logger.info("Comments exported to: %s", export_path)
        except Exception as e:
            logger.error("Failed to export comments: %s", e)





    def _log_configuration(self) -> None:
        logger.info("=" * 60)
        logger.info("COMMENT EXTRACTOR CONFIGURATION")
        logger.info("=" * 60)
        logger.info("Directories: %s", ", ".join(self.config.directories or ["."]))
        logger.info("Pattern: %s", self.config.include_pattern)
        logger.info("Recursive: %s", self.config.recursive)
        logger.info("Remove comments: %s", self.config.remove_comments)
        logger.info("Preview mode: %s", self.config.preview_mode)

        if self.config.comment_symbols:
            logger.info("Override comment symbols: %s", self.config.comment_symbols)
        if self.config.language_filter:
            logger.info("Language filter: %s", self.config.language_filter)
        if self.config.exclude_comment_pattern:
            logger.info("Exclude comment pattern: %s", self.config.exclude_comment_pattern)

        if self.config.use_gitignore or self.config.custom_gitignore:
            logger.info("Gitignore: enabled")

        if self.config.keep_backups:
            if self.config.backup_dir:
                logger.info("Backups: enabled (dir=%s, overwrite=%s)", self.config.backup_dir, self.config.overwrite_backups)
            else:
                logger.info("Backups: enabled (adjacent, overwrite=%s)", self.config.overwrite_backups)

        logger.info("=" * 60)

    def _log_summary(self, removed: int, found: int, files: int) -> None:
        logger.info("=" * 60)
        logger.info("PROCESSING SUMMARY")
        logger.info("=" * 60)

        if self.config.preview_mode and self.config.remove_comments:
            action = "Would remove"
        elif self.config.remove_comments:
            action = "Removed"
        else:
            action = "Found"

        logger.info("%s %d comments out of %d detected", action, removed, found)
        logger.info("Processed %d files", files)
        logger.info("=" * 60)






def _configure_logging(log_file: Optional[Path], *, verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    handlers: List[logging.Handler] = []

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(logging.Formatter("%(message)s"))
    handlers.append(console)

    if log_file:
        fh = logging.FileHandler(log_file, mode="w", encoding="utf-8")
        fh.setLevel(logging.INFO)
        fh.setFormatter(logging.Formatter("%(message)s"))
        handlers.append(fh)

    logging.basicConfig(level=level, handlers=handlers, force=True)


def parse_arguments(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Advanced comment extractor and remover",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )


    parser.add_argument("directories", nargs="*", default=["."], help="Directories to process")
    parser.add_argument("-p", "--pattern", default="*", help='File pattern (e.g. "*.py")')
    parser.add_argument("-r", "--recursive", action="store_true", help="Search recursively")


    parser.add_argument("-c", "--comment-symbols", help='Override: "//" or "/* */" or "// /* */"')
    parser.add_argument("-e", "--exclude-comment-pattern", help='Exclude comments starting with this prefix (e.g. "##")')
    parser.add_argument("-l", "--language", help='Filter removal by comment language (e.g. "en", "ru")')


    parser.add_argument("--remove-comments", action="store_true", help="Remove comments from files")
    parser.add_argument("--preview", action="store_true", help="Preview without modifying files")
    parser.add_argument("--export-comments", type=Path, help="Export comments (.txt/.json/.jsonl)")


    parser.add_argument("-ed", "--exclude-dir", action="append", dest="exclude_dirs", help="Exclude directory name")
    parser.add_argument("-en", "--exclude-name", action="append", dest="exclude_names", help="Exclude file wildcard")
    parser.add_argument("-ep", "--exclude-pattern", action="append", dest="exclude_patterns", help="Exclude path wildcard")
    parser.add_argument("--max-depth", type=int, help="Maximum recursion depth")


    parser.add_argument("-ig", "--use-gitignore", action="store_true", help="Auto-discover and use .gitignore")
    parser.add_argument("-gi", "--gitignore", type=Path, help="Use a specific .gitignore")
    parser.add_argument("--no-gitignore", action="store_true", help="Ignore .gitignore")


    parser.add_argument("-o", "--output", type=Path, help="Output log file")
    parser.add_argument("--log-file", type=Path, help="Legacy alias for --output")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")


    parser.add_argument("--no-cache", action="store_true", help="Disable caching")
    parser.add_argument("--min-langdetect-len", type=int, default=20, help="Min length for language detection")


    parser.add_argument("--keep-backups", action="store_true", help="Keep backups after successful write")
    parser.add_argument("--backup-dir", type=Path, help="Directory to store backups (preserves relative structure)")
    parser.add_argument(
        "--overwrite-backups",
        action="store_true",
        help="Overwrite existing backups (else create .bak.1/.bak.2...)",
    )

    args = parser.parse_args(argv)
    if args.log_file and not args.output:
        args.output = args.log_file
    return args


def create_config_from_args(args: argparse.Namespace) -> CommentExtractorConfig:
    use_gitignore = bool(args.use_gitignore) and not bool(args.no_gitignore)
    custom_gitignore = None if args.no_gitignore else args.gitignore

    return CommentExtractorConfig(
        directories=args.directories,
        include_pattern=args.pattern,
        recursive=args.recursive,
        exclude_dirs=set(args.exclude_dirs or []),
        exclude_names=set(args.exclude_names or []),
        exclude_patterns=set(args.exclude_patterns or []),
        max_depth=args.max_depth,
        use_gitignore=use_gitignore,
        custom_gitignore=custom_gitignore,
        comment_symbols=args.comment_symbols,
        exclude_comment_pattern=args.exclude_comment_pattern,
        language_filter=args.language if LANGDETECT_AVAILABLE else None,
        remove_comments=args.remove_comments,
        preview_mode=args.preview,
        export_file=args.export_comments,
        log_file=args.output,
        use_cache=not args.no_cache,
        min_langdetect_len=int(args.min_langdetect_len),
        keep_backups=bool(args.keep_backups) or bool(args.backup_dir),
        backup_dir=args.backup_dir,
        overwrite_backups=bool(args.overwrite_backups),
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_arguments(argv)
    _configure_logging(args.output, verbose=args.verbose)

    if args.language and not LANGDETECT_AVAILABLE:
        logger.warning("langdetect not installed. Language filter disabled. Install with: pip install langdetect")

    try:
        config = create_config_from_args(args)
        processor = CommentProcessor(config)
        result = processor.process_files()


        if not config.log_file and not config.preview_mode:
            if config.preview_mode and config.remove_comments:
                action = "Would remove"
            elif config.remove_comments:
                action = "Removed"
            else:
                action = "Found"
            print(f"\n{action} {result['removed_comments']} comments in {result['total_files']} files")

        return 0

    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
        return 130
    except Exception as e:
        logger.error("Fatal error: %s", e)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
