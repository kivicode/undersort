"""Core sorting logic for class methods."""

import difflib
from pathlib import Path
from typing import Literal

import libcst as cst

from undersort import logger


def get_method_visibility(method_name: str) -> Literal["public", "private", "protected"]:
    """Determine method visibility based on naming convention.

    Args:
        method_name: The name of the method

    Returns:
        'public' for method (no underscore prefix) or magic methods (__method__),
        'protected' for _method (single underscore),
        'private' for __method (dunder prefix, not magic method)
    """
    if method_name.startswith("__") and method_name.endswith("__"):
        return "public"

    if method_name.startswith("__"):
        return "private"

    if method_name.startswith("_"):
        return "protected"

    return "public"


def get_method_type(method: cst.FunctionDef) -> str:
    """Determine method type based on decorators.

    Args:
        method: The FunctionDef node

    Returns:
        'class' for @classmethod,
        'static' for @staticmethod,
        'instance' for regular instance methods (default)
    """
    for decorator in method.decorators:
        decorator_name = decorator.decorator
        if isinstance(decorator_name, cst.Name):
            if decorator_name.value == "classmethod":
                return "class"
            if decorator_name.value == "staticmethod":
                return "static"
    return "instance"


class MethodSorter(cst.CSTTransformer):
    """Transformer to sort class methods by visibility and type."""

    def __init__(self, order: list[str], method_type_order: list[str] | None = None):
        """Initialize the transformer.

        Args:
            order: List specifying the desired order of visibility levels
                   (e.g., ["public", "protected", "private"])
            method_type_order: Optional list specifying the order of method types
                              within each visibility level
                              (e.g., ["instance", "class", "static"])
        """
        self.order = order
        self.method_type_order = method_type_order or ["instance", "class", "static"]
        self.modified = False

    def leave_ClassDef(  # noqa: PLR0912, PLR0915
        self, original_node: cst.ClassDef, updated_node: cst.ClassDef
    ) -> cst.ClassDef:
        """Sort methods within a class definition.

        Args:
            original_node: Original class definition node
            updated_node: Updated class definition node

        Returns:
            ClassDef with sorted methods
        """
        methods = []
        non_methods = []

        for item in updated_node.body.body:
            if isinstance(item, cst.FunctionDef):
                methods.append(item)
            else:
                non_methods.append(item)

        if not methods:
            return updated_node

        method_with_index = [(i, method) for i, method in enumerate(methods)]

        method_groups: dict[str, dict[str, list[tuple[int, cst.FunctionDef]]]] = {
            "public": {"class": [], "static": [], "instance": []},
            "protected": {"class": [], "static": [], "instance": []},
            "private": {"class": [], "static": [], "instance": []},
        }

        for idx, method in method_with_index:
            visibility = get_method_visibility(method.name.value)
            method_type = get_method_type(method)
            method_groups[visibility][method_type].append((idx, method))

        group_order = []
        for visibility in self.order:
            for method_type in self.method_type_order:
                group_order.append((visibility, method_type))

        sorted_methods = []
        current_position = 0

        for visibility, method_type in group_order:
            group = method_groups[visibility][method_type]
            if not group:
                continue

            group_indices = [idx for idx, _ in group]
            min_original_idx = min(group_indices)
            max_original_idx = max(group_indices)

            moved_down = []
            in_place = []
            moved_up = []

            for idx, method in group:
                if idx < min_original_idx or (idx < current_position and current_position > 0):
                    moved_down.append((idx, method))
                elif idx > max_original_idx:
                    moved_up.append((idx, method))
                else:
                    in_place.append((idx, method))

            moved_down.sort(key=lambda x: x[0])
            in_place.sort(key=lambda x: x[0])
            moved_up.sort(key=lambda x: x[0])

            group_sorted = moved_down + in_place + moved_up
            sorted_methods.extend([method for _, method in group_sorted])

            current_position += len(group)

        if methods != sorted_methods:
            self.modified = True

        leading_non_methods = []
        trailing_non_methods = []
        found_method = False
        original_items = list(updated_node.body.body)

        for item in original_items:
            if isinstance(item, cst.FunctionDef):
                found_method = True
            elif not found_method:
                leading_non_methods.append(item)
            else:
                trailing_non_methods.append(item)

        new_body = leading_non_methods + sorted_methods + trailing_non_methods

        return updated_node.with_changes(body=updated_node.body.with_changes(body=new_body))


def sort_file(
    file_path: Path,
    order: list[str],
    method_type_order: list[str] | None = None,
    check_only: bool = False,
    show_diff: bool = False,
) -> bool:
    """Sort methods in a Python file.

    Args:
        file_path: Path to the Python file
        order: Method visibility ordering configuration
        method_type_order: Optional method type ordering within each visibility level
        check_only: If True, only check if file needs sorting
        show_diff: If True, show diff of changes

    Returns:
        True if file was modified (or needs modification in check mode)
    """
    with open(file_path, encoding="utf-8") as f:
        source_code = f.read()

    try:
        tree = cst.parse_module(source_code)
    except cst.ParserSyntaxError as e:
        raise ValueError(f"Syntax error in {file_path}: {e}")

    sorter = MethodSorter(order, method_type_order)
    new_tree = tree.visit(sorter)

    if not sorter.modified:
        return False

    new_code = new_tree.code

    if show_diff:
        diff = difflib.unified_diff(
            source_code.splitlines(keepends=True),
            new_code.splitlines(keepends=True),
            fromfile=str(file_path),
            tofile=str(file_path),
        )
        logger.diff("".join(diff))

    if not check_only:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(new_code)

    return True
