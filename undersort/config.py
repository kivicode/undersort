"""Configuration loading for undersort."""

import tomllib
from pathlib import Path

from undersort import logger


def load_config() -> dict[str, list[str] | None]:
    """Load configuration from pyproject.toml.

    Returns:
        Dictionary with 'order' and 'method_type_order' keys.
    """
    default_config: dict[str, list[str] | None] = {
        "order": ["public", "protected", "private"],
        "method_type_order": None,
    }

    pyproject_path = _find_pyproject_toml()
    if not pyproject_path:
        return default_config

    try:
        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)
    except Exception as e:
        logger.warning(f"Could not load {pyproject_path}: {e}")
        return default_config

    if "tool" not in data or "undersort" not in data["tool"]:
        return default_config

    config = data["tool"]["undersort"]
    result: dict[str, list[str] | None] = default_config.copy()

    if "order" in config:
        order = config["order"]
        valid_visibility_values = {"public", "protected", "private"}
        if not all(v in valid_visibility_values for v in order):
            logger.warning(f"Invalid order values in {pyproject_path}. Using default order.")
        else:
            result["order"] = order

    if "method_type_order" in config:
        method_type_order = config["method_type_order"]
        valid_method_types = {"class", "static", "instance"}
        if not all(v in valid_method_types for v in method_type_order):
            logger.warning(f"Invalid method_type_order values in {pyproject_path}. Using default.")
        else:
            result["method_type_order"] = method_type_order

    return result


def _find_pyproject_toml() -> Path | None:
    """Find pyproject.toml in current or parent directories.

    Returns:
        Path to pyproject.toml if found, None otherwise.
    """
    current_dir = Path.cwd()
    for directory in [current_dir, *current_dir.parents]:
        pyproject_path = directory / "pyproject.toml"
        if pyproject_path.exists():
            return pyproject_path
    return None
