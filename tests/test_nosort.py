"""Tests for nosort comment directives."""

import tempfile
from pathlib import Path

from undersort.sorter import sort_file


class TestNosortDirectives:
    """Tests for # nosort comment functionality."""

    def test_file_level_nosort(self) -> None:
        """Test that file-level nosort prevents all sorting."""
        source = """# nosort: file
class Example:
    def _protected(self):
        pass

    def public(self):
        pass
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(source)
            temp_path = Path(f.name)

        try:
            order = ["public", "protected", "private"]
            was_modified = sort_file(temp_path, order)

            assert was_modified is False

            with open(temp_path) as f:
                result = f.read()

            assert result == source
        finally:
            temp_path.unlink()

    def test_class_level_nosort(self) -> None:
        """Test that class-level nosort prevents sorting that class."""
        source = """class Example:  # nosort
    def _protected(self):
        pass

    def public(self):
        pass
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(source)
            temp_path = Path(f.name)

        try:
            order = ["public", "protected", "private"]
            was_modified = sort_file(temp_path, order)

            assert was_modified is False

            with open(temp_path) as f:
                result = f.read()

            assert result == source
        finally:
            temp_path.unlink()

    def test_method_level_nosort(self) -> None:
        """Test that method-level nosort keeps that method in place."""
        source = """class Example:
    def public_a(self):
        pass

    def _protected_x(self):  # nosort
        pass

    def public_b(self):
        pass
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(source)
            temp_path = Path(f.name)

        try:
            order = ["public", "protected", "private"]
            was_modified = sort_file(temp_path, order)

            assert was_modified is False

            with open(temp_path) as f:
                result = f.read()

            protected_idx = result.find("def _protected_x")
            public_a_idx = result.find("def public_a")
            public_b_idx = result.find("def public_b")

            assert public_a_idx < protected_idx < public_b_idx
        finally:
            temp_path.unlink()

    def test_multiple_nosort_methods(self) -> None:
        """Test multiple methods with nosort."""
        source = """class Example:
    def public_a(self):
        pass

    def _protected_x(self):  # nosort
        pass

    def public_b(self):  # nosort
        pass

    def _protected_y(self):
        pass
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(source)
            temp_path = Path(f.name)

        try:
            order = ["public", "protected", "private"]
            was_modified = sort_file(temp_path, order)

            assert was_modified is False

            with open(temp_path) as f:
                result = f.read()

            assert result == source
        finally:
            temp_path.unlink()

    def test_nosort_case_insensitive(self) -> None:
        """Test that NOSORT and NoSort also work."""
        source = """class Example:  # NOSORT
    def _protected(self):
        pass

    def public(self):
        pass
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(source)
            temp_path = Path(f.name)

        try:
            order = ["public", "protected", "private"]
            was_modified = sort_file(temp_path, order)

            assert was_modified is False
        finally:
            temp_path.unlink()

    def test_nosort_with_other_classes(self) -> None:
        """Test that nosort on one class doesn't affect others."""
        source = """class First:  # nosort
    def _protected(self):
        pass

    def public(self):
        pass

class Second:
    def _protected(self):
        pass

    def public(self):
        pass
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(source)
            temp_path = Path(f.name)

        try:
            order = ["public", "protected", "private"]
            was_modified = sort_file(temp_path, order)

            assert was_modified is True

            with open(temp_path) as f:
                result = f.read()

            first_protected_idx = result.find("class First")
            first_protected_method_idx = result.find("def _protected", first_protected_idx)
            first_public_idx = result.find("def public", first_protected_idx)
            second_class_idx = result.find("class Second")
            second_public_idx = result.find("def public", second_class_idx)
            second_protected_idx = result.find("def _protected", second_class_idx)

            assert first_protected_method_idx < first_public_idx
            assert second_public_idx < second_protected_idx
        finally:
            temp_path.unlink()
