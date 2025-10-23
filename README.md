# undersort

A Python tool that automatically sorts class methods by visibility (public, protected, private) and type (class, static, instance).

## Features

- Automatically reorders class methods based on visibility and method type
- Two-level sorting: primary by visibility, secondary by method type
- Fully configurable ordering via `pyproject.toml`
- Pre-commit hook integration
- Colored output for better readability
- Check mode for CI/CD validation
- Diff mode to preview changes

## Installation

```bash
# Using uv (recommended)
uv add undersort

# Using pip
pip install undersort

# For development
git clone https://github.com/kivicode/undersort
cd undersort
uv sync
```

## Configuration

Configure the method ordering in your `pyproject.toml`:

```toml
[tool.undersort]
# Method visibility ordering (primary sort)
# Options: "public", "protected", "private"
order = ["public", "protected", "private"]

# Method type ordering within each visibility level (secondary sort, optional)
# Options: "class" (classmethod), "static" (staticmethod), "instance" (regular methods)
# Default: ["instance", "class", "static"]
method_type_order = ["instance", "class", "static"]
```

### Method Visibility Rules

- **Public methods**: No underscore prefix (e.g., `def method()`) or magic methods (e.g., `__init__`, `__str__`)
- **Protected methods**: Single underscore prefix (e.g., `def _method()`)
- **Private methods**: Double underscore prefix, not magic (e.g., `def __method()`)

### Method Type Rules

- **Class methods**: Decorated with `@classmethod`
- **Static methods**: Decorated with `@staticmethod`
- **Instance methods**: Regular methods (no special decorator)

### Sorting Behavior

Methods are sorted in two levels:

1. **Primary**: By visibility (public → protected → private)
2. **Secondary**: Within each visibility level, by method type (instance → class → static by default)

The sorting algorithm **minimizes movement** to preserve the original order as much as possible:

- Methods that need to move DOWN (to a later section) are placed at the **beginning** of their target section
- Methods that need to move UP (to an earlier section) are placed at the **end** of their target section
- Methods already in the correct section maintain their relative order

Example order with default configuration:

1. Public instance methods
2. Public class methods
3. Public static methods
4. Protected instance methods
5. Protected class methods
6. Protected static methods
7. Private instance methods
8. Private class methods
9. Private static methods

### Skipping Sorting with `# nosort`

You can prevent sorting at different levels using `# nosort` comments (case-insensitive):

**File-level**: Skip entire file

```python
# nosort: file
class Example:
    def _protected(self):
        pass
    def public(self):
        pass  # File won't be sorted
```

**Class-level**: Skip specific class

```python
class Example:  # nosort
    def _protected(self):
        pass
    def public(self):
        pass  # This class won't be sorted

class Other:
    def _protected(self):
        pass
    def public(self):
        pass  # This class WILL be sorted
```

**Method-level**: Keep method in its current position

```python
class Example:
    def public_a(self):
        pass

    def _protected(self):  # nosort
        pass  # Stays here, between public methods

    def public_b(self):
        pass  # Will move up, but _protected stays in place
```

## Usage

### Command Line

```bash
# Sort a single file
undersort example.py

# Sort multiple files
undersort file1.py file2.py file3.py

# Sort all Python files in a directory (recursive by default)
undersort src/

# Sort all Python files in current directory and subdirectories
undersort .

# Non-recursive directory sorting (only files in the directory, not subdirectories)
undersort src/ --no-recursive

# Wildcards work too (expanded by shell)
undersort *.py
undersort src/**/*.py

# Check if files need sorting (useful for CI)
undersort --check example.py
undersort --check src/

# Show diff of changes
undersort --diff example.py

# Combine flags
undersort --check --diff src/
```

**Note**: By default, undersort excludes all dot-prefixed directories (e.g., `.venv`, `.git`, `.pytest_cache`) and common build directories (`venv`, `__pycache__`, `node_modules`) when scanning directories recursively.

### Pre-commit Integration

Add to your `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: local
    hooks:
      - id: undersort
        name: undersort
        entry: undersort
        language: python
        types: [python]
        additional_dependencies: ["undersort"]
```

Then install the hook:

```bash
pip install pre-commit
pre-commit install
```

## Example

### Before

```python
class Example:
    def _protected_instance(self):
        pass

    @staticmethod
    def public_static():
        pass

    def __init__(self):
        pass

    @classmethod
    def _protected_class(cls):
        pass

    def public_instance(self):
        pass

    def __private_method(self):
        pass

    @classmethod
    def public_class(cls):
        pass
```

### After (with default config)

```python
class Example:
    def __init__(self):
        pass

    def public_instance(self):
        pass

    @classmethod
    def public_class(cls):
        pass

    @staticmethod
    def public_static():
        pass

    def _protected_instance(self):
        pass

    @classmethod
    def _protected_class(cls):
        pass

    def __private_method(self):
        pass
```

The methods are now organized by:

1. **Visibility**: public (including `__init__`) → protected → private
2. **Type** (within each visibility): instance → class → static

## Development

```bash
# Install dependencies
uv sync

# Run on example file
uv run undersort example.py

# Test with check mode
uv run undersort --check example.py

# View diff
uv run undersort --diff example.py
```

## License

MIT
