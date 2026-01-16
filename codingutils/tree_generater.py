"""
Advanced project structure visualizer with intelligent filtering.
Cross-platform alternative to 'tree' command with enhanced features.
"""

import argparse
import os
import sys
import time
from pathlib import Path
from typing import List, Optional, Dict, Any
import logging
from collections import defaultdict
from dataclasses import dataclass, field

from codingutils.common_utils import (
    FilterConfig,
    GitIgnoreParser,
    FileSystemWalker,
    FileContentDetector,
    FileType,
    format_size
)


# ============================================================================
# Configuration
# ============================================================================

@dataclass
class TreeConfig(FilterConfig):
    """Configuration for tree generation."""
    output_file: Optional[Path] = None
    format: str = "text"  # text, json, xml, markdown
    show_size: bool = True
    show_permissions: bool = False
    show_last_modified: bool = False
    show_file_type: bool = False
    show_hidden: bool = False
    show_icons: bool = True
    color_output: bool = True
    sort_by: str = "name"  # name, size, modified, type
    sort_reverse: bool = False
    indent_size: int = 4
    indent_style: str = "tree"  # tree, spaces, dashes
    include_statistics: bool = True
    include_summary: bool = True
    exclude_empty_dirs: bool = False
    max_width: Optional[int] = None

    # Tree symbols
    tree_symbols: Dict[str, str] = field(default_factory=lambda: {
        'branch': "├── ",
        'last_branch': "└── ",
        'vertical': "│   ",
        'space': "    ",
        'horizontal': "── ",
    })

    # File type icons (for show_icons)
    file_icons: Dict[str, str] = field(default_factory=lambda: {
        'directory': "📁 ",
        'python': "🐍 ",
        'javascript': "📜 ",
        'typescript': "📘 ",
        'java': "☕ ",
        'cpp': "⚙️ ",
        'c': "🔧 ",
        'html': "🌐 ",
        'css': "🎨 ",
        'json': "📋 ",
        'xml': "📄 ",
        'markdown': "📝 ",
        'readme': "📖 ",
        'image': "🖼️ ",
        'video': "🎬 ",
        'audio': "🎵 ",
        'archive': "🗜️ ",
        'binary': "🔨 ",
        'config': "⚙️ ",
        'document': "📄 ",
        'executable': "🚀 ",
        'default': "📄 ",
    })

    def __post_init__(self):
        """Validate configuration."""
        super().__post_init__()

        if self.format not in ["text", "json", "xml", "markdown"]:
            raise ValueError(f"Unsupported format: {self.format}")

        if self.sort_by not in ["name", "size", "modified", "type"]:
            raise ValueError(f"Unsupported sort_by: {self.sort_by}")

        if self.indent_style not in ["tree", "spaces", "dashes"]:
            raise ValueError(f"Unsupported indent_style: {self.indent_style}")


# ============================================================================
# Tree Node Structure
# ============================================================================

