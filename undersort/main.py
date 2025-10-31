"""Main entry point for undersort CLI."""

import argparse
import fnmatch
import sys
from pathlib import Path

from undersort import logger
from undersort.config import load_config
from undersort.sorter import sort_file


def collect_python_files(path: Path, recursive: bool = True, exclude_patterns: list[str] | None = None) -> list[Path]:
    """Collect Python files from a path (file or directory).

    Args:
        path: File or directory path
        recursive: If True, recursively search directories
        exclude_patterns: List of glob patterns to exclude (e.g., ["tests/*", "migrations/*.py"])

    Returns:
        List of Python file paths
    """
    exclude_dirs = {
        "venv",
        "__pycache__",
        "node_modules",
    }

    if path.is_file():
        return [path] if path.suffix == ".py" else []

    if path.is_dir():
        pattern = "**/*.py" if recursive else "*.py"
        all_files = path.glob(pattern)
        filtered_files = [
            f
            for f in all_files
            if not any(part in exclude_dirs or (part.startswith(".") and part != ".") for part in f.parts)
        ]

        if exclude_patterns:
            filtered_files = [f for f in filtered_files if not _matches_any_pattern(f, exclude_patterns)]

        return sorted(filtered_files)

    return []


def _matches_any_pattern(file_path: Path, patterns: list[str]) -> bool:
    """Check if a file matches any of the exclusion patterns.

    Args:
        file_path: Path to check
        patterns: List of glob patterns

    Returns:
        True if file matches any pattern, False otherwise
    """
    path_str = str(file_path)

    for pattern in patterns:
        if fnmatch.fnmatch(path_str, pattern):
            return True

        if "/" not in pattern:
            if fnmatch.fnmatch(file_path.name, pattern):
                return True
            continue

        if fnmatch.fnmatch(path_str, f"*/{pattern}"):
            return True

        for part_idx in range(len(file_path.parts)):
            subpath = str(Path(*file_path.parts[part_idx:]))
            if fnmatch.fnmatch(subpath, pattern):
                return True

    return False


def main() -> int:  # noqa: PLR0912
    """Main entry point for undersort."""
    parser = argparse.ArgumentParser(description="Sort class methods by visibility (public, protected, private)")
    parser.add_argument(
        "paths",
        nargs="+",
        type=Path,
        help="Python files or directories to sort",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check if files need sorting without modifying them",
    )
    parser.add_argument(
        "--diff",
        action="store_true",
        help="Show diff of changes",
    )
    parser.add_argument(
        "--no-recursive",
        dest="recursive",
        action="store_false",
        default=True,
        help="Don't recursively search directories",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        help="Exclude files/directories matching pattern (can be used multiple times)",
    )

    args = parser.parse_args()

    config = load_config()

    exclude_patterns: list[str] = []
    config_exclude = config.get("exclude")
    if config_exclude:
        exclude_patterns.extend(config_exclude)
    if args.exclude:
        exclude_patterns.extend(args.exclude)

    all_files: list[Path] = []
    for path in args.paths:
        if not path.exists():
            logger.error(f"Path not found: {path}")
            continue

        python_files = collect_python_files(path, args.recursive, exclude_patterns or None)
        all_files.extend(python_files)

    if not all_files:
        logger.warning("No Python files found")
        return 0

    modified_files: list[Path] = []
    errors = False

    for file_path in all_files:
        try:
            was_modified = sort_file(
                file_path,
                config["order"],
                method_type_order=config.get("method_type_order"),
                check_only=args.check,
                show_diff=args.diff,
            )

            if not was_modified:
                continue

            modified_files.append(file_path)
            if not args.check:
                logger.success(f"Sorted {file_path}")

        except Exception as e:
            logger.error(f"Error processing {file_path}: {e}")
            errors = True

    if args.check and modified_files:
        logger.warning(f"Files that need sorting: {len(modified_files)}")
        for f in modified_files:
            logger.console.print(f"  - {f}")
        return 1

    if not modified_files and not errors:
        logger.info("All files are already sorted correctly")
    elif modified_files and not args.check:
        logger.success(f"Sorted {len(modified_files)} file(s) successfully")

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
