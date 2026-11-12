"""Core sorting logic for class methods."""

import difflib
import sys
import threading
import tokenize
from collections.abc import Callable, Hashable, Sequence
from pathlib import Path
from typing import TypeVar

import libcst as cst

from undersort import logger
from undersort.deps import annotations_are_eager, eager_names

_Definition = cst.FunctionDef | cst.ClassDef

#: Visibility groups always present, and the order used when none is configured.
DEFAULT_ORDER = ("public", "protected", "private")

#: Dunder methods that build an object, kept apart from the general protocol ones.
CREATIONAL_DUNDERS = frozenset({"__new__", "__init__", "__init_subclass__", "__post_init__"})


def has_nosort_comment(node: cst.FunctionDef | cst.ClassDef) -> bool:
    """Check if a node has a nosort comment.

    Args:
        node: The node to check

    Returns:
        True if the node has a # nosort comment
    """
    if hasattr(node, "leading_lines"):
        for line in node.leading_lines:
            if isinstance(line, cst.EmptyLine) and line.comment and "nosort" in line.comment.value.lower():
                return True

    return bool(
        hasattr(node, "body")
        and hasattr(node.body, "header")
        and isinstance(node.body.header, cst.TrailingWhitespace)
        and node.body.header.comment
        and "nosort" in node.body.header.comment.value.lower()
    )


def file_has_nosort(module: cst.Module) -> bool:
    """Check if a file has a file-level nosort directive.

    Args:
        module: The module to check

    Returns:
        True if the file has a # nosort: file comment
    """
    for line in module.header:
        if isinstance(line, cst.EmptyLine) and line.comment:
            comment_text = line.comment.value.lower()
            if "nosort" in comment_text and "file" in comment_text:
                return True
    return False


def is_dunder(method_name: str) -> bool:
    """Check whether a name is a magic (dunder) name.

    Args:
        method_name: The name of the method

    Returns:
        True for names wrapped in double underscores, such as ``__init__``
    """
    return method_name.startswith("__") and method_name.endswith("__")


def get_method_visibility(method_name: str, order: Sequence[str] | None = None) -> str:
    """Determine method visibility based on naming convention.

    Dunder methods are only split out of ``public`` when the configured order
    asks for it, so an order that does not mention them keeps the historical
    behaviour of treating every magic method as public.

    Args:
        method_name: The name of the method
        order: The configured visibility order. When it contains ``"init"``,
               creational dunders form their own group; when it contains
               ``"dunder"``, the remaining magic methods form theirs.

    Returns:
        One of 'init', 'dunder', 'public', 'protected' or 'private'
    """
    groups = DEFAULT_ORDER if order is None else order

    if is_dunder(method_name):
        if method_name in CREATIONAL_DUNDERS and "init" in groups:
            return "init"
        if "dunder" in groups:
            return "dunder"
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


