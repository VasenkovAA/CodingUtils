"""
Test suite for tree_generater.py
Run with: pytest test_tree_generater.py -v --cov=codingutils.tree_generater --cov-report=term-missing
"""

import pytest
import sys
import os
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, mock_open, MagicMock, call
import argparse
import logging

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from codingutils.tree_generater import GitIgnoreParser, ProjectMapper, main



@pytest.fixture
def temp_dir_structure():
    """Create a temporary directory structure for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        (tmp_path / "src").mkdir()
        (tmp_path / "tests").mkdir()
        (tmp_path / "docs").mkdir()
        (tmp_path / ".hidden").mkdir()
        
        (tmp_path / "README.md").touch()
        (tmp_path / "requirements.txt").touch()
        (tmp_path / ".gitignore").touch()
        (tmp_path / "src" / "__init__.py").touch()
        (tmp_path / "src" / "main.py").touch()
        (tmp_path / "tests" / "test_main.py").touch()
        (tmp_path / "docs" / "index.md").touch()
        (tmp_path / ".hidden" / "secret.txt").touch()
        
        (tmp_path / "src" / "utils").mkdir()
        (tmp_path / "src" / "utils" / "__init__.py").touch()
        (tmp_path / "src" / "utils" / "helpers.py").touch()
        
        large_file = tmp_path / "large.bin"
        with open(large_file, 'wb') as f:
            f.write(b'0' * 1024 * 1024)
        
        yield tmp_path


@pytest.fixture
def gitignore_content():
    """Sample .gitignore content."""
    return """# Test gitignore
