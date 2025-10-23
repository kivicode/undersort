"""Logging configuration for undersort."""

from rich.console import Console
from rich.syntax import Syntax

console = Console()


def info(message: str) -> None:
    """Log an info message."""
    console.print(f"[blue][INFO][/blue] {message}")


def success(message: str) -> None:
    """Log a success message."""
    console.print(f"[green][OK][/green] {message}")


def warning(message: str) -> None:
    """Log a warning message."""
    console.print(f"[yellow][WARNING][/yellow] {message}", highlight=False)


def error(message: str) -> None:
    """Log an error message."""
    console.print(f"[red][ERROR][/red] {message}", highlight=False)


def diff(content: str) -> None:
    """Print a diff with syntax highlighting."""
    syntax = Syntax(content, "diff", theme="monokai", line_numbers=False)
    console.print(syntax)
