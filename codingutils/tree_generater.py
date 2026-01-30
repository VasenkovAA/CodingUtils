"""
CLI flag style aligned with comment_extractor:
- positional directories
- -p/--pattern
- -r/--recursive
- -ed/--exclude-dir, -en/--exclude-name, -ep/--exclude-pattern
- -ig/--use-gitignore, -gi/--gitignore, --no-gitignore
- -o/--output, --log-file, -v/--verbose
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import logging
import stat as stat_module
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
from xml.etree import ElementTree as ET

from codingutils.common_utils import (
    FilterConfig,
    GitIgnoreParser,
    FileContentDetector,
    FileType,
    format_size,
)

logger = logging.getLogger(__name__)



@dataclass(slots=True)
class TreeConfig(FilterConfig):
    output_file: Optional[Path] = None
    format: str = "text"
    log_file: Optional[Path] = None
    verbose: bool = False

    show_size: bool = False
    show_permissions: bool = False
    show_last_modified: bool = False
    show_file_type: bool = False
    show_hidden: bool = False

    sort_by: str = "name"
    sort_reverse: bool = False


    indent_style: str = "tree"
    indent_size: int = 4
    max_width: Optional[int] = None


    include_statistics: bool = True
    include_summary: bool = True
    exclude_empty_dirs: bool = False

    tree_symbols: Dict[str, str] = field(default_factory=lambda: {
        "branch": "|-- ",
        "last_branch": "`-- ",
        "vertical": "|   ",
        "space": "    ",
    })

    def __post_init__(self) -> None:

        FilterConfig.__post_init__(self)

        if self.format not in {"text", "json", "xml", "markdown"}:
            raise ValueError(f"Unsupported format: {self.format}")

        if self.sort_by not in {"name", "size", "modified", "type"}:
            raise ValueError(f"Unsupported sort_by: {self.sort_by}")

        if self.indent_style not in {"tree", "spaces", "dashes"}:
            raise ValueError(f"Unsupported indent_style: {self.indent_style}")

        if self.indent_size < 0:
            raise ValueError("indent_size must be non-negative")


@dataclass(slots=True)
class TreeNode:
    name: str
    path: Path
    is_dir: bool
    children: List["TreeNode"] = field(default_factory=list)

    size: int = 0
    last_modified: float = 0.0
    permissions: str = ""
    file_type: Optional[FileType] = None

    is_symlink: bool = False


class NodeFilter:
    """
    Filtering logic compatible with FilterConfig semantics (plus additional hidden filtering).

    Important detail:
    - exclude_patterns are matched against basename OR root-relative path.
    - For directories, patterns like "docs/*" also exclude the directory itself (docs/),
      to match user expectations for "exclude subtree".
    """

    def __init__(self, config: TreeConfig, gitignore: Optional[GitIgnoreParser], root: Path) -> None:
        self.config = config
        self.gitignore = gitignore
        self.root = root.resolve()

    def _safe_rel(self, path: Path) -> str:
        try:
            return path.resolve().relative_to(self.root).as_posix()
        except Exception:
            return path.as_posix()

    def is_hidden_path(self, path: Path) -> bool:

        try:
            rel = path.resolve().relative_to(self.root)
            parts = rel.parts
        except Exception:
            parts = path.parts
        return any(p.startswith(".") for p in parts if p)

    def should_include(self, path: Path, *, is_dir: bool) -> bool:
        cfg = self.config


        if not cfg.show_hidden and self.is_hidden_path(path):
            return False


        if self.gitignore is not None and self.gitignore.should_ignore(path):
            return False


        if is_dir and cfg.exclude_dirs:
            try:
                rel_parts = path.resolve().relative_to(self.root).parts
            except Exception:
                rel_parts = path.parts
            if any(seg in cfg.exclude_dirs for seg in rel_parts):
                return False


        if cfg.exclude_names:
            for pat in cfg.exclude_names:
                if fnmatch.fnmatchcase(path.name, pat):
                    return False


        if cfg.exclude_patterns:
            rel_str = self._safe_rel(path)
            for pat in cfg.exclude_patterns:
                if fnmatch.fnmatchcase(path.name, pat) or fnmatch.fnmatchcase(rel_str, pat):
                    return False


                if is_dir:
                    probe = rel_str.rstrip("/") + "/__x__"
                    if fnmatch.fnmatchcase(probe, pat):
                        return False


        if not is_dir and not fnmatch.fnmatchcase(path.name, cfg.include_pattern):
            return False

        return True






class TreeBuilder:
    """Filesystem walker that builds a TreeNode hierarchy."""

    def __init__(self, config: TreeConfig, gitignore: Optional[GitIgnoreParser]) -> None:
        self.config = config
        self.gitignore = gitignore
        self.stats: Dict[str, Any] = {
            "directories": 0,
            "files": 0,
            "total_size": 0,
            "excluded_items": 0,
            "start_time": 0.0,
            "end_time": 0.0,
        }

    def build(self, roots: Sequence[Path]) -> TreeNode:
        self.stats["start_time"] = time.time()

        resolved = [Path(p).resolve() for p in roots]
        if not resolved:
            raise ValueError("No roots provided")

        if len(resolved) == 1:
            r = resolved[0]
            if not r.exists():
                raise FileNotFoundError(f"Root path does not exist: {r}")
            node = self._build_single_root(r)
            if node is None:

                node = TreeNode(name=r.name or str(r), path=r, is_dir=r.is_dir())
        else:

            node = TreeNode(name="COMBINED VIEW", path=Path.cwd().resolve(), is_dir=True)
            for r in resolved:
                if not r.exists():
                    self.stats["excluded_items"] += 1
                    continue
                child = self._build_single_root(r)
                if child is not None:
                    node.children.append(child)

        self.stats["end_time"] = time.time()
        return node

    def _build_single_root(self, root: Path) -> Optional[TreeNode]:
        nf = NodeFilter(self.config, self.gitignore, root=root)

        if root.is_file():
            if not nf.should_include(root, is_dir=False):
                self.stats["excluded_items"] += 1
                return None
            n = self._make_node(root, is_dir=False)
            self.stats["files"] += 1
            self.stats["total_size"] += n.size
            return n


        if not nf.should_include(root, is_dir=True):
            self.stats["excluded_items"] += 1
            return None

        root_node = self._make_node(root, is_dir=True)
        self.stats["directories"] += 1

        if self.config.recursive:
            self._populate_children(root_node, nf=nf, current_depth=0)
        else:

            self._populate_children(root_node, nf=nf, current_depth=0, allow_descend=False)

        self._sort_tree(root_node)

        if self.config.exclude_empty_dirs and not root_node.children:
            return None
        return root_node

    def _populate_children(
        self,
        node: TreeNode,
        *,
        nf: NodeFilter,
        current_depth: int,
        allow_descend: bool = True,
    ) -> None:
        cfg = self.config
        if not node.is_dir:
            return


        if allow_descend and cfg.max_depth is not None and current_depth >= cfg.max_depth:
            return

        try:
            entries = list(node.path.iterdir())
        except Exception:
            self.stats["excluded_items"] += 1
            return

        children: List[TreeNode] = []
        for entry in entries:

            try:
                is_symlink = entry.is_symlink()
            except Exception:
                is_symlink = False

            if is_symlink and not cfg.follow_symlinks:
                self.stats["excluded_items"] += 1
                continue

            real_path = entry
            if is_symlink and cfg.follow_symlinks:
                try:
                    real_path = entry.resolve()
                except Exception:
                    self.stats["excluded_items"] += 1
                    continue

            try:
                is_dir = real_path.is_dir()
            except Exception:
                self.stats["excluded_items"] += 1
                continue

            if not nf.should_include(real_path, is_dir=is_dir):
                self.stats["excluded_items"] += 1
                continue

            child = self._make_node(real_path, is_dir=is_dir)
            children.append(child)

            if is_dir:
                self.stats["directories"] += 1
                if allow_descend:
                    self._populate_children(child, nf=nf, current_depth=current_depth + 1, allow_descend=True)

                if cfg.exclude_empty_dirs and not child.children:
                    children.pop()
                    self.stats["directories"] -= 1
            else:
                self.stats["files"] += 1
                self.stats["total_size"] += child.size

        node.children = children

    def _make_node(self, path: Path, *, is_dir: bool) -> TreeNode:
        cfg = self.config
        node = TreeNode(name=path.name or str(path), path=path, is_dir=is_dir)

        try:
            node.is_symlink = path.is_symlink()
        except Exception:
            node.is_symlink = False


        need_stat = (
            cfg.show_size
            or cfg.show_last_modified
            or cfg.show_permissions
            or cfg.sort_by in {"size", "modified"}
        )
        if need_stat:
            try:
                st = path.stat()
                node.size = int(st.st_size) if not is_dir else 0
                node.last_modified = float(st.st_mtime)
                if cfg.show_permissions:
                    node.permissions = stat_module.filemode(st.st_mode)
            except Exception:
                pass


        if cfg.show_file_type and not is_dir:
            node.file_type = self._detect_file_type(path)

        return node

    @staticmethod
    def _detect_file_type(path: Path) -> FileType:

        if path.suffix.lower() in FileContentDetector.BINARY_EXTENSIONS:
            return FileType.BINARY
        return FileContentDetector.detect_file_type(path)

    def _sort_tree(self, node: TreeNode) -> None:
        self._sort_children(node)
        for c in node.children:
            if c.is_dir:
                self._sort_tree(c)

    def _sort_children(self, node: TreeNode) -> None:
        key = self.config.sort_by
        reverse = self.config.sort_reverse

        def sk(n: TreeNode):
            if key == "name":
                return (not n.is_dir, n.name.lower())
            if key == "size":
                return (not n.is_dir, n.size, n.name.lower())
            if key == "modified":
                return (not n.is_dir, n.last_modified, n.name.lower())
            if key == "type":
                return (not n.is_dir, n.path.suffix.lower(), n.name.lower())
            return (not n.is_dir, n.name.lower())

        node.children.sort(key=sk, reverse=reverse)






class Renderer:
    def __init__(self, config: TreeConfig) -> None:
        self.config = config

    def render(self, root: TreeNode, *, stats: Dict[str, Any], roots: Sequence[Path]) -> str:
        raise NotImplementedError

    def _truncate(self, s: str) -> str:
        w = self.config.max_width
        if w is None or w <= 0:
            return s
        if len(s) <= w:
            return s
        if w <= 3:
            return s[:w]
        return s[: w - 3] + "..."


class TextRenderer(Renderer):
    def render(self, root: TreeNode, *, stats: Dict[str, Any], roots: Sequence[Path]) -> str:
        lines: List[str] = []
        lines.extend(self._header(roots))
        self._render_node(root, prefix="", is_last=True, depth=0, lines=lines)

        if self.config.include_statistics:
            lines.extend(self._stats(stats))
        if self.config.include_summary:
            lines.extend(self._summary(stats))

        return "\n".join(lines).rstrip() + "\n"

    def _header(self, roots: Sequence[Path]) -> List[str]:
        cfg = self.config
        out: List[str] = []

        if len(roots) > 1:
            out.append("PROJECT TREES: " + ", ".join(Path(p).name for p in roots))
        else:
            out.append("PROJECT TREE: " + Path(roots[0]).name)

        out.append("Generated: " + time.strftime("%Y-%m-%d %H:%M:%S"))
        out.append("Format: " + cfg.format)
        out.append("Pattern: " + cfg.include_pattern)
        if cfg.max_depth is not None:
            out.append(f"Max Depth: {cfg.max_depth}")
        if cfg.use_gitignore or cfg.custom_gitignore:
            out.append("Gitignore: Enabled")
        out.append("=" * 60)
        return out

    def _render_node(self, node: TreeNode, *, prefix: str, is_last: bool, depth: int, lines: List[str]) -> None:

        if node.name == "COMBINED VIEW" and node.path == Path.cwd().resolve():
            for i, child in enumerate(node.children):
                self._render_node(child, prefix="", is_last=(i == len(node.children) - 1), depth=0, lines=lines)
            return

        line = self._format_line(node, prefix=prefix, is_last=is_last, depth=depth)
        lines.append(self._truncate(line))

        if not node.is_dir or not node.children:
            return

        if self.config.indent_style == "tree":
            next_prefix = prefix + (self.config.tree_symbols["space"] if is_last else self.config.tree_symbols["vertical"])
        elif self.config.indent_style == "spaces":
            next_prefix = " " * (self.config.indent_size * (depth + 1))
        else:
            next_prefix = "-" * (self.config.indent_size * (depth + 1)) + " "

        for i, child in enumerate(node.children):
            self._render_node(child, prefix=next_prefix, is_last=(i == len(node.children) - 1), depth=depth + 1, lines=lines)

    def _format_line(self, node: TreeNode, *, prefix: str, is_last: bool, depth: int) -> str:
        name = self._display_name(node)

        if depth == 0 and self.config.indent_style == "tree":
            return name

        if self.config.indent_style == "tree":
            connector = self.config.tree_symbols["last_branch"] if is_last else self.config.tree_symbols["branch"]
            return f"{prefix}{connector}{name}"
        return f"{prefix}{name}"

    def _display_name(self, node: TreeNode) -> str:
        cfg = self.config
        base = node.name + ("/" if node.is_dir else "")

        meta: List[str] = []


        if not node.is_dir:
            if cfg.show_file_type and node.file_type is not None:
                meta.append(node.file_type.value)
            if cfg.show_last_modified and node.last_modified:
                meta.append(datetime.fromtimestamp(node.last_modified).strftime("%Y-%m-%d"))
            if cfg.show_permissions and node.permissions:
                meta.append(node.permissions)
            if node.is_symlink:
                meta.append("symlink")
            if cfg.show_size:
                meta.append(format_size(node.size))
        else:
            if cfg.show_last_modified and node.last_modified:
                meta.append(datetime.fromtimestamp(node.last_modified).strftime("%Y-%m-%d"))
            if cfg.show_permissions and node.permissions:
                meta.append(node.permissions)
            if node.is_symlink:
                meta.append("symlink")

        if meta:
            base += " (" + ", ".join(meta) + ")"
        return base

    def _stats(self, stats: Dict[str, Any]) -> List[str]:
        elapsed = max(0.0, float(stats["end_time"]) - float(stats["start_time"]))
        return [
            "",
            "=" * 60,
            "STATISTICS:",
            f"  Directories: {stats['directories']}",
            f"  Files: {stats['files']}",
            f"  Total Size: {format_size(int(stats['total_size']))}",
            f"  Excluded Items: {stats['excluded_items']}",
            f"  Processing Time: {elapsed:.2f}s",
        ]

    def _summary(self, stats: Dict[str, Any]) -> List[str]:
        files = int(stats["files"])
        dirs = int(stats["directories"])
        total = int(stats["total_size"])
        avg_file = (total / files) if files else 0
        files_per_dir = (files / dirs) if dirs else 0.0
        elapsed = max(0.0, float(stats["end_time"]) - float(stats["start_time"]))

        return [
            "=" * 60,
            "SUMMARY:",
            f"  Average File Size: {format_size(int(avg_file)) if avg_file else '0 B'}",
            f"  Files per Directory: {files_per_dir:.1f}",
            f"  Tree generated in {elapsed:.2f}s",
            "=" * 60,
        ]


class MarkdownRenderer(Renderer):
    def render(self, root: TreeNode, *, stats: Dict[str, Any], roots: Sequence[Path]) -> str:
        lines: List[str] = []
        lines.append("# Project Structure")
        lines.append("")
        for p in roots:
            lines.append(f"- Root: `{Path(p).resolve()}`")
        lines.append("")
        self._render_node(root, level=0, lines=lines)

        if self.config.include_statistics:
            elapsed = max(0.0, float(stats["end_time"]) - float(stats["start_time"]))
            lines.append("")
            lines.append("## Statistics")
            lines.append(f"- Directories: {stats['directories']}")
            lines.append(f"- Files: {stats['files']}")
            lines.append(f"- Total size: {format_size(int(stats['total_size']))}")
            lines.append(f"- Excluded: {stats['excluded_items']}")
            lines.append(f"- Time: {elapsed:.2f}s")

        lines = [self._truncate(ln) for ln in lines]
        return "\n".join(lines).rstrip() + "\n"

    def _render_node(self, node: TreeNode, *, level: int, lines: List[str]) -> None:
        if node.name == "COMBINED VIEW" and node.path == Path.cwd().resolve():
            for child in node.children:
                self._render_node(child, level=0, lines=lines)
            return

        indent = "  " * level
        label = node.name + ("/" if node.is_dir else "")

        meta: List[str] = []
        if not node.is_dir:
            if self.config.show_last_modified and node.last_modified:
                meta.append(datetime.fromtimestamp(node.last_modified).strftime("%Y-%m-%d"))
            if self.config.show_size:
                meta.append(format_size(node.size))

        if meta:
            label += " (" + ", ".join(meta) + ")"

        lines.append(f"{indent}- {label}")
        for c in node.children:
            self._render_node(c, level=level + 1, lines=lines)


class JsonRenderer(Renderer):
    def render(self, root: TreeNode, *, stats: Dict[str, Any], roots: Sequence[Path]) -> str:
        obj: Dict[str, Any] = {
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "roots": [str(Path(p).resolve()) for p in roots],
            "tree": self._node(root),
        }
        if self.config.include_statistics:
            elapsed = max(0.0, float(stats["end_time"]) - float(stats["start_time"]))
            obj["statistics"] = {
                "directories": int(stats["directories"]),
                "files": int(stats["files"]),
                "total_size": int(stats["total_size"]),
                "excluded_items": int(stats["excluded_items"]),
                "processing_time": elapsed,
            }
        return json.dumps(obj, ensure_ascii=True, indent=2) + "\n"

    def _node(self, node: TreeNode) -> Dict[str, Any]:
        o: Dict[str, Any] = {
            "name": node.name,
            "path": str(node.path),
            "kind": "directory" if node.is_dir else "file",
        }
        if not node.is_dir:
            if self.config.show_size:
                o["size"] = node.size
            if self.config.show_last_modified and node.last_modified:
                o["last_modified"] = node.last_modified
            if self.config.show_permissions and node.permissions:
                o["permissions"] = node.permissions
            if self.config.show_file_type and node.file_type is not None:
                o["file_type"] = node.file_type.value

        if node.children:
            o["children"] = [self._node(c) for c in node.children]
        return o


class XmlRenderer(Renderer):
    def render(self, root: TreeNode, *, stats: Dict[str, Any], roots: Sequence[Path]) -> str:
        doc = ET.Element("project_structure")
        doc.set("generated_at", time.strftime("%Y-%m-%d %H:%M:%S"))

        roots_el = ET.SubElement(doc, "roots")
        for p in roots:
            r = ET.SubElement(roots_el, "root")
            r.text = str(Path(p).resolve())

        tree_el = ET.SubElement(doc, "tree")
        tree_el.append(self._node(root))

        if self.config.include_statistics:
            elapsed = max(0.0, float(stats["end_time"]) - float(stats["start_time"]))
            st = ET.SubElement(doc, "statistics")
            ET.SubElement(st, "directories").text = str(int(stats["directories"]))
            ET.SubElement(st, "files").text = str(int(stats["files"]))
            ET.SubElement(st, "total_size").text = str(int(stats["total_size"]))
            ET.SubElement(st, "excluded_items").text = str(int(stats["excluded_items"]))
            ET.SubElement(st, "processing_time").text = f"{elapsed:.2f}"

        xml_bytes = ET.tostring(doc, encoding="utf-8", xml_declaration=True)
        return xml_bytes.decode("utf-8") + "\n"

    def _node(self, node: TreeNode) -> ET.Element:
        el = ET.Element("directory" if node.is_dir else "file")
        el.set("name", node.name)
        el.set("path", str(node.path))

        if not node.is_dir:
            if self.config.show_size:
                el.set("size", str(node.size))
            if self.config.show_last_modified and node.last_modified:
                el.set("last_modified", datetime.fromtimestamp(node.last_modified).isoformat())
            if self.config.show_permissions and node.permissions:
                el.set("permissions", node.permissions)
            if self.config.show_file_type and node.file_type is not None:
                el.set("file_type", node.file_type.value)

        for c in node.children:
            el.append(self._node(c))
        return el






class ProjectTreeGenerator:
    def __init__(self, config: TreeConfig) -> None:
        self.config = config
        self._configure_logging()

        self.gitignore = self._create_gitignore_parser()
        self.builder = TreeBuilder(config, gitignore=self.gitignore)
        self.renderer = self._create_renderer()

    def _configure_logging(self) -> None:
        level = logging.DEBUG if self.config.verbose else logging.INFO
        handlers: List[logging.Handler] = [logging.StreamHandler(sys.stderr)]
        if self.config.log_file:
            handlers.append(logging.FileHandler(self.config.log_file, mode="w", encoding="utf-8"))
        logging.basicConfig(level=level, handlers=handlers, force=True)

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

    def _create_renderer(self) -> Renderer:
        if self.config.format == "json":
            return JsonRenderer(self.config)
        if self.config.format == "xml":
            return XmlRenderer(self.config)
        if self.config.format == "markdown":
            return MarkdownRenderer(self.config)
        return TextRenderer(self.config)

    def generate(self, roots: Sequence[Path]) -> str:
        valid_roots: List[Path] = []
        for p in roots:
            rp = Path(p).resolve()
            if not rp.exists():
                raise FileNotFoundError(f"Path does not exist: {p}")
            valid_roots.append(rp)

        node = self.builder.build(valid_roots)
        stats = dict(self.builder.stats)
        return self.renderer.render(node, stats=stats, roots=valid_roots)

    def write_output(self, content: str) -> None:
        if self.config.output_file:
            out = Path(self.config.output_file)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(content, encoding="utf-8")
        else:
            sys.stdout.write(content)






def parse_arguments(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="ASCII project structure visualizer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=r"""
Examples:

  project-tree . -r


  project-tree src -r -p "*.py"


  project-tree . -r --format json --output structure.json


  project-tree . -r --show-hidden


  project-tree . -r --use-gitignore