*.pyc
*.log
__pycache__/
build/
dist/
*.egg-info/
*.tmp
secret.txt
test_folder/
!important.log
"""


@pytest.fixture
def config_default():
    """Default configuration for ProjectMapper."""
    class Config:
        directories = None
        pattern = '*'
        output = None
        gitignore = None
        use_gitignore = False
        no_gitignore = False
        exclude_dirs = []
        exclude_names = []
        exclude_patterns = []
        max_depth = None
    
    return Config()



class TestGitIgnoreParser:
    
    def test_init_without_path(self):
        """Test initialization without gitignore path."""
        parser = GitIgnoreParser()
        assert parser.patterns == []
    
    def test_init_with_nonexistent_path(self):
        """Test initialization with non-existent path."""
        parser = GitIgnoreParser(Path("/nonexistent/.gitignore"))
        assert parser.patterns == []
    
    def test_parse_gitignore_success(self, gitignore_content, tmp_path):
        """Test successful parsing of .gitignore file."""
        gitignore_file = tmp_path / ".gitignore"
        gitignore_file.write_text(gitignore_content)
        
        parser = GitIgnoreParser()
        parser.parse_gitignore(gitignore_file)
        
        expected_patterns = [
            "*.pyc",
            "*.log",
            "__pycache__/",
            "build/",
            "dist/",
            "*.egg-info/",
            "*.tmp",
            "secret.txt",
            "test_folder/",
            "!important.log"
        ]
        assert parser.patterns == expected_patterns
    
    def test_parse_gitignore_file_not_found(self):
        """Test parsing non-existent .gitignore file."""
        parser = GitIgnoreParser()
        non_existent = Path("/tmp/nonexistent12345/.gitignore")
        parser.parse_gitignore(non_existent)
    
    def test_parse_gitignore_permission_error(self, monkeypatch):
        """Test parsing .gitignore with permission error."""
        mock_file = mock_open()
        mock_file.side_effect = PermissionError("Permission denied")
        
        with patch('builtins.open', mock_file):
            parser = GitIgnoreParser()
            parser.parse_gitignore(Path("/some/path"))
    
    def test_should_ignore_without_patterns(self):
        """Test should_ignore when no patterns are loaded."""
        parser = GitIgnoreParser()
        path = Path("/some/path/file.txt")
        root = Path("/some")
        assert not parser.should_ignore(path, root)
    
    def test_should_ignore_relative_path_error(self):
        """Test should_ignore when path is not relative to root."""
        parser = GitIgnoreParser()
        parser.patterns = ["*.txt"]
        path = Path("/absolute/path/file.txt")
        root = Path("/different/root")
        assert not parser.should_ignore(path, root)
    
    def test_should_ignore_file_pattern(self, tmp_path):
        """Test ignoring files by pattern."""
        parser = GitIgnoreParser()
        parser.patterns = ["*.log", "*.tmp"]
        
        root = tmp_path
        log_file = root / "app.log"
        tmp_file = root / "temp.tmp"
        txt_file = root / "doc.txt"
        
        log_file.touch()
        tmp_file.touch()
        txt_file.touch()
        
        assert parser.should_ignore(log_file, root)
        assert parser.should_ignore(tmp_file, root)
        assert not parser.should_ignore(txt_file, root)
    
    def test_should_ignore_directory_pattern(self, tmp_path):
        """Test ignoring directories by pattern."""
        parser = GitIgnoreParser()
        parser.patterns = ["__pycache__/", "node_modules/"]
        
        root = tmp_path
        cache_dir = root / "__pycache__"
        node_dir = root / "node_modules"
        src_dir = root / "src"
        
        cache_dir.mkdir()
        node_dir.mkdir()
        src_dir.mkdir()
        
        assert parser.should_ignore(cache_dir, root)
        assert parser.should_ignore(node_dir, root)
        assert not parser.should_ignore(src_dir, root)
    
    def test_should_ignore_nested_pattern(self, tmp_path):
        """Test ignoring nested paths with pattern."""
        parser = GitIgnoreParser()
        parser.patterns = ["*.pyc", "test_*/"]
        
        root = tmp_path
        nested_pyc = root / "dir" / "module.pyc"
        nested_pyc.parent.mkdir()
        nested_pyc.touch()
        
        test_dir = root / "test_folder"
        test_dir.mkdir()
        
        assert parser.should_ignore(nested_pyc, root)
        assert parser.should_ignore(test_dir, root)
    
    def test_should_ignore_negation_pattern(self, tmp_path):
        """Test negation patterns (!)."""
        parser = GitIgnoreParser()
        parser.patterns = ["*.log", "!important.log"]
        
        root = tmp_path
        app_log = root / "app.log"
        important_log = root / "important.log"
        
        app_log.touch()
        important_log.touch()
        
        assert parser.should_ignore(app_log, root)
    
    def test_should_ignore_directory_wildcard(self, tmp_path):
        """Test directory matching with wildcards."""
        parser = GitIgnoreParser()
        parser.patterns = ["build*/", "dist*/"]
        
        root = tmp_path
        build_dir = root / "build"
        build_debug_dir = root / "build-debug"
        dist_dir = root / "dist"
        dist_test_dir = root / "dist-test"
        src_dir = root / "src"
        
        for d in [build_dir, build_debug_dir, dist_dir, dist_test_dir, src_dir]:
            d.mkdir()
        
        assert parser.should_ignore(build_dir, root)
        assert parser.should_ignore(build_debug_dir, root)
        assert parser.should_ignore(dist_dir, root)
        assert parser.should_ignore(dist_test_dir, root)
        assert not parser.should_ignore(src_dir, root)



class TestProjectMapper:
    
    def test_init_default(self):
        """Test initialization with default configuration."""
        config = type('Config', (), {
            'directories': None,
            'pattern': '*',
            'output': None,
            'gitignore': None,
            'use_gitignore': False,
            'no_gitignore': False,
            'exclude_dirs': [],
            'exclude_names': [],
            'exclude_patterns': [],
            'max_depth': None
        })()
        
        mapper = ProjectMapper(config)
        assert len(mapper.directories) == 1
        assert mapper.directories[0].resolve() == Path('.').resolve()
        assert mapper.gitignore_parser is None
        assert not mapper.found_gitignore
    
    def test_init_with_single_directory(self, tmp_path):
        """Test initialization with single directory."""
        config = type('Config', (), {
            'directories': [str(tmp_path)],
            'pattern': '*.py',
            'output': None,
            'gitignore': None,
            'use_gitignore': False,
            'no_gitignore': False,
            'exclude_dirs': [],
            'exclude_names': [],
            'exclude_patterns': [],
            'max_depth': 2
        })()
        
        mapper = ProjectMapper(config)
        assert len(mapper.directories) == 1
        assert mapper.directories[0].resolve() == tmp_path.resolve()
        assert mapper.config.pattern == '*.py'
        assert mapper.config.max_depth == 2
    
    def test_init_with_multiple_directories(self, tmp_path):
        """Test initialization with multiple directories."""
        dir1 = tmp_path / "dir1"
        dir2 = tmp_path / "dir2"
        dir1.mkdir()
        dir2.mkdir()
        
        config = type('Config', (), {
            'directories': [str(dir1), str(dir2)],
            'pattern': '*',
            'output': None,
            'gitignore': None,
            'use_gitignore': False,
            'no_gitignore': False,
            'exclude_dirs': [],
            'exclude_names': [],
            'exclude_patterns': [],
            'max_depth': None
        })()
        
        mapper = ProjectMapper(config)
        assert len(mapper.directories) == 2
        assert mapper.root_dir == Path.cwd()
    
    def test_init_with_gitignore_path(self, tmp_path):
        """Test initialization with explicit gitignore path."""
        gitignore = tmp_path / "custom.gitignore"
        gitignore.write_text("*.log\n")
        
        config = type('Config', (), {
            'directories': [str(tmp_path)],
            'pattern': '*',
            'output': None,
            'gitignore': str(gitignore),
            'use_gitignore': False,
            'no_gitignore': False,
            'exclude_dirs': [],
            'exclude_names': [],
            'exclude_patterns': [],
            'max_depth': None
        })()
        
        mapper = ProjectMapper(config)
        assert mapper.gitignore_parser is not None
        assert mapper.found_gitignore
        assert "*.log" in mapper.gitignore_parser.patterns
    
    def test_init_use_gitignore_auto_discover(self, tmp_path):
        """Test auto-discovery of .gitignore."""
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("*.tmp\n")
        
        config = type('Config', (), {
            'directories': [str(tmp_path)],
            'pattern': '*',
            'output': None,
            'gitignore': None,
            'use_gitignore': True,
            'no_gitignore': False,
            'exclude_dirs': [],
            'exclude_names': [],
            'exclude_patterns': [],
            'max_depth': None
        })()
        
        mapper = ProjectMapper(config)
        assert mapper.gitignore_parser is not None
        assert mapper.found_gitignore
        assert "*.tmp" in mapper.gitignore_parser.patterns
    
    def test_init_no_gitignore(self, tmp_path):
        """Test initialization with no_gitignore flag."""
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("*.log\n")
        
        config = type('Config', (), {
            'directories': [str(tmp_path)],
            'pattern': '*',
            'output': None,
            'gitignore': None,
            'use_gitignore': True,
            'no_gitignore': True,
            'exclude_dirs': [],
            'exclude_names': [],
            'exclude_patterns': [],
            'max_depth': None
        })()
        
        mapper = ProjectMapper(config)
        assert mapper.gitignore_parser is None
        assert not mapper.found_gitignore
    
    def test_setup_logging_console(self):
        """Test logging setup for console output."""
        config = type('Config', (), {
            'directories': ['.'],
            'pattern': '*',
            'output': None,
            'gitignore': None,
            'use_gitignore': False,
            'no_gitignore': False,
            'exclude_dirs': [],
            'exclude_names': [],
            'exclude_patterns': [],
            'max_depth': None
        })()
        
        mapper = ProjectMapper(config)
        mapper.setup_logging()
        
        assert mapper.logger is not None
        assert len(mapper.logger.handlers) == 1
        assert isinstance(mapper.logger.handlers[0], logging.StreamHandler)
        
        mapper.cleanup()
    
    def test_setup_logging_file(self, tmp_path):
        """Test logging setup for file output."""
        output_file = tmp_path / "output.txt"
        
        config = type('Config', (), {
            'directories': ['.'],
            'pattern': '*',
            'output': str(output_file),
            'gitignore': None,
            'use_gitignore': False,
            'no_gitignore': False,
            'exclude_dirs': [],
            'exclude_names': [],
            'exclude_patterns': [],
            'max_depth': None
        })()
        
        mapper = ProjectMapper(config)
        mapper.setup_logging()
        
        assert mapper.logger is not None
        assert len(mapper.logger.handlers) == 1
        assert isinstance(mapper.logger.handlers[0], logging.FileHandler)
        
        mapper.cleanup()
    
    def test_setup_logging_file_error(self):
        """Test logging setup with file error."""
        config = type('Config', (), {
            'directories': ['.'],
            'pattern': '*',
            'output': '/invalid/path/output.txt',
            'gitignore': None,
            'use_gitignore': False,
            'no_gitignore': False,
            'exclude_dirs': [],
            'exclude_names': [],
            'exclude_patterns': [],
            'max_depth': None
        })()
        
        mapper = ProjectMapper(config)
        with pytest.raises(SystemExit):
            mapper.setup_logging()
    
    def test_should_exclude_path_gitignore(self, tmp_path):
        """Test path exclusion via gitignore."""
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("*.log\n*.tmp\n")
        
        config = type('Config', (), {
            'directories': [str(tmp_path)],
            'pattern': '*',
            'output': None,
            'gitignore': None,
            'use_gitignore': True,
            'no_gitignore': False,
            'exclude_dirs': [],
            'exclude_names': [],
            'exclude_patterns': [],
            'max_depth': None
        })()
        
        mapper = ProjectMapper(config)
        
        log_file = tmp_path / "app.log"
        tmp_file = tmp_path / "temp.tmp"
        txt_file = tmp_path / "doc.txt"
        
        log_file.touch()
        tmp_file.touch()
        txt_file.touch()
        
        assert mapper.should_exclude_path(log_file)
        assert mapper.should_exclude_path(tmp_file)
        assert not mapper.should_exclude_path(txt_file)
        assert mapper.excluded_count == 2
    
    def test_should_exclude_path_exclude_dirs(self, tmp_path):
        """Test directory exclusion."""
        config = type('Config', (), {
            'directories': [str(tmp_path)],
            'pattern': '*',
            'output': None,
            'gitignore': None,
            'use_gitignore': False,
            'no_gitignore': False,
            'exclude_dirs': ['node_modules', '__pycache__'],
            'exclude_names': [],
            'exclude_patterns': [],
            'max_depth': None
        })()
        
        mapper = ProjectMapper(config)
        
        node_dir = tmp_path / "node_modules"
        cache_dir = tmp_path / "__pycache__"
        src_dir = tmp_path / "src"
        
        node_dir.mkdir()
        cache_dir.mkdir()
        src_dir.mkdir()
        
        assert mapper.should_exclude_path(node_dir, is_dir=True)
        assert mapper.should_exclude_path(cache_dir, is_dir=True)
        assert not mapper.should_exclude_path(src_dir, is_dir=True)
    
    def test_should_exclude_path_exclude_names(self, tmp_path):
        """Test file name exclusion."""
        config = type('Config', (), {
            'directories': [str(tmp_path)],
            'pattern': '*',
            'output': None,
            'gitignore': None,
            'use_gitignore': False,
            'no_gitignore': False,
            'exclude_dirs': [],
            'exclude_names': ['*.log', '*.tmp', 'secret.txt'],
            'exclude_patterns': [],
            'max_depth': None
        })()
        
        mapper = ProjectMapper(config)
        
        log_file = tmp_path / "app.log"
        tmp_file = tmp_path / "temp.tmp"
        secret_file = tmp_path / "secret.txt"
        normal_file = tmp_path / "normal.txt"
        
        for f in [log_file, tmp_file, secret_file, normal_file]:
            f.touch()
        
        assert mapper.should_exclude_path(log_file)
        assert mapper.should_exclude_path(tmp_file)
        assert mapper.should_exclude_path(secret_file)
        assert not mapper.should_exclude_path(normal_file)
    
    def test_should_exclude_path_exclude_patterns(self, tmp_path):
        """Test pattern exclusion."""
        config = type('Config', (), {
            'directories': [str(tmp_path)],
            'pattern': '*',
            'output': None,
            'gitignore': None,
            'use_gitignore': False,
            'no_gitignore': False,
            'exclude_dirs': [],
            'exclude_names': [],
            'exclude_patterns': ['test_*', '*_backup'],
            'max_depth': None
        })()
        
        mapper = ProjectMapper(config)
        
        test_file = tmp_path / "test_file.py"
        backup_file = tmp_path / "file_backup"
        normal_file = tmp_path / "normal.py"
        
        test_file.touch()
        backup_file.touch()
        normal_file.touch()
        
        assert mapper.should_exclude_path(test_file)
        assert mapper.should_exclude_path(backup_file)
        assert not mapper.should_exclude_path(normal_file)
    
    def test_should_exclude_path_git_dir(self, tmp_path):
        """Test .git directory exclusion."""
        config = type('Config', (), {
            'directories': [str(tmp_path)],
            'pattern': '*',
            'output': None,
            'gitignore': None,
            'use_gitignore': False,
            'no_gitignore': False,
            'exclude_dirs': [],
            'exclude_names': [],
            'exclude_patterns': [],
            'max_depth': None
        })()
        
        mapper = ProjectMapper(config)
        
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        
        assert mapper.should_exclude_path(git_dir, is_dir=True)
    
    def test_should_exclude_path_pattern_filter(self, tmp_path):
        """Test filtering by pattern."""
        config = type('Config', (), {
            'directories': [str(tmp_path)],
            'pattern': '*.py',
            'output': None,
            'gitignore': None,
            'use_gitignore': False,
            'no_gitignore': False,
            'exclude_dirs': [],
            'exclude_names': [],
            'exclude_patterns': [],
            'max_depth': None
        })()
        
        mapper = ProjectMapper(config)
        
        py_file = tmp_path / "script.py"
        txt_file = tmp_path / "doc.txt"
        
        py_file.touch()
        txt_file.touch()
        
        assert not mapper.should_exclude_path(py_file)
    
    def test_get_tree_structure_single_dir(self, temp_dir_structure):
        """Test tree structure generation for single directory."""
        config = type('Config', (), {
            'directories': [str(temp_dir_structure)],
            'pattern': '*',
            'output': None,
            'gitignore': None,
            'use_gitignore': False,
            'no_gitignore': False,
            'exclude_dirs': [],
            'exclude_names': [],
            'exclude_patterns': [],
            'max_depth': None
        })()
        
        mapper = ProjectMapper(config)
        tree_lines = mapper.get_tree_structure()
        
        assert len(tree_lines) > 0
        assert f"{temp_dir_structure.name}/" in tree_lines[0]
        assert any("src/" in line for line in tree_lines)
        assert any("tests/" in line for line in tree_lines)
    
    def test_get_tree_structure_multiple_dirs(self, temp_dir_structure):
        """Test tree structure generation for multiple directories."""
        dir1 = temp_dir_structure / "dir1"
        dir2 = temp_dir_structure / "dir2"
        dir1.mkdir()
        dir2.mkdir()
        (dir1 / "file1.txt").touch()
        (dir2 / "file2.txt").touch()
        
        config = type('Config', (), {
            'directories': [str(dir1), str(dir2)],
            'pattern': '*',
            'output': None,
            'gitignore': None,
            'use_gitignore': False,
            'no_gitignore': False,
            'exclude_dirs': [],
            'exclude_names': [],
            'exclude_patterns': [],
            'max_depth': None
        })()
        
        mapper = ProjectMapper(config)
        tree_lines = mapper.get_tree_structure()
        
        assert "COMBINED VIEW/" in tree_lines[0]
        assert any("dir1/" in line for line in tree_lines)
        assert any("dir2/" in line for line in tree_lines)
    
    def test_get_tree_structure_max_depth(self, temp_dir_structure):
        """Test tree structure with max depth limitation."""
        config = type('Config', (), {
            'directories': [str(temp_dir_structure)],
            'pattern': '*',
            'output': None,
            'gitignore': None,
            'use_gitignore': False,
            'no_gitignore': False,
            'exclude_dirs': [],
            'exclude_names': [],
            'exclude_patterns': [],
            'max_depth': 1
        })()
        
        mapper = ProjectMapper(config)
        tree_lines = mapper.get_tree_structure()
        
        assert any("src/" in line for line in tree_lines)
        assert any("tests/" in line for line in tree_lines)
        assert not any("utils/" in line for line in tree_lines)
    
    def test_get_tree_structure_permission_error(self, monkeypatch, tmp_path):
        """Test tree generation with permission error."""
        config = type('Config', (), {
            'directories': [str(tmp_path)],
            'pattern': '*',
            'output': None,
            'gitignore': None,
            'use_gitignore': False,
            'no_gitignore': False,
            'exclude_dirs': [],
            'exclude_names': [],
            'exclude_patterns': [],
            'max_depth': None
        })()
        
        mapper = ProjectMapper(config)
        
        mock_iterdir = MagicMock(side_effect=PermissionError("Access denied"))
        monkeypatch.setattr(Path, "iterdir", mock_iterdir)
        
        tree_lines = mapper.get_tree_structure()
        
        assert any("[Permission Denied]" in line for line in tree_lines)
    
    def test_get_statistics(self, temp_dir_structure):
        """Test statistics collection."""
        config = type('Config', (), {
            'directories': [str(temp_dir_structure)],
            'pattern': '*',
            'output': None,
            'gitignore': None,
            'use_gitignore': False,
            'no_gitignore': False,
            'exclude_dirs': [],
            'exclude_names': [],
            'exclude_patterns': [],
            'max_depth': None
        })()
        
        mapper = ProjectMapper(config)
        stats = mapper.get_statistics()
        
        assert 'directories' in stats
        assert 'files' in stats
        assert 'total_size' in stats
        assert 'directories_scanned' in stats
        assert stats['files'] >= 9
        assert stats['total_size'] >= 1024 * 1024
    
    def test_get_statistics_with_exclusions(self, temp_dir_structure):
        """Test statistics with exclusions."""
        config = type('Config', (), {
            'directories': [str(temp_dir_structure)],
            'pattern': '*',
            'output': None,
            'gitignore': None,
            'use_gitignore': False,
            'no_gitignore': False,
            'exclude_dirs': ['.hidden'],
            'exclude_names': ['*.bin'],
            'exclude_patterns': [],
            'max_depth': None
        })()
        
        mapper = ProjectMapper(config)
        stats = mapper.get_statistics()
        
        assert stats['directories'] < 5



class TestCommandLine:
    
    def test_main_no_args(self, capsys):
        """Test main with no arguments."""
        with patch('sys.argv', ['codingutils/tree_generater.py']):
            with patch('codingutils.tree_generater.ProjectMapper') as MockMapper:
                mock_instance = MockMapper.return_value
                mock_instance.generate_tree.return_value = True
                mock_instance.cleanup = MagicMock()
                
                result = main()
                
                assert result == 0
                MockMapper.assert_called_once()
    
    def test_main_with_directory_arg(self, temp_dir_structure, capsys):
        """Test main with directory argument."""
        with patch('sys.argv', ['codingutils/tree_generater.py', '-d', str(temp_dir_structure)]):
            with patch('codingutils.tree_generater.ProjectMapper') as MockMapper:
                mock_instance = MockMapper.return_value
                mock_instance.generate_tree.return_value = True
                mock_instance.cleanup = MagicMock()
                
                result = main()
                
                assert result == 0
                MockMapper.assert_called_once()
                args = MockMapper.call_args[0][0]
                assert str(temp_dir_structure) in args.directories
    
    def test_main_with_multiple_directories(self, temp_dir_structure):
        """Test main with multiple directories."""
        dir1 = temp_dir_structure / "dir1"
        dir2 = temp_dir_structure / "dir2"
        dir1.mkdir()
        dir2.mkdir()
        
        with patch('sys.argv', ['codingutils/tree_generater.py', '-d', str(dir1), '-d', str(dir2)]):
            with patch('codingutils.tree_generater.ProjectMapper') as MockMapper:
                mock_instance = MockMapper.return_value
                mock_instance.generate_tree.return_value = True
                mock_instance.cleanup = MagicMock()
                
                result = main()
                
                assert result == 0
                MockMapper.assert_called_once()
                args = MockMapper.call_args[0][0]
                assert len(args.directories) == 2
    
    def test_main_with_pattern(self):
        """Test main with pattern argument."""
        with patch('sys.argv', ['codingutils/tree_generater.py', '-p', '*.py']):
            with patch('codingutils.tree_generater.ProjectMapper') as MockMapper:
                mock_instance = MockMapper.return_value
                mock_instance.generate_tree.return_value = True
                mock_instance.cleanup = MagicMock()
                
                result = main()
                
                assert result == 0
                MockMapper.assert_called_once()
                args = MockMapper.call_args[0][0]
                assert args.pattern == '*.py'
    
    def test_main_with_output_file(self, tmp_path):
        """Test main with output file argument."""
        output_file = tmp_path / "output.txt"
        
        with patch('sys.argv', ['codingutils/tree_generater.py', '-o', str(output_file)]):
            with patch('codingutils.tree_generater.ProjectMapper') as MockMapper:
                mock_instance = MockMapper.return_value
                mock_instance.generate_tree.return_value = True
                mock_instance.cleanup = MagicMock()
                
                result = main()
                
                assert result == 0
                MockMapper.assert_called_once()
                args = MockMapper.call_args[0][0]
                assert args.output == str(output_file)
    
    def test_main_with_exclusions(self):
        """Test main with various exclusion arguments."""
        test_args = [
            'codingutils/tree_generater.py',
            '-ed', 'node_modules',
            '-ed', '__pycache__',
            '-en', '*.log',
            '-en', '*.tmp',
            '-ep', 'test_*',
            '-ep', '*_backup'
        ]
        
        with patch('sys.argv', test_args):
            with patch('codingutils.tree_generater.ProjectMapper') as MockMapper:
                mock_instance = MockMapper.return_value
                mock_instance.generate_tree.return_value = True
                mock_instance.cleanup = MagicMock()
                
                result = main()
                
                assert result == 0
                MockMapper.assert_called_once()
                args = MockMapper.call_args[0][0]
                assert 'node_modules' in args.exclude_dirs
                assert '__pycache__' in args.exclude_dirs
                assert '*.log' in args.exclude_names
                assert '*.tmp' in args.exclude_names
                assert 'test_*' in args.exclude_patterns
                assert '*_backup' in args.exclude_patterns
    
    def test_main_gitignore_options(self, tmp_path):
        """Test main with gitignore options."""
        gitignore_file = tmp_path / ".gitignore"
        
        test_args = [
            'codingutils/tree_generater.py',
            '-i', str(gitignore_file),
            '-ig',
            '--no-gitignore'
        ]
        
        with patch('sys.argv', test_args):
            with patch('codingutils.tree_generater.ProjectMapper') as MockMapper:
                mock_instance = MockMapper.return_value
                mock_instance.generate_tree.return_value = True
                mock_instance.cleanup = MagicMock()
                
                result = main()
                
                assert result == 0
                MockMapper.assert_called_once()
                args = MockMapper.call_args[0][0]
                assert args.gitignore == str(gitignore_file)
                assert args.use_gitignore is True
                assert args.no_gitignore is True
    
    def test_main_max_depth(self):
        """Test main with max depth argument."""
        with patch('sys.argv', ['codingutils/tree_generater.py', '--max-depth', '3']):
            with patch('codingutils.tree_generater.ProjectMapper') as MockMapper:
                mock_instance = MockMapper.return_value
                mock_instance.generate_tree.return_value = True
                mock_instance.cleanup = MagicMock()
                
                result = main()
                
                assert result == 0
                MockMapper.assert_called_once()
                args = MockMapper.call_args[0][0]
                assert args.max_depth == 3
    
    def test_main_generate_tree_fails(self):
        """Test main when generate_tree returns False."""
        with patch('sys.argv', ['codingutils/tree_generater.py']):
            with patch('codingutils.tree_generater.ProjectMapper') as MockMapper:
                mock_instance = MockMapper.return_value
                mock_instance.generate_tree.return_value = False
                mock_instance.cleanup = MagicMock()
                
                result = main()
                
                assert result == 1
                MockMapper.assert_called_once()



class TestIntegration:
    
    def test_end_to_end_simple(self, temp_dir_structure, capsys):
        """End-to-end test with simple directory structure."""
        test_dir = temp_dir_structure / "test_project"
        test_dir.mkdir()
        (test_dir / "main.py").write_text("print('Hello')")
        (test_dir / "utils.py").write_text("# Utilities")
        (test_dir / "data").mkdir()
        (test_dir / "data" / "config.json").write_text("{}")
        
        with patch('sys.argv', ['codingutils/tree_generater.py', '-d', str(test_dir)]):
            result = main()
        
        assert result == 0
    
    def test_end_to_end_with_gitignore(self, temp_dir_structure):
        """End-to-end test with .gitignore file."""
        test_dir = temp_dir_structure / "test_project"
        test_dir.mkdir()
        
        gitignore = test_dir / ".gitignore"
        gitignore.write_text("*.log\n__pycache__/\n*.pyc\n")
        
        (test_dir / "app.py").touch()
        (test_dir / "app.log").touch()
        (test_dir / "__pycache__").mkdir()
        (test_dir / "__pycache__" / "app.pyc").touch()
        
        with patch('sys.argv', ['codingutils/tree_generater.py', '-d', str(test_dir), '-ig']):
            result = main()
        
        assert result == 0
    
    def test_end_to_end_with_exclusions(self, temp_dir_structure):
        """End-to-end test with command line exclusions."""
        test_dir = temp_dir_structure / "test_project"
        test_dir.mkdir()
        
        (test_dir / "src").mkdir()
        (test_dir / "tests").mkdir()
        (test_dir / "build").mkdir()
        (test_dir / "dist").mkdir()
        
        (test_dir / "src" / "main.py").touch()
        (test_dir / "tests" / "test_main.py").touch()
        (test_dir / "build" / "output.exe").touch()
        (test_dir / "dist" / "package.zip").touch()
        
        test_args = [
            'codingutils/tree_generater.py',
            '-d', str(test_dir),
            '-ed', 'build',
            '-ed', 'dist',
            '-en', '*.pyc',
            '-en', '*.log'
        ]
        
        with patch('sys.argv', test_args):
            result = main()
        
        assert result == 0
    
    def test_end_to_end_output_to_file(self, temp_dir_structure, tmp_path):
        """End-to-end test with output to file."""
        test_dir = temp_dir_structure / "test_project"
        test_dir.mkdir()
        (test_dir / "file1.txt").touch()
        (test_dir / "file2.txt").touch()
        
        output_file = tmp_path / "tree_output.txt"
        
        with patch('sys.argv', ['codingutils/tree_generater.py', '-d', str(test_dir), '-o', str(output_file)]):
            result = main()
        
        assert result == 0
        assert output_file.exists()
        content = output_file.read_text()
        assert "Project Tree:" in content
        assert "file1.txt" in content or "file2.txt" in content



class TestEdgeCases:
    
    def test_empty_directory(self, tmp_path):
        """Test with empty directory."""
        config = type('Config', (), {
            'directories': [str(tmp_path)],
            'pattern': '*',
            'output': None,
            'gitignore': None,
            'use_gitignore': False,
            'no_gitignore': False,
            'exclude_dirs': [],
            'exclude_names': [],
            'exclude_patterns': [],
            'max_depth': None
        })()
        
        mapper = ProjectMapper(config)
        mapper.setup_logging()
        success = mapper.generate_tree()
        mapper.cleanup()
        
        assert success
    
    def test_symbolic_links(self, tmp_path):
        """Test with symbolic links (if supported)."""
        import os
        
        main_dir = tmp_path / "main"
        link_dir = tmp_path / "link"
        main_dir.mkdir()
        
        (main_dir / "real_file.txt").touch()
        
        try:
            os.symlink(main_dir, link_dir)
            has_symlinks = True
        except (OSError, AttributeError):
            has_symlinks = False
        
        if has_symlinks:
            config = type('Config', (), {
                'directories': [str(tmp_path)],
                'pattern': '*',
                'output': None,
                'gitignore': None,
                'use_gitignore': False,
                'no_gitignore': False,
                'exclude_dirs': [],
                'exclude_names': [],
                'exclude_patterns': [],
                'max_depth': None
            })()
            
            mapper = ProjectMapper(config)
            mapper.setup_logging()
            success = mapper.generate_tree()
            mapper.cleanup()
            
            assert success
    
    def test_unicode_filenames(self, tmp_path):
        """Test with Unicode filenames."""
        (tmp_path / "normal.txt").touch()
        (tmp_path / "café.txt").touch()
        (tmp_path / "测试.txt").touch()
        (tmp_path / "🎉.txt").touch()
        
        config = type('Config', (), {
            'directories': [str(tmp_path)],
            'pattern': '*',
            'output': None,
            'gitignore': None,
            'use_gitignore': False,
            'no_gitignore': False,
            'exclude_dirs': [],
            'exclude_names': [],
            'exclude_patterns': [],
            'max_depth': None
        })()
        
        mapper = ProjectMapper(config)
        mapper.setup_logging()
        success = mapper.generate_tree()
        mapper.cleanup()
        
        assert success
    
    def test_long_filenames(self, tmp_path):
        """Test with long filenames."""
        long_name = "a" * 100 + ".txt"
        (tmp_path / long_name).touch()
        
        config = type('Config', (), {
            'directories': [str(tmp_path)],
            'pattern': '*',
            'output': None,
            'gitignore': None,
            'use_gitignore': False,
            'no_gitignore': False,
            'exclude_dirs': [],
            'exclude_names': [],
            'exclude_patterns': [],
            'max_depth': None
        })()
        
        mapper = ProjectMapper(config)
        mapper.setup_logging()
        success = mapper.generate_tree()
        mapper.cleanup()
        
        assert success
    
    def test_hidden_files_and_dirs(self, tmp_path):
        """Test with hidden files and directories."""
        (tmp_path / ".hidden_file").touch()
        (tmp_path / ".hidden_dir").mkdir()
        (tmp_path / ".hidden_dir" / "nested.txt").touch()
        (tmp_path / "normal.txt").touch()
        
        config = type('Config', (), {
            'directories': [str(tmp_path)],
            'pattern': '*',
            'output': None,
            'gitignore': None,
            'use_gitignore': False,
            'no_gitignore': False,
            'exclude_dirs': [],
            'exclude_names': [],
            'exclude_patterns': [],
            'max_depth': None
        })()
        
        mapper = ProjectMapper(config)
        mapper.setup_logging()
        success = mapper.generate_tree()
        mapper.cleanup()
        
        assert success


if __name__ == "__main__":
    pytest.main([__file__, "-v"])