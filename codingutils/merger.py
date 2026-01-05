"""
Script for merging multiple files into one with file headers.
"""

import argparse
import os
import fnmatch
import sys
import re
from pathlib import Path
from typing import List, Optional, Set
import re

class GitIgnoreParser:
    """Parse and apply .gitignore patterns."""
    
    def __init__(self, gitignore_path: Optional[Path] = None):
        self.patterns = []
        if gitignore_path and gitignore_path.exists():
            self.parse_gitignore(gitignore_path)
    
    def parse_gitignore(self, gitignore_path: Path):
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
    
    def should_ignore(self, file_path: Path, root_dir: Path) -> bool:
        """Check if file should be ignored based on .gitignore patterns."""
        if not self.patterns:
            return False
        
        try:
            relative_path = file_path.relative_to(root_dir)
        except ValueError:
            return False
        
        rel_path_str = str(relative_path).replace(os.sep, '/')
        
        for pattern in self.patterns:
            if self._matches_pattern(rel_path_str, pattern):
                return True
        
        return False
    
    def _matches_pattern(self, rel_path: str, pattern: str) -> bool:
        """Check if relative path matches gitignore pattern."""
        is_dir_pattern = pattern.endswith('/')
        if is_dir_pattern:
            pattern = pattern.rstrip('/')
        
        regex_pattern = self._convert_to_regex(pattern)
        
        if regex_pattern.match(rel_path):
            if is_dir_pattern:
                return True
            return True
        
        return False
    
    def _convert_to_regex(self, pattern: str) -> re.Pattern:
        """Convert gitignore pattern to regex."""
        if pattern.startswith('/'):
            pattern = pattern[1:]
        
        is_dir_pattern = pattern.endswith('/')
        if is_dir_pattern:
            pattern = pattern.rstrip('/')
        
        regex_chars = r'.^$+{}[]|()\\'
        result = []
        i = 0
        
        while i < len(pattern):
            char = pattern[i]
            
            if char == '*':
                if i + 1 < len(pattern) and pattern[i + 1] == '*':
                    result.append('.*')
                    i += 2
                else:
                    result.append('[^/]*')
                    i += 1
            elif char == '?':
                result.append('[^/]')
                i += 1
            elif char in regex_chars:
                result.append('\\' + char)
                i += 1
            else:
                result.append(char)
                i += 1
        
        regex_str = ''.join(result)
        
        if not pattern.startswith('*') and not pattern.startswith('**'):
            regex_str = r'(^|/)' + regex_str
        
        if is_dir_pattern:
            regex_str += r'(/|$)'
        elif not pattern.endswith('*'):
            regex_str += r'($|/)'
        
        return re.compile(regex_str)

