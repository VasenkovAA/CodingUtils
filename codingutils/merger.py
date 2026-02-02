"""
Advanced file merger with intelligent filtering and formatting.
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import shutil
import sys
import time
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from codingutils.common_utils import (
    FilterConfig,
    GitIgnoreParser,
    FileSystemWalker,
    FileContentDetector,
    FileType,
    ProgressReporter,
    format_size,
    get_relative_path,
)

logger = logging.getLogger(__name__)






@dataclass(slots=True)
class MergerConfig(FilterConfig):

    output_file: Path = Path("merged_output.txt")
    encoding: str = "utf-8"


    preview_mode: bool = False


    include_metadata: bool = True
    include_headers: bool = True
    compact_file_headers: bool = False
    header_separator: str = "=" * 60
    file_separator: str = "-" * 40
    line_number_format: str = "{:>4}: "


    add_line_numbers: bool = False
    remove_empty_lines: bool = False
    deduplicate_lines: bool = False


    sort_files: bool = False
    max_file_size: Optional[int] = None
    max_total_size: Optional[int] = None


    include_binary_placeholders: bool = True
    hash_binary_files: bool = True
    hash_chunk_size: int = 1024 * 1024


    keep_backups: bool = False
    backup_dir: Optional[Path] = None
    overwrite_backups: bool = False

    def __post_init__(self) -> None:
        FilterConfig.__post_init__(self)

        self.output_file = Path(self.output_file)
        if self.backup_dir is not None:
            self.backup_dir = Path(self.backup_dir)
            self.keep_backups = True

        if self.max_file_size is not None and self.max_file_size <= 0:
            raise ValueError("max_file_size must be positive")

        if self.max_total_size is not None and self.max_total_size <= 0:
            raise ValueError("max_total_size must be positive")






class SmartFileMerger:
    def __init__(self, config: MergerConfig) -> None:
        self.config = config

        self._roots: List[Path] = []
        self._gitignore = self._create_gitignore_parser()
        self._walker = FileSystemWalker(config, gitignore_parser=self._gitignore)

        self.stats: Dict[str, object] = {
            "start_time": 0.0,
            "end_time": 0.0,
            "files_found": 0,
            "files_selected": 0,
            "files_processed": 0,
            "files_skipped_by_limits": 0,
            "files_skipped_binary": 0,
            "files_failed": 0,
            "excluded_items": 0,
            "total_found_size": 0,
            "total_selected_size": 0,
            "output_size": 0,
        }





    def _resolve_roots(self) -> List[Path]:
        roots = [Path(d).resolve() for d in (self.config.directories or ["."])]
        self._roots = roots
        return roots

    def _rel(self, p: Path) -> str:

        rp = p.resolve()
        for r in self._roots:
            try:
                return rp.relative_to(r).as_posix()
            except Exception:
                continue
        return get_relative_path(p)





    def _create_gitignore_parser(self) -> Optional[GitIgnoreParser]:
        if not (self.config.use_gitignore or self.config.custom_gitignore):
            return None

        root = Path(self.config.directories[0]).resolve() if self.config.directories else Path.cwd().resolve()
        parser = GitIgnoreParser(root_dir=root)
        if self.config.custom_gitignore:
            parser.load_from_file(self.config.custom_gitignore)
        else:
            parser.load_from_file()
        return parser





    def find_files(self) -> List[Path]:
        roots = self._resolve_roots()
        files = self._walker.find_files(roots, recursive=self.config.recursive)


        try:
            out_abs = self.config.output_file.resolve()
            files = [f for f in files if f.resolve() != out_abs]
        except Exception:
            pass


        if self.config.backup_dir is not None:
            try:
                bd = self.config.backup_dir.resolve()
                files = [f for f in files if not self._is_under_dir(f, bd)]
            except Exception:
                pass

        if self.config.sort_files:
            files.sort(key=lambda x: (x.suffix.lower(), x.name.lower(), str(x)))

        self.stats["files_found"] = len(files)
        self.stats["excluded_items"] = (
            int(self._walker.stats.get("files_excluded", 0)) + int(self._walker.stats.get("directories_excluded", 0))
        )

        total = 0
        for f in files:
            try:
                total += f.stat().st_size
            except Exception:
                pass
        self.stats["total_found_size"] = total

        return files

    @staticmethod
    def _is_under_dir(p: Path, base: Path) -> bool:
        try:
            p.resolve().relative_to(base.resolve())
            return True
        except Exception:
            return False

    def select_files(self, files: List[Path]) -> Tuple[List[Path], List[Tuple[Path, str]]]:
        """
        Returns (selected_files, skipped_with_reason).
        Reasons: max_file_size, max_total_size, stat_failed
        """
        skipped: List[Tuple[Path, str]] = []
        selected: List[Path] = []

        total = 0

        for f in files:
            try:
                size = f.stat().st_size
            except Exception:
                skipped.append((f, "stat_failed"))
                continue

            if self.config.max_file_size is not None and size > self.config.max_file_size:
                skipped.append((f, "max_file_size"))
                continue

            if self.config.max_total_size is not None and (total + size) > self.config.max_total_size:
                skipped.append((f, "max_total_size"))
                continue

            selected.append(f)
            total += size

        self.stats["files_selected"] = len(selected)
        self.stats["total_selected_size"] = total
        self.stats["files_skipped_by_limits"] = sum(
            1 for _p, reason in skipped if reason in {"max_file_size", "max_total_size"}
        )

        return selected, skipped





    def preview_report(self, files: List[Path]) -> str:
        selected, skipped = self.select_files(files)

        lines: List[str] = []
        lines.append("=" * 60)
        lines.append("MERGE PREVIEW")
        lines.append("=" * 60)
        lines.append(f"Output: {self.config.output_file}")
        lines.append(f"Pattern: {self.config.include_pattern}")
        lines.append(f"Recursive: {self.config.recursive}")
        if self.config.max_depth is not None:
            lines.append(f"Max depth: {self.config.max_depth}")
        if self.config.use_gitignore or self.config.custom_gitignore:
            lines.append("Gitignore: enabled")
        lines.append("")

        lines.append("LIMITS:")
        lines.append(f"  max_file_size: {format_size(self.config.max_file_size) if self.config.max_file_size else 'none'}")
        lines.append(f"  max_total_size: {format_size(self.config.max_total_size) if self.config.max_total_size else 'none'}")
        lines.append("")

        lines.append("COUNTS:")
        lines.append(f"  files_found: {len(files)}")
        lines.append(f"  files_selected: {len(selected)}")
        lines.append(f"  skipped: {len(skipped)}")
        lines.append(f"  total_found_size: {format_size(int(self.stats['total_found_size']))}")
        lines.append(f"  total_selected_size: {format_size(int(self.stats['total_selected_size']))}")
        lines.append("")

        lines.append("OPTIONS:")
        lines.append(f"  include_metadata: {self.config.include_metadata}")
        lines.append(f"  include_headers: {self.config.include_headers}")
        lines.append(f"  compact_file_headers: {self.config.compact_file_headers}")
        lines.append(f"  add_line_numbers: {self.config.add_line_numbers}")
        lines.append(f"  remove_empty_lines: {self.config.remove_empty_lines}")
        lines.append(f"  deduplicate_lines(within file): {self.config.deduplicate_lines}")
        lines.append("")

        lines.append("FILES (selected):")
        lines.append(self.config.header_separator)

        for i, f in enumerate(selected[:200], 1):
            rel = self._rel(f)
            size = 0
            try:
                size = f.stat().st_size
            except Exception:
                pass
            kind = "BINARY" if self._is_binary_fast(f) else "TEXT"
            lines.append(f"{i:4}. [{kind}] {rel} ({format_size(size)})")

        if len(selected) > 200:
            lines.append(f"... ({len(selected) - 200} more selected files)")

        if skipped:
            lines.append("")
            lines.append("SKIPPED (first 50):")
            for f, reason in skipped[:50]:
                rel = self._rel(f)
                lines.append(f"  - {rel} [{reason}]")
            if len(skipped) > 50:
                lines.append(f"  ... ({len(skipped) - 50} more skipped)")

        lines.append(self.config.header_separator)
        lines.append("=" * 60)
        return "\n".join(lines) + "\n"

    def _is_binary_fast(self, p: Path) -> bool:
        if p.suffix.lower() in {".ipynb"}:
            return False
        if p.suffix.lower() in FileContentDetector.BINARY_EXTENSIONS:
            return True

        return False





    def merge(self) -> bool:
        self.stats["start_time"] = time.time()

        files = self.find_files()
        if not files:
            logger.error("No files found to merge.")
            return False

        if self.config.preview_mode:
            sys.stdout.write(self.preview_report(files))
            return True

        selected, skipped = self.select_files(files)
        if not selected:
            logger.error("No files selected after applying limits.")
            return False


        out_path = self.config.output_file
        out_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = out_path.with_name(out_path.name + ".tmp")

        backup_path: Optional[Path] = None

        try:
            if self.config.keep_backups and out_path.exists():
                backup_path = self._create_output_backup(out_path)

            with open(tmp_path, "w", encoding=self.config.encoding, newline="") as out:
                if self.config.include_metadata:
                    out.write(self._metadata_header(selected, skipped))

                with ProgressReporter(total=len(selected), description="Merging files", stream=sys.stderr) as progress:
                    for idx, fp in enumerate(selected, 1):
                        try:
                            self._write_file_section(out, fp, idx, len(selected))
                            self.stats["files_processed"] = int(self.stats["files_processed"]) + 1
                        except Exception as e:
                            self.stats["files_failed"] = int(self.stats["files_failed"]) + 1
                            out.write(f"[ERROR processing {self._rel(fp)}: {e}]\n")
                        progress.update(1)

                if self.config.include_metadata:
                    self.stats["end_time"] = time.time()
                    out.write(self._footer())


            tmp_path.replace(out_path)

            try:
                self.stats["output_size"] = out_path.stat().st_size
            except Exception:
                self.stats["output_size"] = 0

            self.stats["end_time"] = time.time()
            self._log_results()
            return True

        except Exception as e:
            logger.error("Failed to merge: %s", e)


            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass


            if backup_path and backup_path.exists():
                try:
                    shutil.copy2(backup_path, out_path)
                except Exception:
                    pass

            return False





    def _write_file_section(self, out, file_path: Path, index: int, total: int) -> None:

        if self.config.include_headers:
            header = self._file_header(file_path, index, total)
            if header:
                out.write(header)


        wrote_any = False
        for line in self._iter_processed_lines(file_path):
            out.write(line)
            wrote_any = True


        if wrote_any:
            out.write("\n")

    def _file_header(self, file_path: Path, index: int, total: int) -> str:
        cfg = self.config

        rel = self._rel(file_path)
        name = file_path.name

        size = 0
        mtime = 0.0
        try:
            st = file_path.stat()
            size = st.st_size
            mtime = st.st_mtime
        except Exception:
            pass


        enc = FileContentDetector.detect_encoding(file_path)

        lines: List[str] = []
        lines.append("")
        lines.append(cfg.file_separator)
        if not cfg.compact_file_headers:
            lines.append(f"FILE {index}/{total}: {rel}")
        else:
            lines.append(f"FILE {index}/{total}: {name}")

        lines.append(f"Size: {format_size(size)} | Encoding: {enc}")

        if not cfg.compact_file_headers and mtime:
            lines.append(f"Modified: {datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')}")

        lines.append(cfg.header_separator[:40])
        lines.append("")
        return "\n".join(lines) + "\n"





    def _iter_processed_lines(self, file_path: Path) -> Iterable[str]:
        if file_path.suffix.lower() == ".ipynb":
            yield from self._iter_ipynb_lines(file_path)
            return

        try:
            size = file_path.stat().st_size
        except Exception:
            size = 0

        if self.config.max_file_size is not None and size > self.config.max_file_size:
            self.stats["files_skipped_by_limits"] = int(self.stats["files_skipped_by_limits"]) + 1
            yield f"[FILE SKIPPED: exceeds max_file_size {format_size(self.config.max_file_size)}]\n"
            return


        if self._is_binary(file_path):
            self.stats["files_skipped_binary"] = int(self.stats["files_skipped_binary"]) + 1
            if self.config.include_binary_placeholders:
                yield from self._binary_placeholder(file_path)
            else:
                yield "[BINARY FILE SKIPPED]\n"
            return


        encoding = FileContentDetector.detect_encoding(file_path)
        try:
            yield from self._iter_text_lines(file_path, encoding=encoding)
        except UnicodeDecodeError:
            logger.warning("Decode failed for %s with %s, fallback to latin-1", file_path, encoding)
            yield from self._iter_text_lines(file_path, encoding="latin-1", errors="replace")
        except PermissionError:
            self.stats["files_failed"] = int(self.stats["files_failed"]) + 1
            yield "[ERROR: permission denied while reading file]\n"
        except FileNotFoundError:
            self.stats["files_failed"] = int(self.stats["files_failed"]) + 1
            yield "[ERROR: file not found]\n"
        except Exception as e:
            self.stats["files_failed"] = int(self.stats["files_failed"]) + 1
            yield f"[ERROR: failed to read file: {e}]\n"

    def _iter_text_lines(self, file_path: Path, *, encoding: str, errors: str = "strict") -> Iterable[str]:
        cfg = self.config
        seen: Optional[set[str]] = set() if cfg.deduplicate_lines else None
        line_no = 0

        with open(file_path, "r", encoding=encoding, errors=errors, newline="") as f:
            for raw in f:
                line = raw.rstrip("\n")

                if cfg.remove_empty_lines and not line.strip():
                    continue

                if seen is not None:
                    if line in seen:
                        continue
                    seen.add(line)

                line_no += 1
                if cfg.add_line_numbers:
                    yield cfg.line_number_format.format(line_no) + line + "\n"
                else:
                    yield line + "\n"

    def _iter_ipynb_lines(self, file_path: Path, encoding: str = "utf-8") -> Iterable[str]:
        try:
            with open(file_path, "r", encoding=encoding) as f:
                notebook = json.load(f)
        except json.JSONDecodeError as e:
            self.stats["files_failed"] = int(self.stats["files_failed"]) + 1
            yield f"[ERROR: Invalid JSON in .ipynb file: {e}]\n"
            return
        except Exception as e:
            self.stats["files_failed"] = int(self.stats["files_failed"]) + 1
            yield f"[ERROR: Failed to read .ipynb file: {e}]\n"
            return
        
        if "cells" not in notebook:
            yield f"[NOTEBOOK: No cells found in {file_path.name}]\n"
            return
        
        cells_extracted = 0
        total_cells = len(notebook.get("cells", []))
        
        notebook_name = notebook.get("metadata", {}).get("kernelspec", {}).get("display_name", "Jupyter Notebook")
        yield f"[NOTEBOOK: {file_path.name} ({notebook_name}) - {total_cells} cells]\n"
        
        for i, cell in enumerate(notebook.get("cells", []), 1):
            cell_type = cell.get("cell_type", "unknown")
            
            if cell_type in ("markdown", "code"):
                cells_extracted += 1
                
                yield f"\n{'='*40}\n"
                yield f"Cell {i}: {cell_type.upper()}\n"
                yield f"{'-'*40}\n"
                
                source = cell.get("source", [])
                
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
                    lines = [f"[UNSUPPORTED SOURCE TYPE: {type(source)}]\n"]
                
                for line in lines:
                    yield line
                
                if cell_type == "code" and cell.get("execution_count") is not None:
                    yield f"\n# Execution count: {cell['execution_count']}\n"
        
        yield f"\n{'='*40}\n"
        yield f"Notebook summary: {cells_extracted}/{total_cells} cells extracted\n"

    def _is_binary(self, file_path: Path) -> bool:
        if file_path.suffix.lower() == ".ipynb":
            return False
        if file_path.suffix.lower() in FileContentDetector.BINARY_EXTENSIONS:
            return True
        return FileContentDetector.detect_file_type(file_path) == FileType.BINARY

    def _binary_placeholder(self, file_path: Path) -> Iterable[str]:
        size = 0
        try:
            size = file_path.stat().st_size
        except Exception:
            pass

        sha256 = self._sha256(file_path) if self.config.hash_binary_files else ""

        yield f"[BINARY FILE: {file_path.name}]\n"
        yield f"Size: {format_size(size)}\n"
        if sha256:
            yield f"SHA256: {sha256}\n"
        yield "Binary content is not merged.\n"

    def _sha256(self, file_path: Path) -> str:
        h = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                while True:
                    chunk = f.read(self.config.hash_chunk_size)
                    if not chunk:
                        break
                    h.update(chunk)
            return h.hexdigest()
        except Exception:
            return ""





    def _metadata_header(self, files: List[Path], skipped: List[Tuple[Path, str]]) -> str:
        cfg = self.config
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        total = 0
        for f in files:
            try:
                total += f.stat().st_size
            except Exception:
                pass

        lines: List[str] = []
        lines.append("MERGED FILE REPORT")
        lines.append(cfg.header_separator)
        lines.append(f"Generated: {now}")
        lines.append("Tool: SmartFileMerger")
        lines.append("")
        lines.append("INPUT:")
        lines.append(f"  Files selected: {len(files)}")
        lines.append(f"  Total input size: {format_size(total)}")
        if skipped:
            by_reason: Dict[str, int] = {}
            for _p, reason in skipped:
                by_reason[reason] = by_reason.get(reason, 0) + 1
            lines.append("  Skipped by reason:")
            for reason, cnt in sorted(by_reason.items()):
                lines.append(f"    - {reason}: {cnt}")

        lines.append("")
        lines.append("CONFIGURATION:")
        lines.append(f"  Pattern: {cfg.include_pattern}")
        lines.append(f"  Recursive: {cfg.recursive}")
        if cfg.max_depth is not None:
            lines.append(f"  Max depth: {cfg.max_depth}")
        if cfg.use_gitignore or cfg.custom_gitignore:
            lines.append("  Gitignore: enabled")

        if cfg.exclude_dirs or cfg.exclude_names or cfg.exclude_patterns:
            lines.append("  Filters:")
            if cfg.exclude_dirs:
                lines.append(f"    exclude_dirs: {', '.join(sorted(cfg.exclude_dirs))}")
            if cfg.exclude_names:
                lines.append(f"    exclude_names: {', '.join(sorted(cfg.exclude_names))}")
            if cfg.exclude_patterns:
                lines.append(f"    exclude_patterns: {', '.join(sorted(cfg.exclude_patterns))}")

        lines.append("  Options:")
        lines.append(f"    include_headers: {cfg.include_headers}")
        lines.append(f"    compact_file_headers: {cfg.compact_file_headers}")
        lines.append(f"    add_line_numbers: {cfg.add_line_numbers}")
        lines.append(f"    remove_empty_lines: {cfg.remove_empty_lines}")
        lines.append(f"    deduplicate_lines(within file): {cfg.deduplicate_lines}")
        if cfg.max_file_size is not None:
            lines.append(f"    max_file_size: {format_size(cfg.max_file_size)}")
        if cfg.max_total_size is not None:
            lines.append(f"    max_total_size: {format_size(cfg.max_total_size)}")

        lines.append("")
        lines.append("FILE LIST:")
        lines.append(cfg.header_separator)
        for i, f in enumerate(files, 1):
            rel = self._rel(f)
            sz = 0
            try:
                sz = f.stat().st_size
            except Exception:
                pass
            lines.append(f"{i:4}. {rel} ({format_size(sz)})")
        lines.append(cfg.header_separator)
        lines.append("")
        return "\n".join(lines) + "\n"

    def _footer(self) -> str:
        cfg = self.config
        end = float(self.stats.get("end_time") or time.time())
        start = float(self.stats.get("start_time") or end)
        elapsed = end - start

        lines: List[str] = []
        lines.append("")
        lines.append(cfg.header_separator)
        lines.append("MERGE COMPLETE")
        lines.append(cfg.header_separator)
        lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"Processing time: {elapsed:.2f}s")
        lines.append("End of merged file")
        lines.append("")
        return "\n".join(lines)





    def _backup_target_path(self, out_file: Path) -> Path:

        bak_name = out_file.name + ".bak"

        if self.config.backup_dir is None:
            return out_file.with_name(bak_name)

        bd = self.config.backup_dir.resolve()
        try:
            rel = out_file.resolve().relative_to(Path.cwd().resolve())
        except Exception:
            rel = Path(out_file.name)

        target = bd / rel
        return target.with_name(bak_name)

    @staticmethod
    def _next_backup_version(p: Path) -> Path:
        i = 1
        while True:
            cand = Path(str(p) + f".{i}")
            if not cand.exists():
                return cand
            i += 1

    def _create_output_backup(self, out_file: Path) -> Optional[Path]:
        if not out_file.exists():
            return None

        target = self._backup_target_path(out_file)
        target.parent.mkdir(parents=True, exist_ok=True)

        if target.exists():
            if self.config.overwrite_backups:
                try:
                    target.unlink()
                except Exception:
                    target = self._next_backup_version(target)
            else:
                target = self._next_backup_version(target)

        shutil.copy2(out_file, target)
        return target





    def _log_results(self) -> None:
        end = float(self.stats.get("end_time") or time.time())
        start = float(self.stats.get("start_time") or end)
        elapsed = end - start

        logger.info("=" * 60)
        logger.info("MERGE COMPLETE")
        logger.info("=" * 60)
        logger.info("Output: %s", self.config.output_file)
        logger.info("files_found: %d", int(self.stats["files_found"]))
        logger.info("files_selected: %d", int(self.stats["files_selected"]))
        logger.info("files_processed: %d", int(self.stats["files_processed"]))
        logger.info("skipped_by_limits: %d", int(self.stats["files_skipped_by_limits"]))
        logger.info("skipped_binary: %d", int(self.stats["files_skipped_binary"]))
        logger.info("failed: %d", int(self.stats["files_failed"]))
        logger.info("total_found_size: %s", format_size(int(self.stats["total_found_size"])))
        logger.info("total_selected_size: %s", format_size(int(self.stats["total_selected_size"])))
        logger.info("output_size: %s", format_size(int(self.stats["output_size"])))
        logger.info("processing_time: %.2fs", elapsed)
        logger.info("=" * 60)






def parse_size_string(size_str: str) -> int:
    """
    Parse size string like '10MB', '1GB', '500KB' into bytes.
    If no unit is provided, assumes bytes.
    """
    s = size_str.strip().upper()
    multipliers = {
        "B": 1,
        "KB": 1024,
        "MB": 1024 * 1024,
        "GB": 1024 * 1024 * 1024,
        "TB": 1024 * 1024 * 1024 * 1024,
    }

    for unit in ("TB", "GB", "MB", "KB", "B"):
        if s.endswith(unit) and s != unit:
            num = float(s[: -len(unit)].strip())
            return int(num * multipliers[unit])

    return int(s)


def parse_arguments(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Advanced file merger with intelligent filtering",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=r"""
Examples:

  file-merger src -r -p "*.py" -o merged.txt


  file-merger src tests -r -p "*.py" --preview


  file-merger . -r -p "*.log" --no-headers --no-metadata -o logs.txt


  file-merger . -r -p "*.txt" --add-line-numbers --remove-empty-lines -o out.txt


  file-merger . -r -p "*.py" --compact-file-headers -o merged.txt


  file-merger . -r -ig -p "*" -o merged.txt


  file-merger . -r -p "*.py" -o merged.txt --keep-backups
  file-merger . -r -p "*.py" -o merged.txt --backup-dir .backups
  file-merger . -r -p "*.py" -o merged.txt --backup-dir .backups --overwrite-backups
