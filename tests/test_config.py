"""Tests for configuration loading."""

from pathlib import Path

import pytest

from undersort.config import _find_pyproject_toml, load_config


class TestConfigLoading:
    """Tests for configuration loading from pyproject.toml."""

    def test_default_config(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that default config is returned when no pyproject.toml exists."""
        monkeypatch.chdir(tmp_path)
        config = load_config()
        assert config == {"order": ["public", "protected", "private"], "method_type_order": None}

    def test_load_custom_order(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test loading custom order from pyproject.toml."""
        pyproject_content = """
[tool.undersort]
order = ["private", "protected", "public"]
"""
        pyproject_path = tmp_path / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        monkeypatch.chdir(tmp_path)
        config = load_config()
        assert config == {"order": ["private", "protected", "public"], "method_type_order": None}

    def test_invalid_order_values(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that invalid order values fall back to default."""
        pyproject_content = """
[tool.undersort]
order = ["public", "invalid", "private"]
"""
        pyproject_path = tmp_path / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        monkeypatch.chdir(tmp_path)
        config = load_config()
        assert config == {"order": ["public", "protected", "private"], "method_type_order": None}

    def test_missing_order_key(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that missing order key returns default."""
        pyproject_content = """
[tool.undersort]
some_other_key = "value"
"""
        pyproject_path = tmp_path / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        monkeypatch.chdir(tmp_path)
        config = load_config()
        assert config == {"order": ["public", "protected", "private"], "method_type_order": None}

    def test_missing_tool_section(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that missing tool.undersort section returns default."""
        pyproject_content = """
[project]
name = "test"
"""
        pyproject_path = tmp_path / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        monkeypatch.chdir(tmp_path)
        config = load_config()
        assert config == {"order": ["public", "protected", "private"], "method_type_order": None}

    def test_find_pyproject_in_parent(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that pyproject.toml is found in parent directories."""
        # Create pyproject.toml in parent
        pyproject_content = """
[tool.undersort]
order = ["private", "public", "protected"]
"""
        pyproject_path = tmp_path / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        # Change to subdirectory
        subdir = tmp_path / "subdir" / "nested"
        subdir.mkdir(parents=True)
        monkeypatch.chdir(subdir)

        config = load_config()
        assert config == {"order": ["private", "public", "protected"], "method_type_order": None}

    def test_corrupted_toml(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that corrupted TOML file falls back to default."""
        pyproject_content = """
[tool.undersort
order = ["public"  # Invalid TOML
"""
        pyproject_path = tmp_path / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        monkeypatch.chdir(tmp_path)
        config = load_config()
        assert config == {"order": ["public", "protected", "private"], "method_type_order": None}

    def test_find_pyproject_toml_not_found(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test _find_pyproject_toml returns None when not found."""
        monkeypatch.chdir(tmp_path)
        result = _find_pyproject_toml()
        assert result is None

    def test_find_pyproject_toml_found(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test _find_pyproject_toml returns path when found."""
        pyproject_path = tmp_path / "pyproject.toml"
        pyproject_path.write_text("[project]\nname = 'test'")

        monkeypatch.chdir(tmp_path)
        result = _find_pyproject_toml()
        assert result == pyproject_path