class FileMerger:
    """Merge multiple files into one with headers."""
    
    def __init__(self, config):
        self.config = config
        self.root_dir = Path.cwd()
        self.gitignore_parser = None

        if self.config.gitignore:
            gitignore_path = Path(self.config.gitignore)
            if gitignore_path.exists():
                self.gitignore_parser = GitIgnoreParser(gitignore_path)
            else:
                print(f"Warning: Gitignore file '{self.config.gitignore}' not found", file=sys.stderr)
        elif self.config.use_gitignore:
            current_gitignore = Path('.gitignore')
            if current_gitignore.exists():
                self.gitignore_parser = GitIgnoreParser(current_gitignore)
                print(f"Auto-discovered .gitignore: {current_gitignore.resolve()}", file=sys.stderr)
    
    def get_relative_path(self, file_path: str) -> str:
        """Get relative path from project root."""
        try:
            absolute_path = Path(file_path).resolve()
            relative_path = absolute_path.relative_to(self.root_dir)
            return str(relative_path)
        except ValueError:
            return str(absolute_path)
    
    def should_exclude(self, file_path: Path) -> bool:
        """Check if file should be excluded based on all filters."""
        relative_path = str(file_path.relative_to(self.root_dir)) if file_path.is_relative_to(self.root_dir) else str(file_path)
        file_name = file_path.name
        
        if self.gitignore_parser:
            if self.gitignore_parser.should_ignore(file_path, self.root_dir):
                return True
        
        if self.config.exclude_dirs:
            for exclude_dir in self.config.exclude_dirs:
                if exclude_dir in relative_path.split(os.sep):
                    parts = relative_path.split(os.sep)
                    if exclude_dir in parts:
                        return True
        
        if self.config.exclude_names:
            for exclude_name in self.config.exclude_names:
                if fnmatch.fnmatch(file_name, exclude_name):
                    return True
        
        if self.config.exclude_patterns:
            for exclude_pattern in self.config.exclude_patterns:
                if fnmatch.fnmatch(file_name, exclude_pattern):
                    return True
                if fnmatch.fnmatch(relative_path, exclude_pattern):
                    return True
        
        return False
    
    def find_files(self) -> List[str]:
        """Find files based on configuration."""
        files = []
        
        if self.config.files:
            for file_path in self.config.files:
                path = Path(file_path)
                if path.exists() and path.is_file():
                    if not self.should_exclude(path):
                        files.append(str(path))
                    else:
                        print(f"Info: File '{file_path}' excluded by filter", file=sys.stderr)
                else:
                    print(f"Warning: File '{file_path}' not found, skipping", file=sys.stderr)
            return files
        
        search_paths = []
        if self.config.directories:
            for dir_path in self.config.directories:
                path = Path(dir_path)
                if path.exists() and path.is_dir():
                    search_paths.append(path)
                else:
                    print(f"Warning: Directory '{dir_path}' not found, skipping", file=sys.stderr)
        else:
            search_paths.append(Path('.'))
        
        for search_path in search_paths:
            if self.config.recursive:
                for file_path in search_path.rglob(self.config.pattern):
                    if file_path.is_file():
                        if not self.should_exclude(file_path):
                            files.append(str(file_path))
            else:
                for item in search_path.iterdir():
                    if item.is_file() and fnmatch.fnmatch(item.name, self.config.pattern):
                        if not self.should_exclude(item):
                            files.append(str(item))
        
        return sorted(set(files))
    
    def create_header(self, file_path: str) -> str:
        """Create header for file with relative path."""
        relative_path = self.get_relative_path(file_path)
        header = f"\n{'='*60}\n"
        header += f"FILE: {relative_path}\n"
        header += f"{'='*60}\n"
        return header
    
    def merge_files(self) -> bool:
        """Merge files into output file."""
        files = self.find_files()
        
        if not files:
            print("No files found to merge", file=sys.stderr)
            return False
        
        print(f"Found {len(files)} files to merge:")
        for file_path in files:
            print(f"  - {self.get_relative_path(file_path)}")
        
        try:
            output_path = Path(self.config.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_path, 'w', encoding='utf-8') as output_file:
                output_file.write(f"MERGED FILES: {len(files)} files\n")
                output_file.write(f"MERGE DATE: {os.popen('date').read().strip()}\n")
                output_file.write(f"ROOT DIRECTORY: {self.root_dir}\n")
                
                has_exclusions = (self.config.exclude_dirs or self.config.exclude_names or 
                                self.config.exclude_patterns or self.config.gitignore or 
                                self.config.use_gitignore)
                
                if has_exclusions:
                    output_file.write("EXCLUSIONS APPLIED:\n")
                    if self.config.exclude_dirs:
                        output_file.write(f"  Directories: {', '.join(self.config.exclude_dirs)}\n")
                    if self.config.exclude_names:
                        output_file.write(f"  Names: {', '.join(self.config.exclude_names)}\n")
                    if self.config.exclude_patterns:
                        output_file.write(f"  Patterns: {', '.join(self.config.exclude_patterns)}\n")
                    if self.config.gitignore:
                        output_file.write(f"  Gitignore file: {self.config.gitignore}\n")
                    elif self.config.use_gitignore:
                        output_file.write(f"  Gitignore: auto-discovered .gitignore\n")
                
                output_file.write("=" * 60 + "\n\n")
                
                for file_path in files:
                    try:
                        output_file.write(self.create_header(file_path))
                        
                        with open(file_path, 'r', encoding='utf-8') as input_file:
                            content = input_file.read()
                            output_file.write(content)
                            
                            if content and not content.endswith('\n'):
                                output_file.write('\n')
                                
                    except UnicodeDecodeError:
                        try:
                            with open(file_path, 'r', encoding='latin-1') as input_file:
                                content = input_file.read()
                                output_file.write(self.create_header(file_path))
                                output_file.write(content)
                                if content and not content.endswith('\n'):
                                    output_file.write('\n')
                        except Exception as e:
                            print(f"Error reading {file_path}: {e}", file=sys.stderr)
                            output_file.write(f"\n[ERROR READING FILE: {e}]\n")
                    
                    except Exception as e:
                        print(f"Error processing {file_path}: {e}", file=sys.stderr)
                        output_file.write(self.create_header(file_path))
                        output_file.write(f"[ERROR READING FILE: {e}]\n")
            
            relative_output = self.get_relative_path(str(output_path))
            print(f"\nSuccessfully merged {len(files)} files into: {relative_output}")
            print(f"Total output file size: {output_path.stat().st_size} bytes")
            
            return True
            
        except Exception as e:
            print(f"Error writing output file: {e}", file=sys.stderr)
            return False
    
    def preview_merge(self) -> bool:
        """Preview what files would be merged without actually merging."""
        files = self.find_files()
        
        if not files:
            print("No files found to merge", file=sys.stderr)
            return False
        
        print(f"PREVIEW - Found {len(files)} files that would be merged:")
        print("-" * 80)
        
        total_size = 0
        for file_path in files:
            relative_path = self.get_relative_path(file_path)
            size = os.path.getsize(file_path)
            total_size += size
            print(f"{relative_path} ({size} bytes)")
        
        print("-" * 80)
        print(f"Total: {len(files)} files, {total_size} bytes")
        print(f"Output would be written to: {self.config.output}")
        
        has_exclusions = (self.config.exclude_dirs or self.config.exclude_names or 
                         self.config.exclude_patterns or self.config.gitignore or 
                         self.config.use_gitignore)
        
        if has_exclusions:
            print("\nExclusions applied:")
            if self.config.exclude_dirs:
                print(f"  Directories: {', '.join(self.config.exclude_dirs)}")
            if self.config.exclude_names:
                print(f"  Names: {', '.join(self.config.exclude_names)}")
            if self.config.exclude_patterns:
                print(f"  Patterns: {', '.join(self.config.exclude_patterns)}")
            if self.config.gitignore:
                print(f"  Gitignore file: {self.config.gitignore}")
            elif self.config.use_gitignore:
                print(f"  Gitignore: auto-discovered .gitignore")
        
        return True