class TreeNode:
    """Represents a node in the tree structure."""

    def __init__(self, name: str, path: Path, is_dir: bool = False):
        self.name = name
        self.path = path
        self.is_dir = is_dir
        self.children: List['TreeNode'] = []
        self.parent: Optional['TreeNode'] = None
        self.size: int = 0
        self.last_modified: float = 0
        self.permissions: str = ""
        self.file_type: FileType = FileType.UNKNOWN
        self.depth: int = 0
        self.is_last: bool = False

        if path.exists():
            try:
                stat = path.stat()
                self.size = stat.st_size
                self.last_modified = stat.st_mtime

                # Get permissions (Unix-style)
                if hasattr(os, 'stat'):
                    import stat as stat_module
                    mode = stat.st_mode
                    self.permissions = stat_module.filemode(mode)

                # Determine file type
                if is_dir:
                    self.file_type = FileType.TEXT  # Directories are considered text for display
                else:
                    self.file_type = FileContentDetector.detect_file_type(path)

            except (OSError, PermissionError):
                pass

    def add_child(self, child: 'TreeNode') -> None:
        """Add a child node."""
        child.parent = self
        child.depth = self.depth + 1
        self.children.append(child)

    def sort_children(self, key: str = "name", reverse: bool = False) -> None:
        """Sort children by specified key."""
        if key == "name":
            self.children.sort(key=lambda x: x.name.lower(), reverse=reverse)
        elif key == "size":
            self.children.sort(key=lambda x: x.size, reverse=reverse)
        elif key == "modified":
            self.children.sort(key=lambda x: x.last_modified, reverse=reverse)
        elif key == "type":
            # Directories first, then files sorted by name
            self.children.sort(key=lambda x: (not x.is_dir, x.name.lower()), reverse=reverse)

        # Recursively sort children
        for child in self.children:
            if child.is_dir:
                child.sort_children(key, reverse)

    def get_icon(self, config: 'TreeConfig') -> str:
        """Get icon for this node."""
        if not config.show_icons:
            return ""

        if self.is_dir:
            return config.file_icons.get('directory', "📁 ")

        # Determine icon based on file extension
        suffix = self.path.suffix.lower()

        # Python files
        if suffix in ['.py', '.pyw', '.pyc', '.pyo']:
            return config.file_icons.get('python', "🐍 ")

        # JavaScript/TypeScript
        elif suffix in ['.js', '.jsx']:
            return config.file_icons.get('javascript', "📜 ")
        elif suffix in ['.ts', '.tsx']:
            return config.file_icons.get('typescript', "📘 ")

        # Java
        elif suffix in ['.java', '.jar', '.class']:
            return config.file_icons.get('java', "☕ ")

        # C/C++
        elif suffix in ['.cpp', '.cc', '.cxx', '.hpp', '.hxx']:
            return config.file_icons.get('cpp', "⚙️ ")
        elif suffix in ['.c', '.h']:
            return config.file_icons.get('c', "🔧 ")

        # Web
        elif suffix in ['.html', '.htm']:
            return config.file_icons.get('html', "🌐 ")
        elif suffix in ['.css', '.scss', '.sass', '.less']:
            return config.file_icons.get('css', "🎨 ")

        # Data formats
        elif suffix in ['.json', '.yaml', '.yml', '.toml']:
            return config.file_icons.get('json', "📋 ")
        elif suffix in ['.xml', '.xsl', '.xslt']:
            return config.file_icons.get('xml', "📄 ")

        # Documents
        elif suffix in ['.md', '.markdown']:
            if 'readme' in self.name.lower():
                return config.file_icons.get('readme', "📖 ")
            return config.file_icons.get('markdown', "📝 ")
        elif suffix in ['.txt', '.rtf', '.doc', '.docx', '.pdf']:
            return config.file_icons.get('document', "📄 ")

        # Media
        elif suffix in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.ico']:
            return config.file_icons.get('image', "🖼️ ")
        elif suffix in ['.mp4', '.avi', '.mov', '.mkv', '.flv']:
            return config.file_icons.get('video', "🎬 ")
        elif suffix in ['.mp3', '.wav', '.flac', '.aac']:
            return config.file_icons.get('audio', "🎵 ")

        # Archives
        elif suffix in ['.zip', '.tar', '.gz', '.rar', '.7z']:
            return config.file_icons.get('archive', "🗜️ ")

        # Executables
        elif suffix in ['.exe', '.bin', '.sh', '.bat', '.cmd']:
            return config.file_icons.get('executable', "🚀 ")

        # Config files
        elif suffix in ['.ini', '.cfg', '.conf', '.config']:
            return config.file_icons.get('config', "⚙️ ")

        # Binary files
        elif self.file_type == FileType.BINARY:
            return config.file_icons.get('binary', "🔨 ")

        return config.file_icons.get('default', "📄 ")

    def get_display_name(self, config: 'TreeConfig') -> str:
        """Get display name with icon and optional metadata."""
        display_name = self.name

        # Add icon
        icon = self.get_icon(config)
        if icon:
            display_name = icon + display_name

        # Add metadata in parentheses
        metadata_parts = []

        if config.show_size and not self.is_dir:
            metadata_parts.append(format_size(self.size))

        if config.show_file_type and not self.is_dir:
            metadata_parts.append(self.file_type.value)

        if config.show_last_modified:
            from datetime import datetime
            mod_time = datetime.fromtimestamp(self.last_modified).strftime('%Y-%m-%d')
            metadata_parts.append(mod_time)

        if config.show_permissions:
            metadata_parts.append(self.permissions)

        if metadata_parts:
            display_name += f" ({', '.join(metadata_parts)})"

        # Add directory marker
        if self.is_dir:
            display_name += "/"

        return display_name