def minimize_movement(
    indexed_nodes: Sequence[tuple[int, cst.CSTNode]],
    group_order: Sequence[Hashable],
    group_of: Callable[[cst.CSTNode], Hashable],
) -> list[cst.CSTNode]:
    """Reorder nodes into groups while preserving as much original order as possible.

    Nodes that must move DOWN (into a later group) are placed at the beginning of
    their target group; nodes that must move UP land at the end of it. Nodes that
    are already in the right region keep their relative order.

    Args:
        indexed_nodes: (original index, node) pairs, in original order
        group_order: The desired order of group keys
        group_of: Callable mapping a node to its group key

    Returns:
        The reordered nodes
    """
    groups: dict[Hashable, list[tuple[int, cst.CSTNode]]] = {key: [] for key in group_order}
    for idx, node in indexed_nodes:
        groups[group_of(node)].append((idx, node))

    ordered: list[cst.CSTNode] = []
    current_position = 0

    for key in group_order:
        group = groups[key]
        if not group:
            continue

        group_indices = [idx for idx, _ in group]
        min_original_idx = min(group_indices)
        max_original_idx = max(group_indices)

        moved_down: list[tuple[int, cst.CSTNode]] = []
        in_place: list[tuple[int, cst.CSTNode]] = []
        moved_up: list[tuple[int, cst.CSTNode]] = []

        for idx, node in group:
            if idx < min_original_idx or (idx < current_position and current_position > 0):
                moved_down.append((idx, node))
            elif idx > max_original_idx:
                moved_up.append((idx, node))
            else:
                in_place.append((idx, node))

        moved_down.sort(key=lambda x: x[0])
        in_place.sort(key=lambda x: x[0])
        moved_up.sort(key=lambda x: x[0])

        ordered.extend([node for _, node in moved_down + in_place + moved_up])
        current_position += len(group)

    return ordered


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

    def visit_SimpleStatementLine(self, node: cst.SimpleStatementLine) -> bool:  # noqa: PLR6301, ARG002
        """Skip simple statements: they hold no classes, and long expressions nest past the recursion limit."""
        return False

    def leave_ClassDef(  # noqa: PLR0912, PLR0915
        self,
        original_node: cst.ClassDef,
        updated_node: cst.ClassDef,  # noqa: ARG002
    ) -> cst.ClassDef:
        """Sort methods within a class definition.

        Args:
            original_node: Original class definition node
            updated_node: Updated class definition node

        Returns:
            ClassDef with sorted methods
        """
        if has_nosort_comment(updated_node):
            return updated_node

        methods = []
        non_methods = []

        for item in updated_node.body.body:
            if isinstance(item, cst.FunctionDef):
                methods.append(item)
            else:
                non_methods.append(item)

        if not methods:
            return updated_node

        sortable_methods = []
        nosort_methods = []

        for i, method in enumerate(methods):
            if has_nosort_comment(method):
                nosort_methods.append((i, method))
            else:
                sortable_methods.append((i, method))

        if not sortable_methods:
            return updated_node

        group_order = [(visibility, method_type) for visibility in self.order for method_type in self.method_type_order]

        sorted_methods = minimize_movement(
            sortable_methods,
            group_order,
            lambda method: (get_method_visibility(method.name.value, self.order), get_method_type(method)),
        )

        all_sorted = sorted_methods[:]
        for orig_idx, nosort_method in sorted(nosort_methods, key=lambda x: x[0]):
            all_sorted.insert(orig_idx, nosort_method)

        if [id(method) for method in all_sorted] != [id(method) for method in methods]:
            self.modified = True
            all_sorted = _rebalance_blank_lines(methods, all_sorted)

        sorted_methods = all_sorted

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


def sort_module_definitions(
    module: cst.Module,
    order: list[str],
    eager_annotations: bool,
    sort_decorated: bool = False,
) -> tuple[cst.Module, bool]:
    """Sort module-level function and class definitions by visibility.

    Only runs of consecutive definitions are reordered: any other top-level
    statement (imports, assignments, ``if`` blocks, ...) acts as a barrier, since
    moving a definition across one could change what it sees at execution time.

    Within a run, ordering is further constrained so that a definition never moves
    above another definition it references in an eagerly evaluated position
    (decorator, base class, default value, class body, or -- when annotations are
    eager -- an annotation).

    Args:
        module: The parsed module
        order: Visibility ordering configuration
        eager_annotations: Whether annotations are evaluated at definition time
        sort_decorated: If True, decorated definitions may be reordered too. Off by
                        default: a decorator can run arbitrary code at import time
                        (registry decorators such as ``@app.route``), and moving it
                        changes the order those side effects happen in -- something
                        no static analysis can rule out.

    Returns:
        Tuple of (module, whether anything moved)
    """
    body = list(module.body)
    duplicated = _duplicated_definition_names(body)

    new_body: list[cst.BaseStatement] = []
    run: list[_Definition] = []
    modified = False
    is_first_run = True

    def flush() -> None:
        nonlocal modified, is_first_run
        if not run:
            return
        # A comment directly above the module's first statement lives in the module
        # header, not on the definition, so moving that definition would strand it.
        pin_first = is_first_run and not new_body and _header_comment_is_adjacent(module)
        is_first_run = False
        sorted_run = _sort_definition_run(
            run, order, eager_annotations, duplicated, pin_first=pin_first, sort_decorated=sort_decorated
        )
        if [id(node) for node in sorted_run] != [id(node) for node in run]:
            modified = True
            sorted_run = _rebalance_blank_lines(run, sorted_run)
        new_body.extend(sorted_run)
        run.clear()

    for statement in body:
        if isinstance(statement, (cst.FunctionDef, cst.ClassDef)):
            run.append(statement)
            continue
        flush()
        new_body.append(statement)

    flush()

    if not modified:
        return module, False

    return module.with_changes(body=new_body), True


def _header_comment_is_adjacent(module: cst.Module) -> bool:
    """Check whether the module header ends with a comment touching the first statement.

    libcst attaches comments preceding the first statement to the module header
    rather than to the statement, so such a comment would stay behind if that
    statement moved.

    Args:
        module: The parsed module

    Returns:
        True if the last header line is a comment with no blank line after it
    """
    return bool(module.header) and module.header[-1].comment is not None


