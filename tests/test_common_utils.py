"""
Unit tests for common_utils module.
Tests internal structures in isolation.
"""

import sys
import os
import pytest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    from codingutils.common_utils import (
        FilterConfig,
        GitIgnoreParser,
        FileSystemWalker,
        FileContentDetector,
        FileType,
        SafeFileProcessor,
        safe_write,
        ProgressReporter,
        format_size,
        get_relative_path,
        create_directory_header,
        FileOperationError,
        PermissionDeniedError,
        InvalidFileTypeError,
        handle_file_errors
    )
except ImportError as e:
    print(f"Import error: {e}")
    raise


# ============================================================================
# FilterConfig Tests
# ============================================================================

class TestFilterConfig:
    """Test FilterConfig dataclass."""

    def test_default_values(self):
        """Test default values."""
        config = FilterConfig()

        assert config.exclude_dirs == set()
        assert config.exclude_names == set()
        assert config.exclude_patterns == set()
        assert config.include_pattern == "*"
        assert config.max_depth is None
        assert config.follow_symlinks is False
        assert config.use_gitignore is False
        assert config.custom_gitignore is None
        assert config.recursive is True

    def test_custom_values(self):
        """Test custom values."""
        config = FilterConfig(
            exclude_dirs={"node_modules", "venv"},
            exclude_names={"*.pyc", "*.log"},
            exclude_patterns={"test_*"},
            include_pattern="*.py",
            max_depth=3,
            follow_symlinks=True,
            use_gitignore=True,
            custom_gitignore=Path("/path/.gitignore"),
            recursive=False
        )

        assert config.exclude_dirs == {"node_modules", "venv"}
        assert config.exclude_names == {"*.pyc", "*.log"}
        assert config.exclude_patterns == {"test_*"}
        assert config.include_pattern == "*.py"
        assert config.max_depth == 3
        assert config.follow_symlinks is True
        assert config.use_gitignore is True
        assert config.custom_gitignore == Path("/path/.gitignore")
        assert config.recursive is False

    def test_invalid_max_depth(self):
        """Test invalid max_depth validation."""
        with pytest.raises(ValueError, match="max_depth must be non-negative"):
            FilterConfig(max_depth=-1)


# ============================================================================
# GitIgnoreParser Tests
# ============================================================================

