"""
Project structure mapper with .gitignore support.
Cross-platform alternative to 'tree' command.
"""

import argparse
import os
import fnmatch
import sys
import re
from pathlib import Path
from typing import List, Set, Optional
import logging


class GitIgnoreParser:
    """Parser for .gitignore files with support for patterns."""
    
    def __init__(self, gitignore_path: Optional[Path] = None):
        self.patterns = []
        if gitignore_path and gitignore_path.exists():
            self.parse_gitignore(gitignore_path)
    
    def parse_gitignore(self, gitignore_path: Path) -> None:
        """Parse .gitignore file and extract patterns."""
        try:
            with open(gitignore_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    
                    if not line or line.startswith('#'):
                        continue
                    
                    self.patterns.append(line)
        except Exception as e:
            print(f"Warning: Could not parse .gitignore file: {e}", file=sys.stderr)
    
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
        self.gitignore_parser = None
        self.found_gitignore = False
        self.output_file = None
        self.excluded_count = 0
        
        if self.config.directories:
            self.directories = [Path(dir_path).resolve() for dir_path in self.config.directories]
            self.root_dir = self.directories[0] if len(self.directories) == 1 else Path.cwd()
        else:
            self.directories = [Path('.').resolve()]
            self.root_dir = self.directories[0]
        
        if self.config.gitignore:
            gitignore_path = Path(self.config.gitignore)
            if gitignore_path.exists():
                self.gitignore_parser = GitIgnoreParser(gitignore_path)
                self.found_gitignore = True
        elif self.config.use_gitignore and not self.config.no_gitignore:
            self.gitignore_parser = GitIgnoreParser()
            for directory in self.directories:
                gitignore_path = directory / '.gitignore'
                if gitignore_path.exists():
                    self.gitignore_parser.parse_gitignore(gitignore_path)
                    self.found_gitignore = True
                    break
    
    def setup_logging(self):
        """Setup logging based on configuration."""
        formatter = logging.Formatter('%(message)s')
        
        if self.config.output:
            try:
                file_handler = logging.FileHandler(self.config.output, mode='w', encoding='utf-8')
                file_handler.setLevel(logging.INFO)
                file_handler.setFormatter(formatter)
                
                self.logger = logging.getLogger('project_mapper')
                self.logger.setLevel(logging.INFO)
                
                self.logger.handlers = []
                
                self.logger.addHandler(file_handler)
                
                self.logger.propagate = False
                
                self.file_handler = file_handler
                
            except Exception as e:
                print(f"Error opening output file: {e}", file=sys.stderr)
                sys.exit(1)
        else:
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            console_handler.setFormatter(formatter)
            
            self.logger = logging.getLogger('project_mapper')
            self.logger.setLevel(logging.INFO)
            self.logger.handlers = []
            self.logger.addHandler(console_handler)
            self.logger.propagate = False
    
    def cleanup(self):
        """Clean up resources."""
        if hasattr(self, 'file_handler'):
            self.file_handler.close()
    
    def should_exclude_path(self, path: Path, is_dir: bool = False) -> bool:
        """Check if path should be excluded based on all filters."""
        path_str = str(path)
        path_name = path.name
        
        if self.gitignore_parser and self.gitignore_parser.should_ignore(path, self.root_dir):
            self.excluded_count += 1
            return True
        
        if self.config.exclude_dirs:
            for exclude_dir in self.config.exclude_dirs:
                if exclude_dir in path_str.split(os.sep):
                    parts = path_str.split(os.sep)
                    if exclude_dir in parts:
                        self.excluded_count += 1
                        return True
        
        if self.config.exclude_names:
            for exclude_name in self.config.exclude_names:
                if fnmatch.fnmatch(path_name, exclude_name):
                    self.excluded_count += 1
                    return True
        
        if self.config.exclude_patterns:
            for exclude_pattern in self.config.exclude_patterns:
                if fnmatch.fnmatch(path_name, exclude_pattern):
                    self.excluded_count += 1
                    return True
                rel_path = str(path.relative_to(path.parents[-len(self.root_dir.parts)])) if path.is_relative_to(self.root_dir) else str(path)
                if fnmatch.fnmatch(rel_path, exclude_pattern):
                    self.excluded_count += 1
                    return True
        
        if self.config.pattern != '*':
            if not fnmatch.fnmatch(path_name, self.config.pattern):
                self.excluded_count += 1
                return False
        
        if path_name == '.git' and is_dir:
            self.excluded_count += 1
            return True
        
        return False
    
    def get_tree_structure(self) -> List[str]:
        """Generate tree structure of the project."""
        lines = []
        
        def add_directory_contents(directory: Path, prefix: str = "", is_last: bool = True, depth: int = 0):
            """Recursively add directory contents to tree."""
            if self.config.max_depth is not None and depth >= self.config.max_depth:
                return
            
            try:
                items = []
                for item in directory.iterdir():
                    if not self.should_exclude_path(item, item.is_dir()):
                        items.append(item)
                
                items.sort(key=lambda x: (not x.is_dir(), x.name.lower()))
                
                for index, item in enumerate(items):
                    is_last_item = index == len(items) - 1
                    
                    if item.is_dir():
                        connector = "└── " if is_last_item else "├── "
                        lines.append(f"{prefix}{connector}{item.name}/")
                        
                        new_prefix = prefix + ("    " if is_last_item else "│   ")
                        add_directory_contents(item, new_prefix, is_last_item, depth + 1)
                    else:
                        connector = "└── " if is_last_item else "├── "
                        lines.append(f"{prefix}{connector}{item.name}")
                        
            except PermissionError:
                lines.append(f"{prefix}└── [Permission Denied]")
            except Exception as e:
                lines.append(f"{prefix}└── [Error: {str(e)}]")
        
        if len(self.directories) > 1:
            lines.append("COMBINED VIEW/")
            for index, directory in enumerate(self.directories):
                if directory.exists() and directory.is_dir():
                    is_last_dir = index == len(self.directories) - 1
                    connector = "└── " if is_last_dir else "├── "
                    lines.append(f"{connector}{directory.name}/")
                    
                    prefix = "    " if is_last_dir else "│   "
                    add_directory_contents(directory, prefix, is_last_dir)
        else:
            directory = self.directories[0]
            lines.append(f"{directory.name}/")
            add_directory_contents(directory)
        
        return lines
    
    def get_statistics(self) -> dict:
        """Get statistics about the project structure."""
        stats = {
            'directories': 0,
            'files': 0,
            'total_size': 0,
            'directories_scanned': 0
        }
        
        def collect_stats(directory: Path, depth: int = 0):
            """Recursively collect statistics."""
            if self.config.max_depth is not None and depth > self.config.max_depth:
                return
            
            try:
                for item in directory.iterdir():
                    if self.should_exclude_path(item, item.is_dir()):
                        continue
                    
                    if item.is_dir():
                        stats['directories'] += 1
                        stats['directories_scanned'] += 1
                        collect_stats(item, depth + 1)
                    else:
                        stats['files'] += 1
                        try:
                            stats['total_size'] += item.stat().st_size
                        except (OSError, FileNotFoundError):
                            pass
            except PermissionError:
                pass
        
        for directory in self.directories:
            if directory.exists() and directory.is_dir():
                collect_stats(directory)
        
        return stats
    
    def generate_tree(self) -> bool:
        """Generate and output the project tree."""
        for directory in self.directories:
            if not directory.exists():
                self.logger.error(f"Directory does not exist: {directory}")
                return False
            if not directory.is_dir():
                self.logger.error(f"Path is not a directory: {directory}")
                return False
        
        tree_lines = self.get_tree_structure()
        
        stats = self.get_statistics()
        
        if len(self.directories) > 1:
            self.logger.info(f"Project Trees (Combined): {', '.join(str(d.name) for d in self.directories)}")
        else:
            self.logger.info(f"Project Tree: {self.directories[0]}")
        
        self.logger.info(f"Pattern: {self.config.pattern}")
        
        if self.found_gitignore:
            if self.config.gitignore:
                self.logger.info(f".gitignore: {self.config.gitignore}")
            else:
                self.logger.info(".gitignore: Auto-discovered and applied")
        elif self.config.no_gitignore:
            self.logger.info(".gitignore: Explicitly disabled")
        else:
            self.logger.info(".gitignore: Not found or not specified")
        
        if (self.config.exclude_dirs or self.config.exclude_names or 
            self.config.exclude_patterns):
            self.logger.info("Exclusions applied:")
            if self.config.exclude_dirs:
                self.logger.info(f"  Directories: {', '.join(self.config.exclude_dirs)}")
            if self.config.exclude_names:
                self.logger.info(f"  Names: {', '.join(self.config.exclude_names)}")
            if self.config.exclude_patterns:
                self.logger.info(f"  Patterns: {', '.join(self.config.exclude_patterns)}")
        
        self.logger.info("=" * 60)
        
        for line in tree_lines:
            self.logger.info(line)
        
        self.logger.info("=" * 60)
        
        self.logger.info(f"Statistics:")
        self.logger.info(f"  Directories: {stats['directories']}")
        self.logger.info(f"  Files: {stats['files']}")
        self.logger.info(f"  Excluded items: {self.excluded_count}")
        self.logger.info(f"  Total Size: {self.format_size(stats['total_size'])}")
        
        if self.config.max_depth is not None:
            self.logger.info(f"  Max Depth: {self.config.max_depth}")
        
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
        action='append',
        dest='directories',
        help='Directory to map (can be used multiple times, default: current directory)'
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
        '-i', '--gitignore',
        help='Path to .gitignore file'
    )
    
    parser.add_argument(
        '-ig', '--use-gitignore',
        action='store_true',
        help='Auto-discover and use .gitignore file in directory'
    )
    
    parser.add_argument(
        '--no-gitignore',
        action='store_true',
        help='Ignore .gitignore files even if present'
    )

    parser.add_argument(
        '-ed', '--exclude-dir',
        action='append',
        dest='exclude_dirs',
        help='Exclude directory by name (can be used multiple times)'
    )
    
    parser.add_argument(
        '-en', '--exclude-name',
        action='append',
        dest='exclude_names',
        help='Exclude file by exact name or wildcard (can be used multiple times)'
    )
    
    parser.add_argument(
        '-ep', '--exclude-pattern',
        action='append',
        dest='exclude_patterns',
        help='Exclude by pattern (can be used multiple times, supports wildcards)'
    )

    parser.add_argument(
        '--max-depth',
        type=int,
        help='Maximum recursion depth (default: unlimited)'
    )
    
    args = parser.parse_args()

    if args.exclude_dirs is None:
        args.exclude_dirs = []
    if args.exclude_names is None:
        args.exclude_names = []
    if args.exclude_patterns is None:
        args.exclude_patterns = []
    
    mapper = ProjectMapper(args)
    mapper.setup_logging()
    
    try:
        success = mapper.generate_tree()
    finally:
        mapper.cleanup()
    
    return 0 if success else 1


if __name__ == '__main__':
    exit(main())