# ============================================================================
# Tree Builder
# ============================================================================

class TreeBuilder:
    """Builds tree structure from file system."""

    def __init__(self, config: TreeConfig):
        self.config = config
        self._setup_file_walker()
        self._stats = {
            'directories': 0,
            'files': 0,
            'total_size': 0,
            'excluded_items': 0,
            'start_time': None,
            'end_time': None
        }

    def _setup_file_walker(self) -> None:
        """Initialize file system walker."""
        gitignore_parser = None

        if self.config.use_gitignore or self.config.custom_gitignore:
            gitignore_parser = GitIgnoreParser()

            if self.config.custom_gitignore:
                gitignore_parser.load_from_file(self.config.custom_gitignore)
            else:
                gitignore_parser.load_from_file()

        self.file_walker = FileSystemWalker(self.config, gitignore_parser)

    def build_tree(self, root_paths: List[Path]) -> TreeNode:
        """Build tree structure from root paths."""
        self._stats['start_time'] = time.time()

        # Create virtual root if multiple paths
        if len(root_paths) > 1:
            virtual_root = TreeNode("COMBINED VIEW", Path.cwd(), is_dir=True)
            virtual_root.depth = -1  # Special depth for virtual root

            for root_path in root_paths:
                if root_path.exists():
                    root_node = self._build_single_tree(root_path)
                    if root_node:
                        virtual_root.add_child(root_node)

            return virtual_root
        else:
            root_path = root_paths[0]
            if root_path.exists():
                return self._build_single_tree(root_path)
            else:
                raise FileNotFoundError(f"Root path does not exist: {root_path}")

    def _build_single_tree(self, root_path: Path) -> TreeNode:
        """Build tree for a single root directory."""
        # Create root node
        root_node = TreeNode(root_path.name, root_path, is_dir=True)

        # Get all files using FileSystemWalker
        files = self.file_walker.find_files([root_path], recursive=True)

        # Build directory tree from file paths
        dir_structure = defaultdict(list)

        # Group files by directory
        for file_path in files:
            # Skip the root path itself
            if file_path == root_path:
                continue

            rel_path = file_path.relative_to(root_path)
            parts = rel_path.parts

            # Build directory hierarchy
            current_path = root_path
            for part in parts[:-1]:
                current_path = current_path / part
                dir_key = str(current_path.relative_to(root_path))
                if dir_key not in dir_structure:
                    dir_structure[dir_key] = []

            # Add file to its parent directory
            parent_key = str(file_path.parent.relative_to(root_path)) if file_path.parent != root_path else ""
            dir_structure[parent_key].append(file_path)

        # Create directory nodes
        dir_nodes = {str(root_path): root_node}

        # Sort directory keys by depth
        sorted_dirs = sorted(dir_structure.keys(), key=lambda x: len(x.split('/')) if x else 0)

        for dir_key in sorted_dirs:
            parent_key = "/".join(dir_key.split("/")[:-1]) if "/" in dir_key else ""
            dir_name = dir_key.split("/")[-1] if dir_key else ""

            if dir_key:  # Not root
                dir_path = root_path / dir_key
                dir_node = TreeNode(dir_name, dir_path, is_dir=True)
                dir_nodes[dir_key] = dir_node

                # Add to parent
                if parent_key in dir_nodes:
                    dir_nodes[parent_key].add_child(dir_node)
                else:
                    root_node.add_child(dir_node)

            # Add files in this directory
            for file_path in dir_structure[dir_key]:
                file_node = TreeNode(file_path.name, file_path, is_dir=False)
                dir_nodes[dir_key].add_child(file_node)

                # Update statistics
                self._stats['files'] += 1
                self._stats['total_size'] += file_node.size

        # Count directories
        self._stats['directories'] = len(dir_nodes)

        # Sort tree
        self._sort_tree(root_node)

        # Mark last children
        self._mark_last_children(root_node)

        self._stats['end_time'] = time.time()
        self._stats['excluded_items'] = self.file_walker.stats['files_excluded'] + self.file_walker.stats['directories_excluded']

        return root_node

    def _sort_tree(self, node: TreeNode) -> None:
        """Sort tree recursively."""
        node.sort_children(self.config.sort_by, self.config.sort_reverse)
        for child in node.children:
            if child.is_dir:
                self._sort_tree(child)

    def _mark_last_children(self, node: TreeNode) -> None:
        """Mark last child in each level for proper tree rendering."""
        if not node.children:
            return

        for i, child in enumerate(node.children):
            child.is_last = (i == len(node.children) - 1)
            self._mark_last_children(child)

    def get_statistics(self) -> Dict[str, Any]:
        """Get tree statistics."""
        elapsed = self._stats['end_time'] - self._stats['start_time'] if self._stats['end_time'] else 0

        return {
            'directories': self._stats['directories'],
            'files': self._stats['files'],
            'total_size': self._stats['total_size'],
            'excluded_items': self._stats['excluded_items'],
            'processing_time': elapsed,
            'file_walker_stats': self.file_walker.stats
        }