class TestGitIgnoreParser:
    """Test GitIgnoreParser in isolation."""

    def test_init_without_root_dir(self):
        """Test initialization without root directory."""
        parser = GitIgnoreParser()
        assert parser.root_dir == Path.cwd().resolve()
        assert parser.patterns == []
        assert parser._cache == {}

    def test_init_with_root_dir(self, tmp_path):
        """Test initialization with custom root directory."""
        parser = GitIgnoreParser(tmp_path)
        assert parser.root_dir == tmp_path.resolve()

    def test_load_from_file_success(self, tmp_path):
        """Test loading patterns from gitignore file."""
        gitignore_path = tmp_path / ".gitignore"
        gitignore_path.write_text("# Comment\nnode_modules/\n*.pyc\n!important.pyc\n")

        parser = GitIgnoreParser(tmp_path)
        result = parser.load_from_file(gitignore_path)

        assert result is True
        assert len(parser.patterns) == 3

    def test_load_from_file_not_found(self, tmp_path):
        """Test loading non-existent gitignore file."""
        parser = GitIgnoreParser(tmp_path)
        result = parser.load_from_file(tmp_path / ".nonexistent")

        assert result is False
        assert len(parser.patterns) == 0

    def test_load_from_file_permission_error(self, tmp_path, monkeypatch):
        """Test loading gitignore with permission error."""
        gitignore_path = tmp_path / ".gitignore"
        gitignore_path.write_text("test")

        def mock_open(*args, **kwargs):
            raise PermissionError("Permission denied")

        monkeypatch.setattr("builtins.open", mock_open)

        parser = GitIgnoreParser(tmp_path)
        result = parser.load_from_file(gitignore_path)

        assert result is False

    def test_load_auto_discovery(self, tmp_path):
        """Test auto-discovery of gitignore files."""
        (tmp_path / ".gitignore").write_text("*.pyc\n")

        # Create nested structure
        subdir = tmp_path / "project"
        subdir.mkdir()
        (subdir / ".gitignore").write_text("node_modules/\n")

        parser = GitIgnoreParser(subdir)
        result = parser.load_from_file()  # Auto-discover

        assert result is True
        assert len(parser.patterns) > 0

    @pytest.mark.parametrize("pattern,path_str,expected", [
        ("*.pyc", "test.pyc", True),
        ("*.pyc", "test.py", False),
        ("*.pyc", "dir/test.pyc", True),
        ("test.py", "test.py", True),
        ("test.py", "other.py", False),
        ("dir/*.py", "dir/test.py", True),
        ("dir/*.py", "other/test.py", False),
        ("**/*.py", "any/deep/test.py", True),
        ("*.py", "any/deep/test.py", True),  # Matches at any depth
    ])
    def test_pattern_matching(self, pattern, path_str, expected, tmp_path):
        """Test pattern matching."""
        parser = GitIgnoreParser(tmp_path)
        parser.add_pattern(pattern)

        test_path = tmp_path / path_str
        test_path.parent.mkdir(parents=True, exist_ok=True)
        test_path.touch()

        result = parser.should_ignore(test_path)
        assert result == expected

    def test_directory_patterns(self, tmp_path):
        """Test directory-only patterns."""
        parser = GitIgnoreParser(tmp_path)
        parser.add_pattern("node_modules/")

        # Directory should be ignored
        node_dir = tmp_path / "node_modules"
        node_dir.mkdir()
        assert parser.should_ignore(node_dir) is True

        # Files inside directory should be ignored
        node_file = node_dir / "index.js"
        node_file.touch()
        assert parser.should_ignore(node_file) is True

        # Удаляем директорию и создаем файл с тем же именем
        import shutil
        shutil.rmtree(node_dir)

        # Regular file with same name shouldn't be ignored
        node_file2 = tmp_path / "node_modules"
        node_file2.touch()

        # Очищаем кэш, так как тип узла изменился (директория → файл)
        parser._cache.clear()
        assert parser.should_ignore(node_file2) is False

    def test_negation_patterns(self, tmp_path):
        """Test negation patterns."""
        parser = GitIgnoreParser(tmp_path)
        parser.add_pattern("*.pyc")
        parser.add_pattern("!important.pyc")

        normal_pyc = tmp_path / "normal.pyc"
        normal_pyc.touch()
        assert parser.should_ignore(normal_pyc) is True

        important_pyc = tmp_path / "important.pyc"
        important_pyc.touch()
        assert parser.should_ignore(important_pyc) is False

    def test_cache_behavior(self, tmp_path):
        """Test caching of ignore decisions."""
        parser = GitIgnoreParser(tmp_path)
        parser.add_pattern("*.pyc")

        test_file = tmp_path / "test.pyc"
        test_file.touch()

        # First call should cache
        result1 = parser.should_ignore(test_file)
        # Кэшируется полный путь
        cache_key = str(test_file)
        assert cache_key in parser._cache

        # Second call should use cache
        with patch.object(parser, 'add_pattern') as mock_add:
            result2 = parser.should_ignore(test_file)
            mock_add.assert_not_called()

        assert result1 == result2 is True

    def test_path_not_under_root(self, tmp_path):
        """Test path not under root directory."""
        parser = GitIgnoreParser(tmp_path)
        parser.add_pattern("*.pyc")

        outside_file = Path("/outside/test.pyc")
        result = parser.should_ignore(outside_file)

        assert result is False
        # Путь не под корневой директорией, но он все равно кэшируется
        # Это ожидаемое поведение
        assert str(outside_file) in parser._cache


# ============================================================================
# FileSystemWalker Tests
# ============================================================================

