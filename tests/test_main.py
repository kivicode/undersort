"""Tests for main CLI functionality."""

from pathlib import Path

from undersort.main import collect_python_files


class TestCollectPythonFiles:
    """Tests for collect_python_files function."""

    def test_collect_single_file(self, tmp_path: Path) -> None:
        """Test collecting a single Python file."""
        py_file = tmp_path / "test.py"
        py_file.write_text("# test")

        result = collect_python_files(py_file)
        assert result == [py_file]

    def test_collect_non_python_file(self, tmp_path: Path) -> None:
        """Test that non-Python files are ignored."""
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("test")

        result = collect_python_files(txt_file)
        assert result == []

    def test_collect_directory_recursive(self, tmp_path: Path) -> None:
        """Test collecting Python files from directory recursively."""
        # Create structure
        (tmp_path / "file1.py").write_text("# file1")
        (tmp_path / "subdir").mkdir()
        (tmp_path / "subdir" / "file2.py").write_text("# file2")
        (tmp_path / "subdir" / "nested").mkdir()
        (tmp_path / "subdir" / "nested" / "file3.py").write_text("# file3")

        result = collect_python_files(tmp_path, recursive=True)

        assert len(result) == 3
        assert any(f.name == "file1.py" for f in result)
        assert any(f.name == "file2.py" for f in result)
        assert any(f.name == "file3.py" for f in result)

    def test_collect_directory_non_recursive(self, tmp_path: Path) -> None:
        """Test collecting Python files from directory non-recursively."""
        # Create structure
        (tmp_path / "file1.py").write_text("# file1")
        (tmp_path / "subdir").mkdir()
        (tmp_path / "subdir" / "file2.py").write_text("# file2")

        result = collect_python_files(tmp_path, recursive=False)

        assert len(result) == 1
        assert result[0].name == "file1.py"

    def test_exclude_venv_directories(self, tmp_path: Path) -> None:
        """Test that .venv directories are excluded."""
        # Create structure
        (tmp_path / "file1.py").write_text("# file1")
        (tmp_path / ".venv").mkdir()
        (tmp_path / ".venv" / "file2.py").write_text("# file2")

        result = collect_python_files(tmp_path, recursive=True)

        assert len(result) == 1
        assert result[0].name == "file1.py"

    def test_exclude_git_directories(self, tmp_path: Path) -> None:
        """Test that .git directories are excluded."""
        # Create structure
        (tmp_path / "file1.py").write_text("# file1")
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "hooks").mkdir()
        (tmp_path / ".git" / "hooks" / "pre-commit.py").write_text("# hook")

        result = collect_python_files(tmp_path, recursive=True)

        assert len(result) == 1
        assert result[0].name == "file1.py"

    def test_exclude_pycache_directories(self, tmp_path: Path) -> None:
        """Test that __pycache__ directories are excluded."""
        # Create structure
        (tmp_path / "file1.py").write_text("# file1")
        (tmp_path / "__pycache__").mkdir()
        (tmp_path / "__pycache__" / "file1.cpython-311.pyc").write_text("# compiled")

        result = collect_python_files(tmp_path, recursive=True)

        assert len(result) == 1
        assert result[0].name == "file1.py"

    def test_nonexistent_path(self, tmp_path: Path) -> None:
        """Test that nonexistent paths return empty list."""
        nonexistent = tmp_path / "doesnotexist"
        result = collect_python_files(nonexistent)
        assert result == []

    def test_sorted_output(self, tmp_path: Path) -> None:
        """Test that results are sorted."""
        (tmp_path / "c.py").write_text("# c")
        (tmp_path / "a.py").write_text("# a")
        (tmp_path / "b.py").write_text("# b")

        result = collect_python_files(tmp_path, recursive=False)

        assert len(result) == 3
        assert result[0].name == "a.py"
        assert result[1].name == "b.py"
        assert result[2].name == "c.py"