# ============================================================================
# Tree Renderers
# ============================================================================

class TreeRenderer:
    """Base class for tree renderers."""

    def __init__(self, config: TreeConfig):
        self.config = config

    def render(self, node: TreeNode) -> List[str]:
        """Render tree to list of strings."""
        raise NotImplementedError


class TextTreeRenderer(TreeRenderer):
    """Render tree in text format with ASCII/Unicode art."""

    def render(self, node: TreeNode) -> List[str]:
        """Render tree to text lines."""
        lines = []
        self._render_node(node, "", True, lines)
        return lines

    def _render_node(self, node: TreeNode, prefix: str, is_last: bool, lines: List[str]) -> None:
        """Render a single node recursively."""
        # Skip virtual root for display
        if node.depth >= 0:
            # Build line for this node
            if node.depth == 0 and not node.parent:  # Root node
                line = node.get_display_name(self.config)
            else:
                connector = self.config.tree_symbols['last_branch'] if is_last else self.config.tree_symbols['branch']
                line = f"{prefix}{connector}{node.get_display_name(self.config)}"

            lines.append(line)

            # Update prefix for children
            if node.is_dir:
                child_prefix = prefix + (self.config.tree_symbols['space'] if is_last else self.config.tree_symbols['vertical'])

                # Render children
                for i, child in enumerate(node.children):
                    is_child_last = (i == len(node.children) - 1)
                    self._render_node(child, child_prefix, is_child_last, lines)


