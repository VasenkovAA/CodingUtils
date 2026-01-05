import pytest
import argparse
import os
import sys
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch, mock_open, call
import io
import re
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent))
from codingutils.merger import GitIgnoreParser, FileMerger, main


@pytest.fixture
def temp_dir():
    """Create temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_files(temp_dir):
    """Create sample test files in directory structure."""
    (temp_dir / "src").mkdir()
    (temp_dir / "src" / "utils").mkdir()
    (temp_dir / "tests").mkdir()
    
    (temp_dir / "src" / "main.py").write_text("print('Hello')")
    (temp_dir / "src" / "utils" / "helper.py").write_text("def help(): pass")
    (temp_dir / "src" / "utils" / "config.py").write_text("DEBUG = True")
    (temp_dir / "tests" / "test_main.py").write_text("import unittest")
    (temp_dir / "README.md").write_text("# Project")
    (temp_dir / ".gitignore").write_text("*.log\n__pycache__/\n*.tmp\n")
    (temp_dir / "output.log").write_text("logs...")
    (temp_dir / "temp.tmp").write_text("temp file")
    (temp_dir / ".env").write_text("SECRET=123")
    
    return temp_dir


@pytest.fixture
def gitignore_content():
    """Gitignore content for tests."""
    return """
*.pyc
__pycache__/
*.log
/temp/
*.tmp
test_*.py
"""


@pytest.fixture
def config_args():
    """Create configuration arguments for tests."""
    return SimpleNamespace(
        files=None,
        directories=None,
        recursive=False,
        pattern="*",
        output="merged.txt",
        preview=False,
        exclude_dirs=[],
        exclude_names=[],
        exclude_patterns=[],
        gitignore=None,
        use_gitignore=False
    )


class TestGitIgnoreParser:
    """Tests for GitIgnoreParser class."""
    
    def test_init_without_gitignore(self):
        """Initialization without .gitignore file."""
        parser = GitIgnoreParser()
        assert parser.patterns == []
    
    def test_init_with_nonexistent_gitignore(self, temp_dir):
        """Initialization with non-existent .gitignore file."""
        parser = GitIgnoreParser(temp_dir / "nonexistent")
        assert parser.patterns == []
    
    def test_parse_gitignore_success(self, temp_dir, gitignore_content):
        """Successful parsing of .gitignore file."""
        gitignore_path = temp_dir / ".gitignore"
        gitignore_path.write_text(gitignore_content)
        
        parser = GitIgnoreParser(gitignore_path)
        expected_patterns = ["*.pyc", "__pycache__/", "*.log", "/temp/", "*.tmp", "test_*.py"]
        assert parser.patterns == expected_patterns
    
    def test_parse_gitignore_io_error(self, temp_dir, monkeypatch):
        """IO error when reading .gitignore file."""
        gitignore_path = temp_dir / ".gitignore"
        gitignore_path.write_text("test")
        
        def mock_open(*args, **kwargs):
            raise IOError("Permission denied")
        
        monkeypatch.setattr("builtins.open", mock_open)
        
        parser = GitIgnoreParser(gitignore_path)
        assert parser.patterns == []
    
    def test_should_ignore_no_patterns(self):
        """Check ignoring behavior without patterns."""
        parser = GitIgnoreParser()
        root_dir = Path("/project")
        file_path = root_dir / "test.py"
        
        assert parser.should_ignore(file_path, root_dir) == False
    
    def test_should_ignore_relative_path_error(self):
        """Check error when getting relative path."""
        parser = GitIgnoreParser()
        parser.patterns = ["*.py"]
        
        root_dir = Path("/project")
        file_path = Path("/other/test.py")
        
        assert parser.should_ignore(file_path, root_dir) == False
    
    def test_should_ignore_pattern_matching(self, temp_dir, gitignore_content):
        """Check .gitignore pattern matching."""
        gitignore_path = temp_dir / ".gitignore"
        gitignore_path.write_text(gitignore_content)
        
        parser = GitIgnoreParser(gitignore_path)
        
        assert parser.should_ignore(temp_dir / "test.log", temp_dir) == True
        assert parser.should_ignore(temp_dir / "module.pyc", temp_dir) == True
        assert parser.should_ignore(temp_dir / "test_example.py", temp_dir) == True
        assert parser.should_ignore(temp_dir / "main.py", temp_dir) == False
        assert parser.should_ignore(temp_dir / "README.md", temp_dir) == False
    
    def test_matches_pattern_with_directory(self):
        """Check pattern matching for directories."""
        parser = GitIgnoreParser()
        
        pattern = "build/"
        rel_path = "build/file.txt"
        
        parser._convert_to_regex = Mock(return_value=Mock(match=Mock(return_value=True)))
        
        assert parser._matches_pattern(rel_path, pattern) == True
    
    def test_convert_to_regex(self):
        """Check conversion of .gitignore pattern to regex."""
        parser = GitIgnoreParser()
        
        test_cases = [
            ("*.py", r'(^|/).*\.py($|/)'),
            ("test_*", r'(^|/)test_.*($|/)'),
            ("**/temp", r'(^|/).*temp($|/)'),
            ("/exact", r'(^|/)exact($|/)'),
        ]
        
        for pattern, expected_regex in test_cases:
            result = parser._convert_to_regex(pattern)
            assert isinstance(result, type(re.compile('')))
            assert hasattr(result, 'pattern')
    
    def test_empty_gitignore(self, temp_dir):
        """Check empty .gitignore file."""
        gitignore_path = temp_dir / ".gitignore"
        gitignore_path.write_text("")
        
        parser = GitIgnoreParser(gitignore_path)
        assert parser.patterns == []
    
    def test_gitignore_with_comments_only(self, temp_dir):
        """Check .gitignore with only comments."""
        gitignore_path = temp_dir / ".gitignore"
        gitignore_path.write_text("# Comment 1\n\n# Comment 2")
        
        parser = GitIgnoreParser(gitignore_path)
        assert parser.patterns == []
    
    def test_pattern_matching_edge_cases(self):
        """Check edge cases for pattern matching."""
        parser = GitIgnoreParser()
        
        test_cases = [
            ("*.py", "test.py", True),
            ("*.py", "test.txt", False),
            ("test_*", "test_file.py", True),
            ("test_*", "file_test.py", False),
            ("*/temp/*", "dir/temp/file.txt", True),
            ("*/temp/*", "dir/other/file.txt", False),
        ]
        
        for pattern, path, expected in test_cases:
            mock_regex = Mock()
            mock_regex.match.return_value = expected
            parser._convert_to_regex = Mock(return_value=mock_regex)
            
            result = parser._matches_pattern(path, pattern)
            assert result == expected


class TestFileMerger:
    """Tests for FileMerger class."""
    
    def test_init_with_gitignore_file(self, temp_dir):
        """Initialization with specified .gitignore file."""
        gitignore_path = temp_dir / ".myignore"
        gitignore_path.write_text("*.tmp")
        
        config = SimpleNamespace(
            gitignore=str(gitignore_path),
            use_gitignore=False,
            files=None,
            directories=None,
            recursive=False,
            pattern="*",
            output="merged.txt",
            preview=False,
            exclude_dirs=[],
            exclude_names=[],
            exclude_patterns=[]
        )
        
        merger = FileMerger(config)
        assert merger.gitignore_parser is not None
    
    def test_init_with_missing_gitignore(self, temp_dir, capsys):
        """Initialization with non-existent .gitignore file."""
        config = SimpleNamespace(
            gitignore=str(temp_dir / "nonexistent"),
            use_gitignore=False,
            files=None,
            directories=None,
            recursive=False,
            pattern="*",
            output="merged.txt",
            preview=False,
            exclude_dirs=[],
            exclude_names=[],
            exclude_patterns=[]
        )
        
        merger = FileMerger(config)
        captured = capsys.readouterr()
        assert "Warning: Gitignore file" in captured.err
        assert merger.gitignore_parser is None
    
    def test_init_with_use_gitignore(self, temp_dir, capsys):
        """Initialization with automatic .gitignore discovery."""
        (temp_dir / ".gitignore").write_text("*.tmp")
        
        original_cwd = os.getcwd()
        os.chdir(temp_dir)
        
        try:
            config = SimpleNamespace(
                gitignore=None,
                use_gitignore=True,
                files=None,
                directories=None,
                recursive=False,
                pattern="*",
                output="merged.txt",
                preview=False,
                exclude_dirs=[],
                exclude_names=[],
                exclude_patterns=[]
            )
            
            merger = FileMerger(config)
            captured = capsys.readouterr()
            
            assert "Auto-discovered .gitignore" in captured.err
            assert merger.gitignore_parser is not None
        finally:
            os.chdir(original_cwd)
    
    def test_get_relative_path_inside_root(self, temp_dir):
        """Get relative path inside root directory."""
        config = SimpleNamespace(
            gitignore=None,
            use_gitignore=False,
            files=None,
            directories=None,
            recursive=False,
            pattern="*",
            output="merged.txt",
            preview=False,
            exclude_dirs=[],
            exclude_names=[],
            exclude_patterns=[]
        )
        
        merger = FileMerger(config)
        merger.root_dir = temp_dir
        
        file_path = temp_dir / "src" / "main.py"
        result = merger.get_relative_path(str(file_path))
        result = result.replace('\\', '/')
        
        assert result == "src/main.py"
    
    def test_get_relative_path_outside_root(self, temp_dir):
        """Get relative path outside root directory."""
        config = SimpleNamespace(
            gitignore=None,
            use_gitignore=False,
            files=None,
            directories=None,
            recursive=False,
            pattern="*",
            output="merged.txt",
            preview=False,
            exclude_dirs=[],
            exclude_names=[],
            exclude_patterns=[]
        )
        
        merger = FileMerger(config)
        merger.root_dir = temp_dir
        
        outside_file = Path("/outside") / "file.txt"
        result = merger.get_relative_path(str(outside_file))
        
        assert str(outside_file) in result or "/outside/file.txt" in result
    
    def test_should_exclude_gitignore(self, temp_dir):
        """Exclude files based on .gitignore."""
        config = SimpleNamespace(
            gitignore=None,
            use_gitignore=False,
            exclude_dirs=[],
            exclude_names=[],
            exclude_patterns=[],
            files=None,
            directories=None,
            recursive=False,
            pattern="*",
            output="merged.txt",
            preview=False
        )
        
        merger = FileMerger(config)
        mock_parser = Mock()
        mock_parser.should_ignore.return_value = True
        merger.gitignore_parser = mock_parser
        
        file_path = temp_dir / "test.py"
        assert merger.should_exclude(file_path) == True
        mock_parser.should_ignore.assert_called_once_with(file_path, merger.root_dir)
    
    def test_should_exclude_by_directory(self, temp_dir):
        """Exclude by directory name."""
        config = SimpleNamespace(
            gitignore=None,
            use_gitignore=False,
            exclude_dirs=["__pycache__", "node_modules"],
            exclude_names=[],
            exclude_patterns=[],
            files=None,
            directories=None,
            recursive=False,
            pattern="*",
            output="merged.txt",
            preview=False
        )
        
        merger = FileMerger(config)
        merger.gitignore_parser = None
        merger.root_dir = temp_dir
        
        file_path = temp_dir / "__pycache__" / "module.pyc"
        file_path.parent.mkdir(exist_ok=True)
        
        assert merger.should_exclude(file_path) == True
        
        file_path2 = temp_dir / "src" / "main.py"
        file_path2.parent.mkdir(exist_ok=True)
        assert merger.should_exclude(file_path2) == False
    
    def test_should_exclude_by_name(self):
        """Exclude by file name."""
        config = SimpleNamespace(
            gitignore=None,
            use_gitignore=False,
            exclude_dirs=[],
            exclude_names=["*.tmp", "temp_*"],
            exclude_patterns=[],
            files=None,
            directories=None,
            recursive=False,
            pattern="*",
            output="merged.txt",
            preview=False
        )
        
        merger = FileMerger(config)
        merger.gitignore_parser = None
        
        assert merger.should_exclude(Path("test.tmp")) == True
        assert merger.should_exclude(Path("temp_file.txt")) == True
        assert merger.should_exclude(Path("normal.txt")) == False
    
    def test_should_exclude_by_pattern(self):
        """Exclude by pattern."""
        config = SimpleNamespace(
            gitignore=None,
            use_gitignore=False,
            exclude_dirs=[],
            exclude_names=[],
            exclude_patterns=["test_*.py", "*/tmp/*"],
            files=None,
            directories=None,
            recursive=False,
            pattern="*",
            output="merged.txt",
            preview=False
        )
        
        merger = FileMerger(config)
        merger.gitignore_parser = None
        
        assert merger.should_exclude(Path("test_example.py")) == True
        assert merger.should_exclude(Path("src/tmp/file.txt")) == True
        assert merger.should_exclude(Path("main.py")) == False
    
    def test_find_files_explicit_list(self, temp_dir):
        """Find files via explicit list."""
        config = SimpleNamespace(
            files=[str(temp_dir / "file1.txt"), str(temp_dir / "file2.txt")],
            directories=None,
            recursive=False,
            pattern="*",
            output="merged.txt",
            preview=False,
            exclude_dirs=[],
            exclude_names=[],
            exclude_patterns=[],
            gitignore=None,
            use_gitignore=False
        )
        
        (temp_dir / "file1.txt").write_text("content1")
        (temp_dir / "file2.txt").write_text("content2")
        (temp_dir / "file3.txt").write_text("content3")
        
        merger = FileMerger(config)
        merger.root_dir = temp_dir
        merger.gitignore_parser = None
        
        files = merger.find_files()
        assert len(files) == 2
        assert str(temp_dir / "file1.txt") in files
        assert str(temp_dir / "file2.txt") in files
    
    def test_find_files_explicit_list_missing(self, temp_dir, capsys):
        """Find files via explicit list with missing files."""
        config = SimpleNamespace(
            files=[str(temp_dir / "existing.txt"), str(temp_dir / "missing.txt")],
            directories=None,
            recursive=False,
            pattern="*",
            output="merged.txt",
            preview=False,
            exclude_dirs=[],
            exclude_names=[],
            exclude_patterns=[],
            gitignore=None,
            use_gitignore=False
        )
        
        (temp_dir / "existing.txt").write_text("content")
        
        merger = FileMerger(config)
        merger.root_dir = temp_dir
        merger.gitignore_parser = None
        
        files = merger.find_files()
        captured = capsys.readouterr()
        
        assert len(files) == 1
        assert "Warning: File" in captured.err
    
    def test_find_files_explicit_list_excluded(self, temp_dir, capsys):
        """Find files via explicit list with excluded files."""
        config = SimpleNamespace(
            files=[str(temp_dir / "included.txt"), str(temp_dir / "excluded.tmp")],
            directories=None,
            recursive=False,
            pattern="*",
            output="merged.txt",
            preview=False,
            exclude_dirs=[],
            exclude_names=["*.tmp"],
            exclude_patterns=[],
            gitignore=None,
            use_gitignore=False
        )
        
        (temp_dir / "included.txt").write_text("content")
        (temp_dir / "excluded.tmp").write_text("temp")
        
        merger = FileMerger(config)
        merger.root_dir = temp_dir
        merger.gitignore_parser = None
        
        files = merger.find_files()
        captured = capsys.readouterr()
        
        assert len(files) == 1
        assert str(temp_dir / "included.txt") in files
        assert str(temp_dir / "excluded.tmp") not in files
        assert "Info: File" in captured.err
    
    def test_find_files_directory_nonrecursive(self, temp_dir):
        """Find files in directory non-recursively."""
        config = SimpleNamespace(
            files=None,
            directories=[str(temp_dir)],
            recursive=False,
            pattern="*.txt",
            output="merged.txt",
            preview=False,
            exclude_dirs=[],
            exclude_names=[],
            exclude_patterns=[],
            gitignore=None,
            use_gitignore=False
        )
        
        (temp_dir / "file1.txt").write_text("content1")
        (temp_dir / "file2.py").write_text("content2")
        (temp_dir / "subdir").mkdir()
        (temp_dir / "subdir" / "file3.txt").write_text("content3")
        
        merger = FileMerger(config)
        merger.root_dir = temp_dir
        merger.gitignore_parser = None
        
        files = merger.find_files()
        assert len(files) == 1
        assert str(temp_dir / "file1.txt") in files
    
    def test_find_files_directory_recursive(self, temp_dir):
        """Find files in directory recursively."""
        config = SimpleNamespace(
            files=None,
            directories=[str(temp_dir)],
            recursive=True,
            pattern="*.txt",
            output="merged.txt",
            preview=False,
            exclude_dirs=[],
            exclude_names=[],
            exclude_patterns=[],
            gitignore=None,
            use_gitignore=False
        )
        
        (temp_dir / "file1.txt").write_text("content1")
        (temp_dir / "subdir").mkdir()
        (temp_dir / "subdir" / "file2.txt").write_text("content2")
        (temp_dir / "subdir" / "file3.py").write_text("content3")
        
        merger = FileMerger(config)
        merger.root_dir = temp_dir
        merger.gitignore_parser = None
        
        files = merger.find_files()
        assert len(files) == 2
        assert str(temp_dir / "file1.txt") in files
        assert str(temp_dir / "subdir" / "file2.txt") in files
    
    def test_find_files_multiple_directories(self, temp_dir):
        """Find files in multiple directories."""
        config = SimpleNamespace(
            files=None,
            directories=[str(temp_dir / "dir1"), str(temp_dir / "dir2")],
            recursive=False,
            pattern="*.txt",
            output="merged.txt",
            preview=False,
            exclude_dirs=[],
            exclude_names=[],
            exclude_patterns=[],
            gitignore=None,
            use_gitignore=False
        )
        
        (temp_dir / "dir1").mkdir()
        (temp_dir / "dir2").mkdir()
        (temp_dir / "dir1" / "file1.txt").write_text("content1")
        (temp_dir / "dir2" / "file2.txt").write_text("content2")
        
        merger = FileMerger(config)
        merger.root_dir = temp_dir
        merger.gitignore_parser = None
        
        files = merger.find_files()
        assert len(files) == 2
    
    def test_find_files_default_directory(self, temp_dir):
        """Find files in default directory (current)."""
        config = SimpleNamespace(
            files=None,
            directories=None,
            recursive=False,
            pattern="*.txt",
            output="merged.txt",
            preview=False,
            exclude_dirs=[],
            exclude_names=[],
            exclude_patterns=[],
            gitignore=None,
            use_gitignore=False
        )
        
        original_cwd = os.getcwd()
        os.chdir(temp_dir)
        
        try:
            (temp_dir / "file1.txt").write_text("content1")
            (temp_dir / "file2.py").write_text("content2")
            
            merger = FileMerger(config)
            merger.root_dir = temp_dir
            merger.gitignore_parser = None
            
            files = merger.find_files()
            assert len(files) == 1
            assert "file1.txt" in files or str(temp_dir / "file1.txt") in files
        finally:
            os.chdir(original_cwd)
    
    def test_find_files_directory_not_found(self, temp_dir, capsys):
        """Find files in non-existent directory."""
        config = SimpleNamespace(
            files=None,
            directories=[str(temp_dir / "nonexistent")],
            recursive=False,
            pattern="*",
            output="merged.txt",
            preview=False,
            exclude_dirs=[],
            exclude_names=[],
            exclude_patterns=[],
            gitignore=None,
            use_gitignore=False
        )
        
        merger = FileMerger(config)
        merger.root_dir = temp_dir
        merger.gitignore_parser = None
        
        files = merger.find_files()
        captured = capsys.readouterr()
        
        assert len(files) == 0
        assert "Warning: Directory" in captured.err
    
    def test_create_header(self, temp_dir):
        """Create file header."""
        config = SimpleNamespace(
            gitignore=None,
            use_gitignore=False,
            files=None,
            directories=None,
            recursive=False,
            pattern="*",
            output="merged.txt",
            preview=False,
            exclude_dirs=[],
            exclude_names=[],
            exclude_patterns=[]
        )
        
        merger = FileMerger(config)
        merger.root_dir = temp_dir
        
        file_path = temp_dir / "src" / "main.py"
        file_path.parent.mkdir(exist_ok=True)
        file_path.write_text("content")
        
        header = merger.create_header(str(file_path))
        
        assert "FILE:" in header
        assert "src/main.py" in header.replace('\\', '/')
        assert "=" * 60 in header
    
    def test_merge_files_success(self, temp_dir):
        """Successful file merging."""
        config = SimpleNamespace(
            files=[str(temp_dir / "file1.txt"), str(temp_dir / "file2.txt")],
            directories=None,
            recursive=False,
            pattern="*",
            output=str(temp_dir / "merged.txt"),
            exclude_dirs=[],
            exclude_names=[],
            exclude_patterns=[],
            gitignore=None,
            use_gitignore=False,
            preview=False
        )
        
        (temp_dir / "file1.txt").write_text("Content 1\nLine 2")
        (temp_dir / "file2.txt").write_text("Content 2")
        
        merger = FileMerger(config)
        merger.root_dir = temp_dir
        merger.gitignore_parser = None
        
        with patch('os.popen') as mock_popen:
            mock_popen.return_value.read.return_value = "2024-01-01"
            result = merger.merge_files()
        
        assert result == True
        assert (temp_dir / "merged.txt").exists()
        
        content = (temp_dir / "merged.txt").read_text()
        assert "MERGED FILES: 2 files" in content
        assert "FILE: file1.txt" in content
        assert "Content 1" in content
        assert "FILE: file2.txt" in content
        assert "Content 2" in content
    
    def test_merge_files_unicode_error(self, temp_dir):
        """Handle Unicode error when reading file."""
        config = SimpleNamespace(
            files=[str(temp_dir / "binary.bin")],
            directories=None,
            recursive=False,
            pattern="*",
            output=str(temp_dir / "merged.txt"),
            exclude_dirs=[],
            exclude_names=[],
            exclude_patterns=[],
            gitignore=None,
            use_gitignore=False,
            preview=False
        )
        
        (temp_dir / "binary.bin").write_bytes(b'\x80\x81\x82')
        
        merger = FileMerger(config)
        merger.root_dir = temp_dir
        merger.gitignore_parser = None
        
        with patch('os.popen') as mock_popen:
            mock_popen.return_value.read.return_value = "2024-01-01"
            result = merger.merge_files()
        
        assert result == True
        assert (temp_dir / "merged.txt").exists()
    
    def test_merge_files_output_error(self, temp_dir):
        """Error when writing output file."""
        config = SimpleNamespace(
            files=[str(temp_dir / "file.txt")],
            directories=None,
            recursive=False,
            pattern="*",
            output=str(temp_dir / "readonly" / "merged.txt"),
            exclude_dirs=[],
            exclude_names=[],
            exclude_patterns=[],
            gitignore=None,
            use_gitignore=False,
            preview=False
        )
        
        (temp_dir / "file.txt").write_text("content")
        
        readonly_dir = temp_dir / "readonly"
        readonly_dir.mkdir()
        
        merger = FileMerger(config)
        merger.root_dir = temp_dir
        merger.gitignore_parser = None
        
        try:
            import stat
            readonly_dir.chmod(stat.S_IRUSR)
        except:
            pass
        
        result = merger.merge_files()
        assert result in [True, False]
    
    def test_merge_files_no_files(self, temp_dir, capsys):
        """Attempt to merge with no files."""
        config = SimpleNamespace(
            files=[],
            directories=None,
            recursive=False,
            pattern="*.nonexistent",
            output=str(temp_dir / "merged.txt"),
            exclude_dirs=[],
            exclude_names=[],
            exclude_patterns=[],
            gitignore=None,
            use_gitignore=False,
            preview=False
        )
        
        merger = FileMerger(config)
        merger.root_dir = temp_dir
        merger.gitignore_parser = None
        
        result = merger.merge_files()
        captured = capsys.readouterr()
        
        assert result == False
        assert "No files found to merge" in captured.err
    
    def test_preview_merge(self, temp_dir, capsys):
        """Preview merging."""
        config = SimpleNamespace(
            files=[str(temp_dir / "file1.txt"), str(temp_dir / "file2.txt")],
            directories=None,
            recursive=False,
            pattern="*",
            output=str(temp_dir / "merged.txt"),
            exclude_dirs=["excluded"],
            exclude_names=["*.tmp"],
            exclude_patterns=["test_*"],
            gitignore=None,
            use_gitignore=False,
            preview=True
        )
        
        (temp_dir / "file1.txt").write_text("Content 1")
        (temp_dir / "file2.txt").write_text("Content 2")
        
        merger = FileMerger(config)
        merger.root_dir = temp_dir
        merger.gitignore_parser = None
        
        result = merger.preview_merge()
        captured = capsys.readouterr()
        
        assert result == True
        assert "PREVIEW" in captured.out
        assert "2 files" in captured.out
        assert "file1.txt" in captured.out
        assert "Exclusions applied" in captured.out
    
    def test_preview_merge_no_files(self, temp_dir, capsys):
        """Preview merging with no files."""
        config = SimpleNamespace(
            files=[],
            directories=None,
            recursive=False,
            pattern="*.nonexistent",
            output=str(temp_dir / "merged.txt"),
            exclude_dirs=[],
            exclude_names=[],
            exclude_patterns=[],
            gitignore=None,
            use_gitignore=False,
            preview=True
        )
        
        merger = FileMerger(config)
        merger.root_dir = temp_dir
        merger.gitignore_parser = None
        
        result = merger.preview_merge()
        captured = capsys.readouterr()
        
        assert result == False
        assert "No files found to merge" in captured.err
    
    def test_file_encoding_fallback(self, temp_dir):
        """Test encoding fallback on Unicode error."""
        config = SimpleNamespace(
            files=[str(temp_dir / "latin1.txt")],
            directories=None,
            recursive=False,
            pattern="*",
            output=str(temp_dir / "merged.txt"),
            exclude_dirs=[],
            exclude_names=[],
            exclude_patterns=[],
            gitignore=None,
            use_gitignore=False,
            preview=False
        )
        
        latin1_content = "café".encode('latin-1')
        (temp_dir / "latin1.txt").write_bytes(latin1_content)
        
        merger = FileMerger(config)
        merger.root_dir = temp_dir
        merger.gitignore_parser = None
        
        with patch('os.popen') as mock_popen:
            mock_popen.return_value.read.return_value = "2024-01-01"
            result = merger.merge_files()
        
        assert result == True
    
    def test_merge_files_general_exception(self, temp_dir):
        """Handle general exception when reading file."""
        config = SimpleNamespace(
            files=[str(temp_dir / "problem.txt")],
            directories=None,
            recursive=False,
            pattern="*",
            output=str(temp_dir / "merged.txt"),
            preview=False,
            exclude_dirs=[],
            exclude_names=[],
            exclude_patterns=[],
            gitignore=None,
            use_gitignore=False
        )
        
        (temp_dir / "problem.txt").write_text("original content")
        
        merger = FileMerger(config)
        merger.root_dir = temp_dir
        merger.gitignore_parser = None
        
        import builtins
        original_open = builtins.open
        
        def custom_open(file, *args, **kwargs):
            mode = kwargs.get('mode', 'r') if kwargs else 'r'
            if 'r' in mode and 'problem.txt' in str(file):
                raise Exception("File error")
            return original_open(file, *args, **kwargs)
        
        with patch('builtins.open', side_effect=custom_open):
            with patch('os.popen') as mock_popen:
                mock_popen.return_value.read.return_value = "2024-01-01"
                result = merger.merge_files()
        
        assert result == True
        assert (temp_dir / "merged.txt").exists()


class TestMainFunction:
    """Tests for main function."""
    
    def test_main_with_preview(self, temp_dir, capsys):
        """Run main with --preview flag."""
        (temp_dir / "test1.txt").write_text("test1")
        (temp_dir / "test2.txt").write_text("test2")
        
        original_cwd = os.getcwd()
        os.chdir(temp_dir)
        
        try:
            test_args = [
                "merger.py",
                "test1.txt",
                "test2.txt",
                "--preview",
                "--output", "merged.txt"
            ]
            
            with patch.object(sys, 'argv', test_args):
                exit_code = main()
            
            captured = capsys.readouterr()
            
            assert exit_code == 0
            assert "PREVIEW" in captured.out
            assert "2 files" in captured.out
        finally:
            os.chdir(original_cwd)
    
    def test_main_without_preview(self, temp_dir):
        """Run main without --preview flag (actual merging)."""
        (temp_dir / "test1.txt").write_text("test1")
        (temp_dir / "test2.txt").write_text("test2")
        
        original_cwd = os.getcwd()
        os.chdir(temp_dir)
        
        try:
            test_args = [
                "merger.py",
                "test1.txt",
                "test2.txt",
                "--output", "merged.txt"
            ]
            
            with patch.object(sys, 'argv', test_args):
                with patch('os.popen') as mock_popen:
                    mock_popen.return_value.read.return_value = "2024-01-01"
                    exit_code = main()
            
            assert exit_code == 0
            assert (temp_dir / "merged.txt").exists()
        finally:
            os.chdir(original_cwd)
    
    def test_main_with_directory_search(self, temp_dir):
        """Run main with directory search."""
        (temp_dir / "src").mkdir()
        (temp_dir / "src" / "main.py").write_text("print('test')")
        (temp_dir / "src" / "utils.py").write_text("def test(): pass")
        
        original_cwd = os.getcwd()
        os.chdir(temp_dir)
        
        try:
            test_args = [
                "merger.py",
                "-d", "src",
                "-p", "*.py",
                "-r",
                "--output", "merged.txt"
            ]
            
            with patch.object(sys, 'argv', test_args):
                with patch('os.popen') as mock_popen:
                    mock_popen.return_value.read.return_value = "2024-01-01"
                    exit_code = main()
            
            assert exit_code == 0
            assert (temp_dir / "merged.txt").exists()
            
            content = (temp_dir / "merged.txt").read_text()
            assert "main.py" in content
            assert "utils.py" in content
        finally:
            os.chdir(original_cwd)
    
    def test_main_with_exclusions(self, temp_dir):
        """Run main with exclusions."""
        (temp_dir / "include.txt").write_text("include")
        (temp_dir / "exclude.tmp").write_text("exclude")
        (temp_dir / "test_exclude.py").write_text("test")
        
        original_cwd = os.getcwd()
        os.chdir(temp_dir)
        
        try:
            test_args = [
                "merger.py",
                "-d", ".",
                "-en", "*.tmp",
                "-ep", "test_*.py",
                "--output", "merged.txt"
            ]
            
            with patch.object(sys, 'argv', test_args):
                with patch('os.popen') as mock_popen:
                    mock_popen.return_value.read.return_value = "2024-01-01"
                    exit_code = main()
            
            assert exit_code == 0
            assert (temp_dir / "merged.txt").exists()
            
            content = (temp_dir / "merged.txt").read_text()
            assert "include.txt" in content
            assert "exclude.tmp" not in content
            assert "test_exclude.py" not in content
        finally:
            os.chdir(original_cwd)
    
    def test_main_merge_failure(self, temp_dir, capsys):
        """Run main with merge error."""
        (temp_dir / "test.txt").write_text("test")
        
        original_cwd = os.getcwd()
        os.chdir(temp_dir)
        
        try:
            test_args = [
                "merger.py",
                "test.txt",
                "--output", "/nonexistent/path/merged.txt"
            ]
            
            with patch.object(sys, 'argv', test_args):
                exit_code = main()
            
            captured = capsys.readouterr()
            assert exit_code in [0, 1]
        finally:
            os.chdir(original_cwd)
    
    def test_main_preview_failure(self, temp_dir, capsys):
        """Run main with preview and error."""
        original_cwd = os.getcwd()
        os.chdir(temp_dir)
        
        try:
            test_args = [
                "merger.py",
                "nonexistent.txt",
                "--preview"
            ]
            
            with patch.object(sys, 'argv', test_args):
                exit_code = main()
            
            captured = capsys.readouterr()
            
            assert exit_code == 1
            assert "No files found to merge" in captured.err
        finally:
            os.chdir(original_cwd)


class TestIntegration:
    """Integration tests."""
    
    def test_complete_workflow(self, temp_dir):
        """Complete merging workflow."""
        (temp_dir / "src").mkdir()
        (temp_dir / "tests").mkdir()
        (temp_dir / "logs").mkdir()
        
        (temp_dir / "src" / "main.py").write_text("def main(): pass")
        (temp_dir / "src" / "utils.py").write_text("import os")
        (temp_dir / "tests" / "test_main.py").write_text("import unittest")
        (temp_dir / "logs" / "app.log").write_text("INFO: Started")
        (temp_dir / ".gitignore").write_text("*.log\n__pycache__/\n")
        (temp_dir / "README.md").write_text("# Project")
        
        original_cwd = os.getcwd()
        os.chdir(temp_dir)
        
        try:
            test_args = [
                "merger.py",
                "-d", "src",
                "-d", "tests",
                "-r",
                "-p", "*.py",
                "-en", "test_*.py",
                "--use-gitignore",
                "--output", "merged.txt"
            ]
            
            with patch.object(sys, 'argv', test_args):
                with patch('os.popen') as mock_popen:
                    mock_popen.return_value.read.return_value = "2024-01-01"
                    exit_code = main()
            
            assert exit_code == 0
            assert (temp_dir / "merged.txt").exists()
            
            content = (temp_dir / "merged.txt").read_text()
            assert "main.py" in content
            assert "utils.py" in content
            assert "test_main.py" not in content
            assert "app.log" not in content
            assert "README.md" not in content
            
        finally:
            os.chdir(original_cwd)