def main():
    parser = argparse.ArgumentParser(
        description="Merge multiple files into one with file headers",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        'files',
        nargs='*',
        help='Explicit list of files to merge (overrides directory search)'
    )
    
    parser.add_argument(
        '-d', '--directory',
        action='append',
        dest='directories',
        help='Directory to search files in (can be used multiple times, default: current directory)'
    )
    
    parser.add_argument(
        '-r', '--recursive',
        action='store_true',
        help='Search recursively in subdirectories'
    )
    
    parser.add_argument(
        '-p', '--pattern',
        default='*',
        help='File pattern to search (e.g., "*.py" or "model_*.txt")'
    )
    
    parser.add_argument(
        '-o', '--output',
        default='merged_files.txt',
        help='Output file for merged content (default: merged_files.txt)'
    )
    
    parser.add_argument(
        '--preview',
        action='store_true',
        help='Preview what would be merged without actually merging'
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
        help='Exclude file by exact name or wildcard (can be used multiple times, e.g., "*.tmp" or "temp_*")'
    )
    
    parser.add_argument(
        '-ep', '--exclude-pattern',
        action='append',
        dest='exclude_patterns',
        help='Exclude by pattern (can be used multiple times, supports wildcards in paths)'
    )
    
    parser.add_argument(
        '-gi', '--gitignore',
        help='Use specific .gitignore file for filtering'
    )
    
    parser.add_argument(
        '-ig', '--use-gitignore',
        action='store_true',
        help='Auto-discover and use .gitignore file in current directory'
    )
    
    args = parser.parse_args()
    
    if args.exclude_dirs is None:
        args.exclude_dirs = []
    if args.exclude_names is None:
        args.exclude_names = []
    if args.exclude_patterns is None:
        args.exclude_patterns = []
    
    merger = FileMerger(args)
    
    if args.preview:
        return 0 if merger.preview_merge() else 1
    else:
        return 0 if merger.merge_files() else 1


if __name__ == '__main__':
    exit(main())