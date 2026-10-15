"""Lightweight package entry: application startup is owned by the CLI."""

import os
from typing import Any

JESSE_DIR = os.path.dirname(os.path.abspath(__file__))


def __getattr__(name: str) -> Any:
    """Preserve public entry names without initializing routes or database models."""
    if name == 'cli':
        from jesse.cli import cli
        # Importing a submodule sets the package attribute to the module first.
        # Cache the callable so repeated `from jesse import cli` stays compatible.
        globals()['cli'] = cli
        return cli
    if name == 'fastapi_app':
        from jesse.app import fastapi_app
        return fastapi_app
    raise AttributeError(f'module {__name__!r} has no attribute {name!r}')