class MarkdownTreeRenderer(TreeRenderer):
    """Render tree in Markdown format."""

    def render(self, node: TreeNode) -> List[str]:
        """Render tree to Markdown lines."""
        lines = ["# Project Structure\n"]
        self._render_node(node, "", 0, lines)
        return lines

    def _render_node(self, node: TreeNode, prefix: str, level: int, lines: List[str]) -> None:
        """Render a single node recursively for Markdown."""
        if node.depth >= 0:
            # Create Markdown list item
            indent = "  " * level
            bullet = "- "

            if node.is_dir:
                line = f"{indent}{bullet}**{node.name}/**"
            else:
                line = f"{indent}{bullet}{node.name}"

            # Add metadata
            metadata = []
            if self.config.show_size and not node.is_dir:
                metadata.append(format_size(node.size))

            if metadata:
                line += f" *({', '.join(metadata)})*"

            lines.append(line)

            # Render children
            if node.is_dir:
                for child in node.children:
                    self._render_node(child, prefix, level + 1, lines)


class JsonTreeRenderer(TreeRenderer):
    """Render tree in JSON format."""

    def render(self, node: TreeNode) -> List[str]:
        """Render tree to JSON."""
        import json
        tree_dict = self._node_to_dict(node)
        json_str = json.dumps(tree_dict, indent=2, default=str)
        return [json_str]

    def _node_to_dict(self, node: TreeNode) -> Dict[str, Any]:
        """Convert node to dictionary."""
        result = {
            'name': node.name,
            'path': str(node.path),
            'type': 'directory' if node.is_dir else 'file',
            'size': node.size,
            'last_modified': node.last_modified,
        }

        if self.config.show_permissions:
            result['permissions'] = node.permissions

        if self.config.show_file_type:
            result['file_type'] = node.file_type.value

        if node.is_dir and node.children:
            result['children'] = [self._node_to_dict(child) for child in node.children]

        return result


class XmlTreeRenderer(TreeRenderer):
    """Render tree in XML format."""

    def render(self, node: TreeNode) -> List[str]:
        """Render tree to XML."""
        lines = ['<?xml version="1.0" encoding="UTF-8"?>']
        lines.append('<project_structure>')
        self._render_node(node, lines, 1)
        lines.append('</project_structure>')
        return lines

    def _render_node(self, node: TreeNode, lines: List[str], indent_level: int) -> None:
        """Render a single node recursively for XML."""
        indent = "  " * indent_level

        attrs = [
            f'name="{node.name}"',
            f'path="{node.path}"',
            f'type="{"directory" if node.is_dir else "file"}"',
            f'size="{node.size}"',
        ]

        if self.config.show_permissions:
            attrs.append(f'permissions="{node.permissions}"')

        if self.config.show_file_type:
            attrs.append(f'file_type="{node.file_type.value}"')

        if self.config.show_last_modified:
            from datetime import datetime
            mod_time = datetime.fromtimestamp(node.last_modified).strftime('%Y-%m-%d %H:%M:%S')
            attrs.append(f'last_modified="{mod_time}"')

        if node.is_dir and node.children:
            lines.append(f'{indent}<directory {" ".join(attrs)}>')
            for child in node.children:
                self._render_node(child, lines, indent_level + 1)
            lines.append(f'{indent}</directory>')
        else:
            lines.append(f'{indent}<file {" ".join(attrs)} />')


# ============================================================================
# Main Tree Generator
# ============================================================================