class TestFileSystemWalker:
    """Test FileSystemWalker in isolation."""

    @pytest.fixture
    def sample_directory(self, tmp_path):
        """Create sample directory structure."""
        # Create directories
        (tmp_path / "src").mkdir()
        (tmp_path / "tests").mkdir()
        (tmp_path / "docs").mkdir()
        (tmp_path / "venv").mkdir()

        # Create files
        (tmp_path / "src" / "main.py").touch()
        (tmp_path / "src" / "utils.py").touch()
        (tmp_path / "tests" / "test_main.py").touch()
        (tmp_path / "docs" / "readme.md").touch()
        (tmp_path / "requirements.txt").touch()
        (tmp_path / ".gitignore").touch()

        # Create hidden file
        (tmp_path / ".hidden").touch()

        return tmp_path

    def test_init(self):
        """Test initialization."""
        config = FilterConfig()
        walker = FileSystemWalker(config)

        assert walker.config == config
        assert walker.gitignore_parser is None
        assert walker.stats == {
            'files_found': 0,
            'directories_found': 0,
            'files_excluded': 0,
            'directories_excluded': 0
        }

    def test_find_files_non_recursive(self, sample_directory):
        """Test non-recursive file finding."""
        config = FilterConfig(include_pattern="*.py", recursive=False)
        walker = FileSystemWalker(config)

        files = walker.find_files([sample_directory])

        # Should only find top-level .py files (none at top level)
        # Но на верхнем уровне есть другие файлы: requirements.txt, .gitignore, .hidden
        # Они будут проверены и исключены из-за паттерна "*.py"
        assert len(files) == 0
        # Проверяем, что нашло 3 файла (но они не .py)
        assert walker.stats['files_found'] == 3
        assert walker.stats['files_excluded'] == 3

    def test_find_files_recursive(self, sample_directory):
        """Test recursive file finding."""
        config = FilterConfig(include_pattern="*.py", recursive=True)
        walker = FileSystemWalker(config)

        files = walker.find_files([sample_directory])

        # Should find all .py files
        assert len(files) == 3  # main.py, utils.py, test_main.py
        # Проверим какие именно файлы
        file_names = [f.name for f in files]
        assert "main.py" in file_names
        assert "utils.py" in file_names
        assert "test_main.py" in file_names

    def test_find_files_with_exclusions(self, sample_directory):
        """Test file finding with exclusions."""
        config = FilterConfig(
            include_pattern="*",
            recursive=True,
            exclude_dirs={"venv"},
            exclude_names={"*.pyc", "*.log"},
            exclude_patterns={"test_*"}
        )
        walker = FileSystemWalker(config)

        files = walker.find_files([sample_directory])

        # Should exclude venv directory and test files
        file_names = [f.name for f in files]
        assert "venv" not in str(file_names)
        assert "test_main.py" not in file_names

    def test_find_files_max_depth(self, sample_directory):
        """Test file finding with max depth."""
        # Create nested structure
        (sample_directory / "src" / "deep" / "nested.py").parent.mkdir(parents=True)
        (sample_directory / "src" / "deep" / "nested.py").touch()

        config = FilterConfig(include_pattern="*.py", recursive=True, max_depth=2)
        walker = FileSystemWalker(config)

        files = walker.find_files([sample_directory])

        # Should find files up to depth 2
        # main.py - глубина 2 (sample_directory/src/main.py)
        # utils.py - глубина 2 (sample_directory/src/utils.py)
        # test_main.py - глубина 1 (sample_directory/tests/test_main.py)
        # nested.py - глубина 3 - не должен быть найден
        assert len(files) == 3
        file_paths = [str(f.relative_to(sample_directory)) for f in files]
        assert "src/main.py" in file_paths
        assert "src/utils.py" in file_paths
        assert "tests/test_main.py" in file_paths
        assert "src/deep/nested.py" not in file_paths

        # Проверяем статистику
        # Всего файлов: 8 (включая созданный nested.py)
        # Не .py файлы: readme.md, requirements.txt, .gitignore, .hidden = 4 файла
        # .py файлы: main.py, utils.py, test_main.py, nested.py = 4 файла
        # Исключено: 4 не .py файла + 1 nested.py (глубина) = 5 файлов
        # Включено: 3 .py файла (main.py, utils.py, test_main.py)
        assert walker.stats['files_found'] == 8
        assert walker.stats['files_excluded'] == 5

    def test_find_files_multiple_roots(self, tmp_path):
        """Test finding files from multiple root directories."""
        dir1 = tmp_path / "dir1"
        dir2 = tmp_path / "dir2"
        dir1.mkdir()
        dir2.mkdir()

        (dir1 / "file1.py").touch()
        (dir2 / "file2.py").touch()

        config = FilterConfig(include_pattern="*.py", recursive=True)
        walker = FileSystemWalker(config)

        files = walker.find_files([dir1, dir2])

        assert len(files) == 2

    def test_find_files_nonexistent_directory(self):
        """Test finding files in non-existent directory."""
        config = FilterConfig(include_pattern="*.py", recursive=True)
        walker = FileSystemWalker(config)

        files = walker.find_files([Path("/nonexistent")])

        assert len(files) == 0

    def test_permission_error_handling(self, tmp_path, monkeypatch):
        """Test handling of permission errors."""
        config = FilterConfig(include_pattern="*", recursive=True)
        walker = FileSystemWalker(config)

        # Mock iterdir to raise PermissionError
        def mock_iterdir(self):
            raise PermissionError("Permission denied")

        monkeypatch.setattr(Path, "iterdir", mock_iterdir)

        # Should not crash
        files = walker.find_files([tmp_path])
        assert len(files) == 0