""".strip(),
    )


    parser.add_argument("directories", nargs="*", default=["."], help="Directories to merge files from (default: .)")
    parser.add_argument("-p", "--pattern", default="*", help='File pattern (e.g. "*.py")')
    parser.add_argument("-r", "--recursive", action="store_true", help="Search directories recursively")
    parser.add_argument("--max-depth", type=int, help="Maximum recursion depth")


    parser.add_argument("-o", "--output", type=Path, default=Path("merged_output.txt"), help="Output file path")
    parser.add_argument("--encoding", default="utf-8", help="Output encoding (default: utf-8)")
    parser.add_argument("--log-file", type=Path, help="Write logs to file (default: stderr)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logs")


    parser.add_argument("-ed", "--exclude-dir", action="append", dest="exclude_dirs", help="Exclude directory by name (repeatable)")
    parser.add_argument("-en", "--exclude-name", action="append", dest="exclude_names", help="Exclude file by name/wildcard (repeatable)")
    parser.add_argument("-ep", "--exclude-pattern", action="append", dest="exclude_patterns", help="Exclude by path wildcard (repeatable)")


    parser.add_argument("-gi", "--gitignore", type=Path, help="Use specific .gitignore file")
    parser.add_argument("-ig", "--use-gitignore", action="store_true", help="Auto-discover and use .gitignore")
    parser.add_argument("--no-gitignore", action="store_true", help="Ignore .gitignore")


    parser.add_argument("--preview", action="store_true", help="Preview what would be merged without merging")


    parser.add_argument("--no-headers", action="store_false", dest="include_headers", help="Do not include per-file headers")
    parser.add_argument("--no-metadata", action="store_false", dest="include_metadata", help="Do not include global metadata header/footer")
    parser.add_argument("--compact-file-headers", action="store_true", help="Omit relpath and modified datetime lines in per-file header")
    parser.set_defaults(include_headers=True, include_metadata=True)


    parser.add_argument("--add-line-numbers", action="store_true", help="Add line numbers to file content")
    parser.add_argument("--remove-empty-lines", action="store_true", help="Remove empty/whitespace-only lines")
    parser.add_argument("--deduplicate", action="store_true", dest="deduplicate_lines", help="Deduplicate identical lines within each file")
    parser.add_argument("--sort-files", action="store_true", help="Sort files before merging")


    parser.add_argument("--max-file-size", help="Max individual file size (e.g. 10MB, 200KB)")
    parser.add_argument("--max-total-size", help="Max total size of selected files (e.g. 100MB)")


    parser.add_argument("--keep-backups", action="store_true", help="Keep backups of output file before overwrite")
    parser.add_argument("--backup-dir", type=Path, help="Directory to store backups (preserves cwd-relative structure)")
    parser.add_argument("--overwrite-backups", action="store_true", help="Overwrite existing backups (else .bak.1, .bak.2...)")


    parser.add_argument("--no-binary-placeholders", action="store_false", dest="include_binary_placeholders", help="Skip binary files silently (no placeholder)")
    parser.add_argument("--no-binary-hash", action="store_false", dest="hash_binary_files", help="Do not compute SHA256 for binary files")
    parser.set_defaults(include_binary_placeholders=True, hash_binary_files=True)

    return parser.parse_args(argv)


def _configure_logging(log_file: Optional[Path], *, verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    handlers: List[logging.Handler] = [logging.StreamHandler(sys.stderr)]
    if log_file:
        handlers.append(logging.FileHandler(log_file, mode="w", encoding="utf-8"))
    logging.basicConfig(level=level, handlers=handlers, force=True)


def create_config_from_args(args: argparse.Namespace) -> MergerConfig:
    max_file = parse_size_string(args.max_file_size) if args.max_file_size else None
    max_total = parse_size_string(args.max_total_size) if args.max_total_size else None

    use_gitignore = bool(args.use_gitignore) and not bool(args.no_gitignore)
    custom_gitignore = None if args.no_gitignore else args.gitignore

    return MergerConfig(
        directories=args.directories,
        recursive=bool(args.recursive),
        include_pattern=args.pattern,
        max_depth=args.max_depth,
        exclude_dirs=set(args.exclude_dirs or []),
        exclude_names=set(args.exclude_names or []),
        exclude_patterns=set(args.exclude_patterns or []),
        use_gitignore=use_gitignore,
        custom_gitignore=custom_gitignore,
        output_file=args.output,
        encoding=args.encoding,
        preview_mode=bool(args.preview),
        include_headers=bool(args.include_headers),
        include_metadata=bool(args.include_metadata),
        compact_file_headers=bool(args.compact_file_headers),
        add_line_numbers=bool(args.add_line_numbers),
        remove_empty_lines=bool(args.remove_empty_lines),
        deduplicate_lines=bool(args.deduplicate_lines),
        sort_files=bool(args.sort_files),
        max_file_size=max_file,
        max_total_size=max_total,
        keep_backups=bool(args.keep_backups) or bool(args.backup_dir),
        backup_dir=args.backup_dir,
        overwrite_backups=bool(args.overwrite_backups),
        include_binary_placeholders=bool(args.include_binary_placeholders),
        hash_binary_files=bool(args.hash_binary_files),
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    try:
        args = parse_arguments(argv)
        _configure_logging(args.log_file, verbose=bool(args.verbose))

        config = create_config_from_args(args)
        merger = SmartFileMerger(config)

        ok = merger.merge()
        return 0 if ok else 1

    except KeyboardInterrupt:
        print("\nOperation cancelled by user", file=sys.stderr)
        return 130
    except ValueError as e:
        logger.error("Configuration error: %s", e)
        return 1
    except Exception as e:
        logger.error("Fatal error: %s", e)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "MergerConfig",
    "SmartFileMerger",
    "parse_size_string",
    "parse_arguments",
    "create_config_from_args",
    "main",
]