""".strip(),
    )


    parser.add_argument("directories", nargs="*", default=["."], help="Directories to visualize (default: .)")
    parser.add_argument("-p", "--pattern", default="*", help='File pattern (e.g. "*.py")')
    parser.add_argument("-r", "--recursive", action="store_true", help="Search directories recursively")
    parser.add_argument("--max-depth", type=int, help="Maximum recursion depth (works with --recursive)")


    parser.add_argument("-f", "--format", choices=["text", "json", "xml", "markdown"], default="text")
    parser.add_argument("-o", "--output", type=Path, help="Write output to file (default: stdout)")
    parser.add_argument("--log-file", type=Path, help="Write logs to file (default: stderr)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logs")


    parser.add_argument("-ed", "--exclude-dir", action="append", dest="exclude_dirs", help="Exclude directory by name (repeatable)")
    parser.add_argument("-en", "--exclude-name", action="append", dest="exclude_names", help="Exclude file by name/wildcard (repeatable)")
    parser.add_argument("-ep", "--exclude-pattern", action="append", dest="exclude_patterns", help="Exclude by path wildcard (repeatable)")
    parser.add_argument("--exclude-empty-dirs", action="store_true", help="Exclude empty directories")


    parser.add_argument("-gi", "--gitignore", type=Path, help="Use specific .gitignore file")
    parser.add_argument("-ig", "--use-gitignore", action="store_true", help="Auto-discover and use .gitignore")
    parser.add_argument("--no-gitignore", action="store_true", help="Ignore .gitignore")


    parser.add_argument("--show-hidden", action="store_true", help="Include hidden files/directories")
    parser.add_argument("--show-size", action="store_true", help="Show file sizes")
    parser.add_argument("--show-permissions", action="store_true", help="Show permissions (best-effort)")
    parser.add_argument("--show-last-modified", action="store_true", help="Show last modified date")
    parser.add_argument("--show-file-type", action="store_true", help="Show file type (may be slower)")


    parser.add_argument("--sort-by", choices=["name", "size", "modified", "type"], default="name")
    parser.add_argument("--sort-reverse", action="store_true", help="Reverse sort order")


    parser.add_argument("--indent-style", choices=["tree", "spaces", "dashes"], default="tree")
    parser.add_argument("--indent-size", type=int, default=4)
    parser.add_argument("--max-width", type=int, help="Max line width (truncate with '...')")


    parser.add_argument("--no-statistics", action="store_false", dest="include_statistics", default=True)
    parser.add_argument("--no-summary", action="store_false", dest="include_summary", default=True)

    return parser.parse_args(argv)


def create_config_from_args(args: argparse.Namespace) -> TreeConfig:
    use_gitignore = bool(args.use_gitignore) and not bool(args.no_gitignore)
    custom_gitignore = None if args.no_gitignore else args.gitignore

    return TreeConfig(

        directories=args.directories,
        include_pattern=args.pattern,
        recursive=bool(args.recursive),
        max_depth=args.max_depth,
        exclude_dirs=set(args.exclude_dirs or []),
        exclude_names=set(args.exclude_names or []),
        exclude_patterns=set(args.exclude_patterns or []),
        use_gitignore=use_gitignore,
        custom_gitignore=custom_gitignore,

        output_file=args.output,
        format=args.format,
        log_file=args.log_file,
        verbose=bool(args.verbose),
        show_hidden=bool(args.show_hidden),
        show_size=bool(args.show_size),
        show_permissions=bool(args.show_permissions),
        show_last_modified=bool(args.show_last_modified),
        show_file_type=bool(args.show_file_type),
        exclude_empty_dirs=bool(args.exclude_empty_dirs),
        sort_by=args.sort_by,
        sort_reverse=bool(args.sort_reverse),
        indent_style=args.indent_style,
        indent_size=int(args.indent_size),
        max_width=args.max_width,
        include_statistics=bool(args.include_statistics),
        include_summary=bool(args.include_summary),
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    try:
        args = parse_arguments(argv)
        config = create_config_from_args(args)

        gen = ProjectTreeGenerator(config)
        roots = [Path(d) for d in (config.directories or ["."])]

        content = gen.generate(roots)
        gen.write_output(content)
        return 0

    except KeyboardInterrupt:
        print("\nOperation cancelled by user", file=sys.stderr)
        return 130
    except Exception as e:
        logger.error("Fatal error: %s", e)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "TreeConfig",
    "TreeNode",
    "ProjectTreeGenerator",
    "parse_arguments",
    "create_config_from_args",
    "main",
]
