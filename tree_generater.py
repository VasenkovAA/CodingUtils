"""
Project structure mapper with .gitignore support.
Cross-platform alternative to 'tree' command.
"""

import argparse
import os
import fnmatch
import sys
from pathlib import Path
from typing import List, Set, Optional
import logging


class GitIgnoreParser:
    """Parser for .gitignore files with support for patterns."""
    
    def __init__(self):
        self.patterns = []
    
    def parse_file(self, gitignore_path: Path) -> None:
        """Parse .gitignore file and extract patterns."""
        if not gitignore_path.exists():
            return
        
        with open(gitignore_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                
                if not line or line.startswith('#'):
                    continue
                
                self.patterns.append(line)
    
    def should_ignore(self, path: Path, root_dir: Path) -> bool:
        """Check if path should be ignored based on .gitignore patterns."""
        if not self.patterns:
            return False
        
        try:
            relative_path = path.relative_to(root_dir)
        except ValueError:
            return False
        
        path_str = str(relative_path).replace('\\', '/')
        
        for pattern in self.patterns:
            if pattern.endswith('/'):
                dir_pattern = pattern.rstrip('/')
                if path.is_dir() and fnmatch.fnmatch(path_str, dir_pattern):
                    return True
                if fnmatch.fnmatch(path_str, dir_pattern + '/*'):
                    return True
            
            elif pattern.startswith('!'):
                neg_pattern = pattern[1:]
                if fnmatch.fnmatch(path_str, neg_pattern):
                    return False
            
            else:
                if fnmatch.fnmatch(path_str, pattern):
                    return True
                if fnmatch.fnmatch(path_str + '/', pattern + '/*'):
                    return True
        
        return False


class ProjectMapper:
    """Create project structure tree with .gitignore support."""
    
    def __init__(self, config):
        self.config = config
        self.root_dir = Path(config.directory).resolve()
        self.gitignore_parser = GitIgnoreParser()
        self.found_gitignore = False
        
    def setup_logging(self):
        """Setup logging based on configuration."""
        if self.config.output:
            logging.basicConfig(
                filename=self.config.output,
                level=logging.INFO,
                format='%(message)s'
            )
        else:
            logging.basicConfig(level=logging.INFO, format='%(message)s')
    
    def load_gitignore(self) -> None:
        """Load .gitignore file from specified location or auto-discover."""
        if self.config.gitignore:
            gitignore_path = Path(self.config.gitignore)
            if gitignore_path.exists():
                self.gitignore_parser.parse_file(gitignore_path)
                self.found_gitignore = True
                logging.info(f"Using .gitignore: {gitignore_path}")
            else:
                logging.warning(f"Specified .gitignore not found: {gitignore_path}")
        else:
            gitignore_path = self.root_dir / '.gitignore'
            if gitignore_path.exists():
                self.gitignore_parser.parse_file(gitignore_path)
                self.found_gitignore = True
                logging.info(f"Auto-discovered .gitignore: {gitignore_path}")
    
    def should_include_path(self, path: Path, is_dir: bool = False) -> bool:
        """Check if path should be included in the tree."""
        if path.name == '.git' and is_dir:
            return False
        
        if self.gitignore_parser.should_ignore(path, self.root_dir):
            return False
        
        if self.config.pattern != '*':
            if not fnmatch.fnmatch(path.name, self.config.pattern):
                return False
        
        return True
    
    def get_tree_structure(self) -> List[str]:
        """Generate tree structure of the project."""
        lines = []
        
        def add_directory_contents(directory: Path, prefix: str = "", is_last: bool = True):
            """Recursively add directory contents to tree."""
            try:
                items = []
                for item in directory.iterdir():
                    if self.should_include_path(item, item.is_dir()):
                        items.append(item)
                
                items.sort(key=lambda x: (not x.is_dir(), x.name.lower()))
                
                for index, item in enumerate(items):
                    is_last_item = index == len(items) - 1
                    
                    if item.is_dir():
                        connector = "└── " if is_last_item else "├── "
                        lines.append(f"{prefix}{connector}{item.name}/")
                        
                        new_prefix = prefix + ("    " if is_last_item else "│   ")
                        add_directory_contents(item, new_prefix, is_last_item)
                    else:
                        connector = "└── " if is_last_item else "├── "
                        lines.append(f"{prefix}{connector}{item.name}")
                        
            except PermissionError:
                lines.append(f"{prefix}└── [Permission Denied]")
        
        lines.append(f"{self.root_dir.name}/")
        add_directory_contents(self.root_dir)
        
        return lines
    
    def get_statistics(self) -> dict:
        """Get statistics about the project structure."""
        stats = {
            'directories': 0,
            'files': 0,
            'total_size': 0
        }
        
        def collect_stats(directory: Path):
            """Recursively collect statistics."""
            try:
                for item in directory.iterdir():
                    if not self.should_include_path(item, item.is_dir()):
                        continue
                    
                    if item.is_dir():
                        stats['directories'] += 1
                        collect_stats(item)
                    else:
                        stats['files'] += 1
                        try:
                            stats['total_size'] += item.stat().st_size
                        except (OSError, FileNotFoundError):
                            pass
            except PermissionError:
                pass
        
        collect_stats(self.root_dir)
        return stats
    
    def generate_tree(self) -> bool:
        """Generate and output the project tree."""
        if not self.root_dir.exists():
            logging.error(f"Directory does not exist: {self.root_dir}")
            return False
        
        if not self.root_dir.is_dir():
            logging.error(f"Path is not a directory: {self.root_dir}")
            return False
        
        self.load_gitignore()
        
        tree_lines = self.get_tree_structure()
        
        stats = self.get_statistics()
        
        logging.info(f"Project Tree: {self.root_dir}")
        logging.info(f"Pattern: {self.config.pattern}")
        if self.found_gitignore:
            logging.info(".gitignore: Applied")
        else:
            logging.info(".gitignore: Not found or not specified")
        logging.info("=" * 60)
        
        for line in tree_lines:
            logging.info(line)
        
        logging.info("=" * 60)
        logging.info(f"Statistics:")
        logging.info(f"  Directories: {stats['directories']}")
        logging.info(f"  Files: {stats['files']}")
        logging.info(f"  Total Size: {self.format_size(stats['total_size'])}")
        
        return True
    
    def format_size(self, size_bytes: int) -> str:
        """Format file size in human-readable format."""
        if size_bytes == 0:
            return "0 B"
        
        size_names = ["B", "KB", "MB", "GB"]
        i = 0
        size = float(size_bytes)
        
        while size >= 1024 and i < len(size_names) - 1:
            size /= 1024
            i += 1
        
        return f"{size:.2f} {size_names[i]}"


def main():
    parser = argparse.ArgumentParser(
        description="Project structure mapper with .gitignore support",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        '-d', '--directory',
        default='.',
        help='Directory to map (default: current directory)'
    )
    
    parser.add_argument(
        '-i', '--gitignore',
        help='Path to .gitignore file (default: auto-discover in root)'
    )
    
    parser.add_argument(
        '-p', '--pattern',
        default='*',
        help='File pattern to include (e.g., "*.py" or "*.txt")'
    )
    
    parser.add_argument(
        '-o', '--output',
        help='Output file for tree (default: console)'
    )
    
    parser.add_argument(
        '--no-gitignore',
        action='store_true',
        help='Ignore .gitignore files even if present'
    )
    
    args = parser.parse_args()
    
    if args.no_gitignore:
        args.gitignore = None
    
    mapper = ProjectMapper(args)
    mapper.setup_logging()
    
    success = mapper.generate_tree()
    
    return 0 if success else 1


if __name__ == '__main__':
    exit(main())
