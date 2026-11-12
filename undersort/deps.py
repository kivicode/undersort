"""Dependency analysis for safely reordering module-level definitions.

Module-level statements execute top-to-bottom, so reordering ``def``/``class``
statements is only safe when no definition references a name that would end up
being defined *after* it in an eagerly evaluated position.

Eagerly evaluated positions are:

- decorators
- base classes and class keyword arguments (e.g. ``metaclass=``)
- default parameter values
- class bodies (everything except nested function bodies)
- annotations -- *unless* they are lazily evaluated, which happens when the
  module uses ``from __future__ import annotations`` (PEP 563) or the target
  Python version evaluates annotations lazily by default (PEP 649, 3.14+)

Function *bodies* are never eager: they only run when called, so references
made there impose no ordering constraint.
"""

import re
import sys

import libcst as cst

#: First Python version where annotations are lazily evaluated by default (PEP 649).
LAZY_ANNOTATIONS_VERSION = (3, 14)


def has_future_annotations(module: cst.Module) -> bool:
    """Check whether a module enables PEP 563 postponed annotation evaluation.

    Args:
        module: The parsed module

    Returns:
        True if the module contains ``from __future__ import annotations``
    """
    for statement in module.body:
        if not isinstance(statement, cst.SimpleStatementLine):
            continue
        for small in statement.body:
            if not isinstance(small, cst.ImportFrom) or small.module is None:
                continue
            if _dotted_name(small.module) != "__future__":
                continue
            if isinstance(small.names, cst.ImportStar):
                continue
            if any(alias.name.value == "annotations" for alias in small.names):
                return True
    return False


def annotations_are_eager(module: cst.Module, python_version: tuple[int, int] | None = None) -> bool:
    """Determine whether annotations in a module are evaluated at definition time.

    Args:
        module: The parsed module
        python_version: Target ``(major, minor)`` version. Defaults to the
                        running interpreter's version.

    Returns:
        True if annotations are evaluated eagerly and therefore constrain ordering
    """
    if has_future_annotations(module):
        return False

    version = python_version or sys.version_info[:2]
    return version < LAZY_ANNOTATIONS_VERSION


def parse_python_version(value: str) -> tuple[int, int] | None:
    """Parse a Python version out of a version or requirement string.

    Handles plain versions (``"3.12"``, ``"3.12.1"``, ``"py312"``) as well as
    ``requires-python`` style specifiers (``">=3.9,<4"``), in which case the
    lower bound is used -- the oldest supported interpreter is the one that
    determines whether annotations are eager.

    Args:
        value: The version string

    Returns:
        A ``(major, minor)`` tuple, or None if nothing could be parsed
    """
    lower_bound = re.search(r">=?\s*(\d+)\.(\d+)", value)
    if lower_bound:
        return (int(lower_bound.group(1)), int(lower_bound.group(2)))

    compatible = re.search(r"~=\s*(\d+)\.(\d+)", value)
    if compatible:
        return (int(compatible.group(1)), int(compatible.group(2)))

    py_style = re.fullmatch(r"\s*py(\d)(\d+)\s*", value)
    if py_style:
        return (int(py_style.group(1)), int(py_style.group(2)))

    plain = re.search(r"(\d+)\.(\d+)", value)
    if plain:
        return (int(plain.group(1)), int(plain.group(2)))

    return None


def eager_names(node: cst.CSTNode, eager_annotations: bool) -> set[str]:
    """Collect every name a statement references at definition/execution time.

    Args:
        node: The statement to analyse
        eager_annotations: Whether annotations count as eager references

    Returns:
        Set of referenced names
    """
    collector = _EagerNameCollector(eager_annotations)
    node.visit(collector)
    return collector.names


def _dotted_name(node: cst.BaseExpression) -> str:
    """Render a (possibly dotted) name expression as a string.

    Args:
        node: Name or Attribute expression

    Returns:
        The dotted string, or an empty string for other expression types
    """
    if isinstance(node, cst.Name):
        return node.value
    if isinstance(node, cst.Attribute):
        base = _dotted_name(node.value)
        return f"{base}.{node.attr.value}" if base else ""
    return ""


class _EagerNameCollector(cst.CSTVisitor):
    """Visitor collecting names referenced in eagerly evaluated positions."""

    def __init__(self, eager_annotations: bool):
        """Initialize the collector.

        Args:
            eager_annotations: Whether to descend into annotations
        """
        self.names: set[str] = set()
        self.eager_annotations = eager_annotations

    def visit_ConcatenatedString(self, node: cst.ConcatenatedString) -> bool:
        """Walk an implicit string concatenation without recursing per literal.

        Args:
            node: The concatenated string

        Returns:
            False -- parts are visited manually
        """
        # libcst nests each extra literal one level deeper; long chains exceed the recursion limit.
        stack: list[cst.BaseExpression] = [node]
        while stack:
            part = stack.pop()
            if isinstance(part, cst.ConcatenatedString):
                stack.extend((part.right, part.left))
            else:
                part.visit(self)
        return False

    def visit_FunctionDef(self, node: cst.FunctionDef) -> bool:
        """Collect eager references of a function definition, skipping its body.

        Args:
            node: The function definition

        Returns:
            False -- children are visited manually
        """
        for decorator in node.decorators:
            decorator.decorator.visit(self)

        self._visit_parameters(node.params)

        if self.eager_annotations and node.returns is not None:
            node.returns.annotation.visit(self)

        return False

    def visit_ClassDef(self, node: cst.ClassDef) -> bool:
        """Collect eager references of a class definition, including its body.

        Args:
            node: The class definition

        Returns:
            False -- children are visited manually
        """
        for decorator in node.decorators:
            decorator.decorator.visit(self)

        for base in node.bases:
            base.value.visit(self)

        for keyword in node.keywords:
            keyword.value.visit(self)

        # A class body executes eagerly when the class is created.
        node.body.visit(self)

        return False

    def visit_Annotation(self, node: cst.Annotation) -> bool:
        """Descend into an annotation only when annotations are eager.

        Args:
            node: The annotation

        Returns:
            True if annotations are evaluated at definition time
        """
        return self.eager_annotations

    def visit_Attribute(self, node: cst.Attribute) -> bool:
        """Visit only the base of an attribute access, never the attribute name.

        Args:
            node: The attribute expression

        Returns:
            False -- the base is visited manually
        """
        node.value.visit(self)
        return False

    def visit_Arg(self, node: cst.Arg) -> bool:
        """Visit an argument's value but not its keyword name.

        Args:
            node: The call argument

        Returns:
            False -- the value is visited manually
        """
        node.value.visit(self)
        return False

    def visit_Name(self, node: cst.Name) -> None:
        """Record a referenced name.

        Args:
            node: The name node
        """
        self.names.add(node.value)

    def _visit_parameters(self, params: cst.Parameters) -> None:
        """Collect eager references from a parameter list.

        Args:
            params: The parameter list
        """
        all_params = [
            *params.posonly_params,
            *params.params,
            *params.kwonly_params,
        ]
        for star in (params.star_arg, params.star_kwarg):
            if isinstance(star, cst.Param):
                all_params.append(star)

        for param in all_params:
            if param.default is not None:
                param.default.visit(self)
            if self.eager_annotations and param.annotation is not None:
                param.annotation.annotation.visit(self)