# ============================================================================
# FileContentDetector Tests
# ============================================================================

class TestFileContentDetector:
    """Test FileContentDetector in isolation."""

    def test_detect_file_type_text(self, tmp_path):
        """Test text file detection."""
        text_file = tmp_path / "test.txt"
        text_file.write_text("Hello World\n")

        result = FileContentDetector.detect_file_type(text_file)
        assert result == FileType.TEXT

    def test_detect_file_type_binary_by_extension(self, tmp_path):
        """Test binary file detection by extension."""
        binary_file = tmp_path / "test.exe"
        binary_file.write_bytes(b"\x00\x01\x02\x03")

        result = FileContentDetector.detect_file_type(binary_file)
        assert result == FileType.BINARY

    def test_detect_file_type_binary_by_content(self, tmp_path):
        """Test binary file detection by null bytes."""
        binary_file = tmp_path / "test.bin"
        binary_file.write_bytes(b"Hello\x00World")

        result = FileContentDetector.detect_file_type(binary_file)
        assert result == FileType.BINARY

    def test_detect_file_type_unknown(self, tmp_path):
        """Test unknown file type detection."""
        unknown_file = tmp_path / "test.unknown"
        unknown_file.write_bytes(b"\xff\xfe")  # Invalid UTF-8

        result = FileContentDetector.detect_file_type(unknown_file)
        assert result == FileType.UNKNOWN

    @pytest.mark.parametrize("extension,expected_style", [
        (".py", {"line": "#", "block": ('"""', '"""'), "alt_block": ("'''", "'''")}),
        (".js", {"line": "//", "block": ("/*", "*/")}),
        (".css", {"block": ("/*", "*/")}),
        (".html", {"block": ("<!--", "-->")}),
        (".unknown", None),
    ])
    def test_get_comment_style(self, extension, expected_style):
        """Test comment style detection."""
        dummy_path = Path(f"dummy{extension}")
        result = FileContentDetector.get_comment_style(dummy_path)

        if expected_style is None:
            assert result is None
        else:
            for key in expected_style:
                assert result[key] == expected_style[key]

    def test_detect_encoding_utf8(self, tmp_path):
        """Test UTF-8 encoding detection."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello World", encoding="utf-8")

        result = FileContentDetector.detect_encoding(test_file)
        assert result == "utf-8"

    def test_detect_encoding_latin1(self, tmp_path):
        """Test Latin-1 encoding detection."""
        test_file = tmp_path / "test.txt"
        # Write Latin-1 content that would fail in UTF-8
        test_file.write_bytes(b"Hello\xe9World")  # é in Latin-1

        result = FileContentDetector.detect_encoding(test_file)
        assert result == "latin-1"

    def test_detect_encoding_fallback(self, tmp_path):
        """Test encoding detection fallback."""
        test_file = tmp_path / "test.txt"
        # Write some invalid bytes
        test_file.write_bytes(b"\xff\xfeHello")

        result = FileContentDetector.detect_encoding(test_file)
        assert result == "latin-1"  # Should fall back


# ============================================================================
# Utility Functions Tests
# ============================================================================

class TestUtilityFunctions:
    """Test utility functions in isolation."""

    @pytest.mark.parametrize("size_bytes,expected", [
        (0, "0 B"),
        (1023, "1023.00 B"),
        (1024, "1.00 KB"),
        (1024 * 1024, "1.00 MB"),
        (1024 * 1024 * 1024, "1.00 GB"),
        (1024 * 1024 * 1024 * 1024, "1.00 TB"),
    ])
    def test_format_size(self, size_bytes, expected):
        """Test size formatting."""
        result = format_size(size_bytes)
        assert result == expected

    def test_get_relative_path(self, tmp_path):
        """Test getting relative path."""
        base_dir = tmp_path / "project"
        base_dir.mkdir()

        test_file = base_dir / "src" / "main.py"
        test_file.parent.mkdir(parents=True)
        test_file.touch()

        # When file is under base directory
        result = get_relative_path(test_file, base_dir)
        assert result == "src/main.py"

        # When file is not under base directory
        outside_file = Path("/outside/file.txt")
        result = get_relative_path(outside_file, base_dir)
        assert result == "/outside/file.txt"

    def test_create_directory_header(self, tmp_path):
        """Test creating directory header."""
        base_dir = tmp_path / "project"
        base_dir.mkdir()

        test_file = base_dir / "src" / "main.py"
        test_file.parent.mkdir(parents=True)
        test_file.touch()

        header = create_directory_header(test_file, base_dir)

        assert "=" * 60 in header
        assert "FILE: src/main.py" in header


# ============================================================================
# Safe Operations Tests
# ============================================================================

class TestSafeFileProcessor:
    """Test SafeFileProcessor in isolation."""

    def test_context_manager_success(self, tmp_path):
        """Test successful file operation."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Original content")

        with SafeFileProcessor(test_file, backup=True) as processor:
            # Verify backup was created
            backup_file = tmp_path / "test.txt.bak"
            assert backup_file.exists()
            assert processor.backup_path == backup_file
            assert processor.original_content == "Original content"

            # Modify file
            test_file.write_text("Modified content")

        # After successful exit, backup should be removed
        assert not backup_file.exists()
        assert test_file.read_text() == "Modified content"

    def test_context_manager_error(self, tmp_path):
        """Test file operation with error."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Original content")

        with pytest.raises(ValueError, match="Test error"):
            with SafeFileProcessor(test_file, backup=True) as processor:
                backup_file = processor.backup_path
                test_file.write_text("Modified content")
                raise ValueError("Test error")

        # After error, file should be restored from backup
        assert test_file.read_text() == "Original content"
        assert not backup_file.exists()  # Backup cleaned up

    def test_context_manager_no_backup(self, tmp_path):
        """Test file operation without backup."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Original content")

        with SafeFileProcessor(test_file, backup=False) as processor:
            assert processor.backup_path is None
            test_file.write_text("Modified content")

        # No backup should exist
        assert not (tmp_path / "test.txt.bak").exists()
        assert test_file.read_text() == "Modified content"

    def test_safe_write_success(self, tmp_path):
        """Test safe_write function success."""
        test_file = tmp_path / "test.txt"

        result = safe_write(test_file, "Test content", backup=True)

        assert result is True
        assert test_file.exists()
        assert test_file.read_text() == "Test content"
        assert not (tmp_path / "test.txt.bak").exists()  # Backup cleaned up

    def test_safe_write_error(self, tmp_path, monkeypatch):
        """Test safe_write function with error."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Original content")

        # Mock open to raise error on write
        def mock_open(*args, **kwargs):
            if args[1] == 'w':
                raise PermissionError("Write error")
            return mock_open.original(*args, **kwargs)

        mock_open.original = open
        monkeypatch.setattr("builtins.open", mock_open)

        result = safe_write(test_file, "New content", backup=True)

        assert result is False
        # File should be unchanged due to backup restore
        assert test_file.read_text() == "Original content"


# ============================================================================
# ProgressReporter Tests
# ============================================================================

class TestProgressReporter:
    """Test ProgressReporter in isolation."""

    def test_basic_functionality(self, capsys):
        """Test basic progress reporting."""
        with ProgressReporter(total=100, description="Processing") as progress:
            for i in range(10):
                progress.update(10)

        captured = capsys.readouterr()
        assert "Processing" in captured.out
        assert "100.0%" in captured.out  # Ищем с точностью до 1 знака

    def test_zero_total(self, capsys):
        """Test progress reporter with zero total."""
        with ProgressReporter(total=0, description="Processing") as progress:
            progress.update(0)

        captured = capsys.readouterr()
        # Проверяем, что нет вывода прогресса, но может быть пустая строка или \n
        assert "0.0%" not in captured.out
        assert "completed" not in captured.out  # Сообщение о завершении не должно выводиться

    def test_update_with_custom_increment(self):
        """Test updating with custom increment."""
        reporter = ProgressReporter(total=100, description="Test")
        reporter.__enter__()

        assert reporter.current == 0
        reporter.update(25)
        assert reporter.current == 25
        reporter.update(25)
        assert reporter.current == 50

        reporter.__exit__(None, None, None)


# ============================================================================
# Error Handling Tests
# ============================================================================

class TestErrorHandling:
    """Test error handling utilities."""

    def test_custom_exceptions(self):
        """Test custom exception hierarchy."""
        # Test FileOperationError
        with pytest.raises(FileOperationError):
            raise FileOperationError("File operation failed")

        # Test PermissionDeniedError
        with pytest.raises(PermissionDeniedError):
            raise PermissionDeniedError("Permission denied")

        # Test InvalidFileTypeError
        with pytest.raises(InvalidFileTypeError):
            raise InvalidFileTypeError("Invalid file type")

        # Verify inheritance
        assert issubclass(PermissionDeniedError, FileOperationError)
        assert issubclass(InvalidFileTypeError, FileOperationError)

    def test_handle_file_errors_decorator_success(self):
        """Test error handler decorator on success."""
        @handle_file_errors
        def successful_operation():
            return "Success"

        result = successful_operation()
        assert result == "Success"

    def test_handle_file_errors_decorator_permission_error(self):
        """Test error handler decorator with permission error."""
        @handle_file_errors
        def operation_with_permission_error():
            raise PermissionError("Permission denied")

        with pytest.raises(PermissionDeniedError, match="Permission denied"):
            operation_with_permission_error()

    def test_handle_file_errors_decorator_file_not_found(self, caplog):
        """Test error handler decorator with file not found."""
        @handle_file_errors
        def operation_with_file_not_found():
            raise FileNotFoundError("File not found")

        result = operation_with_file_not_found()
        assert result is None
        assert "File not found" in caplog.text

    def test_handle_file_errors_decorator_unicode_error(self, caplog):
        """Test error handler decorator with Unicode decode error."""
        @handle_file_errors
        def operation_with_unicode_error():
            raise UnicodeDecodeError("utf-8", b"", 0, 1, "test")

        result = operation_with_unicode_error()
        assert result is None
        assert "Encoding error" in caplog.text

    def test_handle_file_errors_decorator_unexpected_error(self):
        """Test error handler decorator with unexpected error."""
        @handle_file_errors
        def operation_with_unexpected_error():
            raise ValueError("Unexpected error")

        with pytest.raises(ValueError, match="Unexpected error"):
            operation_with_unexpected_error()
