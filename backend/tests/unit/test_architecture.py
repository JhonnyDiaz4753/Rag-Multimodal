"""Tests de arquitectura: el dominio y los puertos no dependen de terceros."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
SRC_DIR = BACKEND_DIR / "src"
DOMAIN_DIR = SRC_DIR / "domain"
PORTS_DIR = SRC_DIR / "application" / "ports"

STDLIB = frozenset(sys.stdlib_module_names)


def _python_files(directory: Path) -> list[Path]:
    return sorted(path for path in directory.rglob("*.py") if "__pycache__" not in path.parts)


def _imported_modules(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                raise AssertionError(
                    f"{path.relative_to(BACKEND_DIR)} usa un import relativo; usa imports absolutos"
                )
            if node.module:
                modules.append(node.module)
    return modules


def _assert_allowed_imports(path: Path, allowed_prefixes: tuple[str, ...]) -> None:
    for module in _imported_modules(path):
        if module.split(".")[0] in STDLIB:
            continue
        if any(module == prefix or module.startswith(f"{prefix}.") for prefix in allowed_prefixes):
            continue
        raise AssertionError(
            f"{path.relative_to(BACKEND_DIR)} importa '{module}', que no está permitido"
        )


def test_domain_only_imports_the_standard_library() -> None:
    files = _python_files(DOMAIN_DIR)
    assert files

    for path in files:
        _assert_allowed_imports(path, ("src.domain",))


def test_ports_only_depend_on_domain_and_the_standard_library() -> None:
    files = _python_files(PORTS_DIR)
    assert files

    for path in files:
        _assert_allowed_imports(path, ("src.domain", "src.application.ports"))