class ProjectTreeGenerator:
    """Main class for generating project structure trees."""

    def __init__(self, config: TreeConfig):
        self.config = config
        self._setup_logging()
        self.tree_builder = TreeBuilder(config)
        self.renderer = self._create_renderer()

    def _setup_logging(self) -> None:
        """Configure logging."""
        log_level = logging.DEBUG

        handlers = []

        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        console_handler.setFormatter(logging.Formatter('%(message)s'))
        handlers.append(console_handler)

        # File handler if specified
        if self.config.output_file:
            try:
                file_handler = logging.FileHandler(self.config.output_file, mode='w', encoding='utf-8')
                file_handler.setLevel(logging.INFO)
                file_handler.setFormatter(logging.Formatter('%(message)s'))
                handlers.append(file_handler)
            except Exception as e:
                logging.warning(f"Could not open output file: {e}")

        # Configure root logger
        logging.basicConfig(
            level=log_level,
            handlers=handlers,
            force=True
        )

    def _create_renderer(self) -> TreeRenderer:
        """Create appropriate renderer based on format."""
        if self.config.format == "json":
            return JsonTreeRenderer(self.config)
        elif self.config.format == "xml":
            return XmlTreeRenderer(self.config)
        elif self.config.format == "markdown":
            return MarkdownTreeRenderer(self.config)
        else:  # text
            return TextTreeRenderer(self.config)

    def generate(self, root_paths: List[Path]) -> bool:
        """Generate and output the project tree."""
        try:
            # Validate root paths
            valid_paths = []
            for path in root_paths:
                if not path.exists():
                    logging.error(f"Path does not exist: {path}")
                    return False
                valid_paths.append(path.resolve())

            if not valid_paths:
                logging.error("No valid paths provided")
                return False

            # Build tree
            logging.info(f"Building tree for {len(valid_paths)} path(s)...")
            root_node = self.tree_builder.build_tree(valid_paths)

            # Get statistics
            stats = self.tree_builder.get_statistics()

            # Render tree
            lines = self.renderer.render(root_node)

            # Output tree
            self._output_tree(lines, stats, valid_paths)

            return True

        except Exception as e:
            logging.error(f"Failed to generate tree: {e}")
            return False

    def _output_tree(self, lines: List[str], stats: Dict[str, Any], root_paths: List[Path]) -> None:
        """Output tree with optional headers and statistics."""
        # Output header
        self._output_header(root_paths)

        # Output tree lines
        for line in lines:
            logging.info(line)

        # Output statistics if enabled
        if self.config.include_statistics:
            self._output_statistics(stats)

        # Output summary if enabled
        if self.config.include_summary:
            self._output_summary(stats)

    def _output_header(self, root_paths: List[Path]) -> None:
        """Output tree header."""
        if self.config.format == "text":
            if len(root_paths) > 1:
                logging.info(f"PROJECT TREES: {', '.join(p.name for p in root_paths)}")
            else:
                logging.info(f"PROJECT TREE: {root_paths[0].name}")

            logging.info(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}")
            logging.info(f"Format: {self.config.format}")
            logging.info(f"Pattern: {self.config.include_pattern}")

            if self.config.max_depth:
                logging.info(f"Max Depth: {self.config.max_depth}")

            # Show filters
            filters = []
            if self.config.exclude_dirs:
                filters.append(f"Excluded dirs: {', '.join(self.config.exclude_dirs)}")
            if self.config.exclude_names:
                filters.append(f"Excluded names: {', '.join(self.config.exclude_names)}")
            if self.config.exclude_patterns:
                filters.append(f"Excluded patterns: {', '.join(self.config.exclude_patterns)}")

            if filters:
                logging.info("Filters:")
                for filter_str in filters:
                    logging.info(f"  - {filter_str}")

            if self.config.use_gitignore or self.config.custom_gitignore:
                logging.info("Gitignore: Enabled")

            logging.info("=" * 60)

    def _output_statistics(self, stats: Dict[str, Any]) -> None:
        """Output tree statistics."""
        if self.config.format == "text":
            logging.info("=" * 60)
            logging.info("STATISTICS:")
            logging.info(f"  Directories: {stats['directories']}")
            logging.info(f"  Files: {stats['files']}")
            logging.info(f"  Total Size: {format_size(stats['total_size'])}")
            logging.info(f"  Excluded Items: {stats['excluded_items']}")
            logging.info(f"  Processing Time: {stats['processing_time']:.2f}s")

            if self.config.max_depth:
                logging.info(f"  Max Depth: {self.config.max_depth}")

    def _output_summary(self, stats: Dict[str, Any]) -> None:
        """Output tree summary."""
        if self.config.format == "text":
            logging.info("=" * 60)
            logging.info("SUMMARY:")

            avg_file_size = stats['total_size'] / stats['files'] if stats['files'] > 0 else 0
            logging.info(f"  Average File Size: {format_size(avg_file_size)}")

            files_per_dir = stats['files'] / stats['directories'] if stats['directories'] > 0 else 0
            logging.info(f"  Files per Directory: {files_per_dir:.1f}")

            logging.info(f"  Tree generated in {stats['processing_time']:.2f} seconds")
            logging.info("=" * 60)