def _rebalance_blank_lines(original_run: list[_Definition], sorted_run: list[_Definition]) -> list[_Definition]:
    """Keep blank-line spacing tied to positions rather than to the moved nodes.

    A definition's leading blank lines describe the gap before it, so they belong
    to the slot it occupies -- otherwise the first definition in a run (which
    usually has no blank lines above it) would collapse against its new neighbour
    when moved down. Leading comments stay attached to their definition.

    Args:
        original_run: The definitions in their original order
        sorted_run: The same definitions, reordered

    Returns:
        The reordered definitions with position-appropriate leading blank lines
    """
    slot_blanks = [_split_leading_blanks(node)[0] for node in original_run]

    rebalanced: list[_Definition] = []
    for position, node in enumerate(sorted_run):
        _, own_lines = _split_leading_blanks(node)
        rebalanced.append(node.with_changes(leading_lines=[*slot_blanks[position], *own_lines]))

    return rebalanced


def _split_leading_blanks(node: _Definition) -> tuple[list[cst.EmptyLine], list[cst.EmptyLine]]:
    """Split a definition's leading lines into blank padding and everything else.

    Args:
        node: The definition

    Returns:
        Tuple of (leading blank lines, remaining lines starting at the first comment)
    """
    lines = list(node.leading_lines)
    split_at = 0
    while split_at < len(lines) and lines[split_at].comment is None:
        split_at += 1
    return lines[:split_at], lines[split_at:]


def _duplicated_definition_names(body: Sequence[cst.BaseStatement]) -> set[str]:
    """Find top-level definition names that are declared more than once.

    Redefinitions (``@overload``, ``@singledispatch`` registrations, conditional
    re-definitions) depend on their relative order, so they are never moved.

    Args:
        body: The module body

    Returns:
        Set of names bound by more than one top-level definition
    """
    counts: dict[str, int] = {}
    for statement in body:
        if isinstance(statement, (cst.FunctionDef, cst.ClassDef)):
            counts[statement.name.value] = counts.get(statement.name.value, 0) + 1
    return {name for name, count in counts.items() if count > 1}


def _sort_definition_run(
    run: list[_Definition],
    order: list[str],
    eager_annotations: bool,
    duplicated: set[str],
    pin_first: bool = False,
    sort_decorated: bool = False,
) -> list[_Definition]:
    """Sort one run of consecutive top-level definitions.

    Args:
        run: The consecutive definitions, in original order
        order: Visibility ordering configuration
        eager_annotations: Whether annotations are evaluated at definition time
        duplicated: Names that are defined more than once and must stay put
        pin_first: If True, the first definition must keep its position
        sort_decorated: If True, decorated definitions may move as well

    Returns:
        The reordered definitions
    """
    if len(run) < 2:
        return run

    pinned = {
        idx
        for idx, node in enumerate(run)
        if has_nosort_comment(node) or node.name.value in duplicated or (node.decorators and not sort_decorated)
    }
    if pin_first:
        pinned.add(0)

    sortable = [(idx, node) for idx, node in enumerate(run) if idx not in pinned]
    if len(sortable) < 2:
        return run

    desired = minimize_movement(sortable, list(order), lambda node: get_method_visibility(node.name.value, order))

    candidate: list[_Definition] = list(desired)
    for idx in sorted(pinned):
        candidate.insert(idx, run[idx])

    predecessors = _ordering_constraints(run, eager_annotations, pinned)
    return _priority_topological_sort(run, candidate, predecessors)


def _ordering_constraints(
    run: list[_Definition],
    eager_annotations: bool,
    pinned: set[int],
) -> dict[int, set[int]]:
    """Build the "must come before" constraints for a run of definitions.

    A definition that eagerly references an earlier definition's name must stay
    after it. Pinned definitions additionally keep every neighbour on the side it
    started on.

    Args:
        run: The definitions, in original order
        eager_annotations: Whether annotations are evaluated at definition time
        pinned: Indices of definitions that must not move

    Returns:
        Mapping of index to the set of indices that must precede it
    """
    predecessors: dict[int, set[int]] = {idx: set() for idx in range(len(run))}

    for idx, node in enumerate(run):
        referenced = eager_names(node, eager_annotations)
        for earlier in range(idx):
            if run[earlier].name.value in referenced:
                predecessors[idx].add(earlier)

    for pin in pinned:
        for idx in range(len(run)):
            if idx < pin:
                predecessors[pin].add(idx)
            elif idx > pin:
                predecessors[idx].add(pin)

    return predecessors