# ============================================================================
# CLI Interface
# ============================================================================

def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Advanced project structure visualizer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic tree of current directory
  %(prog)s

  # Tree with file sizes and last modified dates
  %(prog)s --show-size --show-last-modified

  # Tree of specific directories with depth limit
  %(prog)s src/ tests/ --max-depth 3

  # JSON output for programmatic processing
  %(prog)s --format json --output structure.json

  # Markdown output for documentation
  %(prog)s --format markdown --output README.md

  # Tree with icons and colors
  %(prog)s --show-icons --color-output

  # Tree sorted by file size (largest first)
  %(prog)s --sort-by size --sort-reverse
        """
    )

    # Input sources
    input_group = parser.add_argument_group('Input Sources')
    input_group.add_argument(
        'directories',
        nargs='*',
        default=['.'],
        help='Directories to visualize (default: current directory)'
    )
    input_group.add_argument(
        '-p', '--pattern',
        default='*',
        help='File pattern to include (e.g., "*.py", "*.txt")'
    )
    input_group.add_argument(
        '--max-depth',
        type=int,
        help='Maximum recursion depth'
    )

    # Output format
    format_group = parser.add_argument_group('Output Format')
    format_group.add_argument(
        '-f', '--format',
        choices=['text', 'json', 'xml', 'markdown'],
        default='text',
        help='Output format (default: text)'
    )
    format_group.add_argument(
        '-o', '--output',
        type=Path,
        help='Output file (default: stdout)'
    )

    # Display options
    display_group = parser.add_argument_group('Display Options')
    display_group.add_argument(
        '--show-size',
        action='store_true',
        help='Show file sizes'
    )
    display_group.add_argument(
        '--show-permissions',
        action='store_true',
        help='Show file permissions'
    )
    display_group.add_argument(
        '--show-last-modified',
        action='store_true',
        help='Show last modified dates'
    )
    display_group.add_argument(
        '--show-file-type',
        action='store_true',
        help='Show file types'
    )
    display_group.add_argument(
        '--show-hidden',
        action='store_true',
        help='Show hidden files and directories'
    )
    display_group.add_argument(
        '--show-icons',
        action='store_true',
        default=True,
        help='Show file type icons (default: True)'
    )
    display_group.add_argument(
        '--no-icons',
        action='store_false',
        dest='show_icons',
        help='Hide file type icons'
    )
    display_group.add_argument(
        '--color-output',
        action='store_true',
        default=True,
        help='Use colored output (default: True)'
    )
    display_group.add_argument(
        '--no-color',
        action='store_false',
        dest='color_output',
        help='Disable colored output'
    )

    # Sorting
    sort_group = parser.add_argument_group('Sorting')
    sort_group.add_argument(
        '--sort-by',
        choices=['name', 'size', 'modified', 'type'],
        default='name',
        help='Sort criteria (default: name)'
    )
    sort_group.add_argument(
        '--sort-reverse',
        action='store_true',
        help='Reverse sort order'
    )

    # Filtering
    filter_group = parser.add_argument_group('Filtering')
    filter_group.add_argument(
        '-ed', '--exclude-dir',
        action='append',
        dest='exclude_dirs',
        help='Exclude directory by name (can be repeated)'
    )
    filter_group.add_argument(
        '-en', '--exclude-name',
        action='append',
        dest='exclude_names',
        help='Exclude file by name/wildcard (can be repeated)'
    )
    filter_group.add_argument(
        '-ep', '--exclude-pattern',
        action='append',
        dest='exclude_patterns',
        help='Exclude by path pattern (can be repeated)'
    )
    filter_group.add_argument(
        '--exclude-empty-dirs',
        action='store_true',
        help='Exclude empty directories'
    )

    # Gitignore
    gitignore_group = parser.add_argument_group('Gitignore')
    gitignore_group.add_argument(
        '-gi', '--gitignore',
        type=Path,
        help='Use specific .gitignore file'
    )
    gitignore_group.add_argument(
        '-ig', '--use-gitignore',
        action='store_true',
        help='Auto-discover and use .gitignore files'
    )
    gitignore_group.add_argument(
        '--no-gitignore',
        action='store_true',
        help='Ignore .gitignore files'
    )

    # Statistics
    stats_group = parser.add_argument_group('Statistics')
    stats_group.add_argument(
        '--no-statistics',
        action='store_false',
        dest='include_statistics',
        default=True,
        help='Do not show statistics'
    )
    stats_group.add_argument(
        '--no-summary',
        action='store_false',
        dest='include_summary',
        default=True,
        help='Do not show summary'
    )

    # Tree style
    style_group = parser.add_argument_group('Tree Style')
    style_group.add_argument(
        '--indent-size',
        type=int,
        default=4,
        help='Indentation size (default: 4)'
    )
    style_group.add_argument(
        '--indent-style',
        choices=['tree', 'spaces', 'dashes'],
        default='tree',
        help='Indentation style (default: tree)'
    )
    style_group.add_argument(
        '--max-width',
        type=int,
        help='Maximum line width (for wrapping)'
    )

    args = parser.parse_args()

    # Convert show_hidden to appropriate exclude pattern
    if not args.show_hidden:
        if args.exclude_names is None:
            args.exclude_names = []
        args.exclude_names.extend(['.*', '.*/'])

    return args


def create_config_from_args(args) -> TreeConfig:
    """Create configuration from command line arguments."""
    return TreeConfig(
        # Filtering
        exclude_dirs=set(args.exclude_dirs or []),
        exclude_names=set(args.exclude_names or []),
        exclude_patterns=set(args.exclude_patterns or []),
        include_pattern=args.pattern,
        max_depth=args.max_depth,

        # Gitignore
        use_gitignore=args.use_gitignore and not args.no_gitignore,
        custom_gitignore=args.gitignore,

        # Output
        output_file=args.output,
        format=args.format,

        # Display options
        show_size=args.show_size,
        show_permissions=args.show_permissions,
        show_last_modified=args.show_last_modified,
        show_file_type=args.show_file_type,
        show_icons=args.show_icons,
        color_output=args.color_output,

        # Sorting
        sort_by=args.sort_by,
        sort_reverse=args.sort_reverse,

        # Tree style
        indent_size=args.indent_size,
        indent_style=args.indent_style,
        max_width=args.max_width,

        # Statistics
        include_statistics=args.include_statistics,
        include_summary=args.include_summary,

        # Other
        exclude_empty_dirs=args.exclude_empty_dirs,

        # File operations
        recursive=True,  # Always recursive for tree
        directories=args.directories
    )


def main():
    """Main entry point."""
    try:
        args = parse_arguments()
        config = create_config_from_args(args)

        generator = ProjectTreeGenerator(config)

        # Convert directory strings to Path objects
        root_paths = [Path(d).resolve() for d in args.directories]

        success = generator.generate(root_paths)

        return 0 if success else 1

    except KeyboardInterrupt:
        print("\n\nOperation cancelled by user")
        return 130
    except Exception as e:
        logging.error(f"Fatal error: {e}")
        return 1


if __name__ == '__main__':
    exit(main())