def _priority_topological_sort(
    run: list[_Definition],
    candidate: list[_Definition],
    predecessors: dict[int, set[int]],
) -> list[_Definition]:
    """Order definitions as close to ``candidate`` as the constraints allow.

    Args:
        run: The definitions, in original order
        candidate: The preferred order, used as a tie-breaking priority
        predecessors: Mapping of index to indices that must precede it

    Returns:
        A constraint-satisfying order, or the original order if none exists
    """
    priority = {id(node): position for position, node in enumerate(candidate)}

    remaining = set(range(len(run)))
    placed: set[int] = set()
    result: list[_Definition] = []

    while remaining:
        available = [idx for idx in remaining if predecessors[idx] <= placed]
        if not available:
            return list(run)

        chosen = min(available, key=lambda idx: priority[id(run[idx])])
        remaining.discard(chosen)
        placed.add(chosen)
        result.append(run[chosen])

    return result


def _read_source(file_path: Path) -> tuple[str, str]:
    """Read a Python file, honouring its declared encoding and line endings.

    The file is decoded from bytes rather than read in text mode: text mode would
    translate CRLF line endings to LF and silently rewrite them on save. The
    encoding is taken from a PEP 263 coding declaration or BOM when present.

    Args:
        file_path: Path to the Python file

    Returns:
        Tuple of (source code, the encoding to write it back with)
    """
    try:
        with open(file_path, "rb") as f:
            encoding, _ = tokenize.detect_encoding(f.readline)
    except SyntaxError:
        encoding = "utf-8"

    return file_path.read_bytes().decode(encoding), encoding


# libcst walks and regenerates trees recursively; a long implicit string concatenation
# nests one level per literal, so a generated data module can need thousands of frames.
_DEEP_STACK_BYTES = 256 * 1024 * 1024
_DEEP_RECURSION_LIMIT = 100_000
_T = TypeVar("_T")


def _call_with_deep_stack(fn: Callable[..., _T], *args: object, **kwargs: object) -> _T:
    outcome: dict[str, object] = {}

    def run() -> None:
        try:
            outcome["value"] = fn(*args, **kwargs)
        except BaseException as e:  # noqa: BLE001 - re-raised on the caller's thread
            outcome["error"] = e

    previous_stack = threading.stack_size(_DEEP_STACK_BYTES)
    previous_limit = sys.getrecursionlimit()
    sys.setrecursionlimit(max(previous_limit, _DEEP_RECURSION_LIMIT))
    try:
        worker = threading.Thread(target=run, name="undersort-deep")
        worker.start()
        worker.join()
    finally:
        threading.stack_size(previous_stack)
        sys.setrecursionlimit(previous_limit)
    if "error" in outcome:
        raise outcome["error"]  # type: ignore[misc]
    return outcome["value"]  # type: ignore[return-value]


def sort_file(
    file_path: Path,
    order: list[str],
    method_type_order: list[str] | None = None,
    check_only: bool = False,
    show_diff: bool = False,
    sort_module_level: bool = False,
    python_version: tuple[int, int] | None = None,
    sort_decorated: bool = False,
) -> bool:
    """Sort methods in a Python file.

    Args:
        file_path: Path to the Python file
        order: Method visibility ordering configuration
        method_type_order: Optional method type ordering within each visibility level
        check_only: If True, only check if file needs sorting
        show_diff: If True, show diff of changes
        sort_module_level: If True, also sort module-level functions and classes
        python_version: Target Python version, used to decide whether annotations
                        are evaluated eagerly
        sort_decorated: If True, module-level decorated definitions may move too

    Returns:
        True if file was modified (or needs modification in check mode)
    """
    return _call_with_deep_stack(
        _sort_file,
        file_path,
        order,
        method_type_order,
        check_only,
        show_diff,
        sort_module_level,
        python_version,
        sort_decorated,
    )


def _sort_file(  # noqa: PLR0913, PLR0917
    file_path: Path,
    order: list[str],
    method_type_order: list[str] | None,
    check_only: bool,
    show_diff: bool,
    sort_module_level: bool,
    python_version: tuple[int, int] | None,
    sort_decorated: bool,
) -> bool:
    source_code, encoding = _read_source(file_path)

    try:
        tree = cst.parse_module(source_code)
    except cst.ParserSyntaxError as e:
        raise ValueError(f"Syntax error in {file_path}: {e}")

    if file_has_nosort(tree):
        return False

    sorter = MethodSorter(order, method_type_order)
    new_tree = tree.visit(sorter)
    modified = sorter.modified

    if sort_module_level:
        eager_annotations = annotations_are_eager(tree, python_version)
        new_tree, module_modified = sort_module_definitions(
            new_tree, order, eager_annotations, sort_decorated=sort_decorated
        )
        modified = modified or module_modified

    if not modified:
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
        # Written as bytes so the file's original line endings, BOM, and declared
        # encoding survive the rewrite untouched.
        file_path.write_bytes(new_code.encode(encoding))

    return True
