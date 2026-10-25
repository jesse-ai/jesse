"""
The code a queued research job carries to its runner (see services/runner_queue.py).

A bundle is every file the job's strategies need, read from the hub's project when the job is
queued:
- the whole folder of each route's strategy (all of its files, data files such as models too),
- every other strategy folder those files import (`from strategies.Base import ...`),
- every project-level module or package they import (a `custom_indicators/` folder, say),
followed recursively. Third-party packages are not bundled; their import names are listed so a
runner without them can refuse the job.

Each file is stored once in CodeBlob by the SHA-256 of its content, and a job keeps only a
manifest {relative path: hash}. A runner writes the files into the job's own folder; it never
touches its project's strategies/ folder.
"""

import ast
import hashlib
import os
import sys
from typing import Iterable

MAX_BUNDLE_BYTES = 100 * 1024 * 1024
_SKIPPED_DIRS = {'__pycache__', '.git', '.ipynb_checkpoints', 'node_modules'}
_SKIPPED_SUFFIXES = ('.pyc', '.pyo')
_NOT_THIRD_PARTY = {'jesse', 'jesse_rust', 'jesse_live', '__future__'}
_PROJECT_ROOTS_NOT_CODE = {'strategies', 'storage', 'research_scripts'}


class BundleError(Exception):
    pass


def _stdlib_names() -> set:
    return set(getattr(sys, 'stdlib_module_names', ())) | set(sys.builtin_module_names)


def _files_under(path: str) -> list:
    if os.path.isfile(path):
        return [path]
    found = []
    for root, dirs, files in os.walk(path):
        dirs[:] = sorted(d for d in dirs if d not in _SKIPPED_DIRS and not d.startswith('.'))
        for name in sorted(files):
            if name.startswith('.') or name.endswith(_SKIPPED_SUFFIXES):
                continue
            found.append(os.path.join(root, name))
    return found


def _imports(source: str, filename: str) -> list:
    """(top-level name, second part) for every absolute import in a Python file."""
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError as e:
        raise BundleError(f'{filename} has a syntax error (line {e.lineno}); fix it before queuing.')
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                parts = alias.name.split('.')
                found.append((parts[0], parts[1] if len(parts) > 1 else None))
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            parts = node.module.split('.')
            if len(parts) > 1:
                found.append((parts[0], parts[1]))
            else:
                # `from strategies import Base` names the folder in the imported names.
                for alias in node.names:
                    found.append((parts[0], alias.name))
    return found


def build(strategy_names: Iterable[str], project_root: str = '.') -> dict:
    """
    Collect the files of these strategies and of everything they import from the project.
    Returns {'files': {relative path: bytes}, 'packages': [import names], 'size': bytes}.
    """
    root = os.path.abspath(project_root)
    stdlib = _stdlib_names()
    files = {}
    packages = set()
    pending = [os.path.join('strategies', name) for name in dict.fromkeys(strategy_names)]
    seen = set()

    while pending:
        relative = pending.pop()
        if relative in seen:
            continue
        seen.add(relative)
        absolute = os.path.join(root, relative)
        if not os.path.exists(absolute):
            if relative.startswith('strategies' + os.sep):
                raise BundleError(f'Strategy "{relative.split(os.sep, 1)[1]}" was not found in {root}/strategies.')
            continue
        for path in _files_under(absolute):
            # Bundles move between machines, so their paths always use "/" (also on Windows).
            relative_path = os.path.relpath(path, root).replace(os.sep, '/')
            if relative_path in files:
                continue
            with open(path, 'rb') as f:
                files[relative_path] = f.read()
            if not path.endswith('.py'):
                continue
            for top, second in _imports(files[relative_path].decode('utf-8', 'replace'), relative_path):
                if top == 'strategies':
                    if second:
                        pending.append(os.path.join('strategies', second))
                elif top in _NOT_THIRD_PARTY or top in stdlib:
                    continue
                elif top not in _PROJECT_ROOTS_NOT_CODE and (
                    os.path.isdir(os.path.join(root, top)) or os.path.isfile(os.path.join(root, f'{top}.py'))
                ):
                    pending.append(top if os.path.isdir(os.path.join(root, top)) else f'{top}.py')
                else:
                    packages.add(top)

    size = sum(len(content) for content in files.values())
    if size > MAX_BUNDLE_BYTES:
        largest = max(files, key=lambda p: len(files[p]))
        raise BundleError(
            f'The job\'s files total {size / 1024 / 1024:.0f} MB, above the {MAX_BUNDLE_BYTES // 1024 // 1024} MB '
            f'limit (largest: {largest}). Move large data out of the strategy folders.'
        )
    return {'files': files, 'packages': sorted(packages), 'size': size}


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def store(bundle: dict, now_ms: int) -> dict:
    """Save each file once in CodeBlob; returns the manifest {relative path: hash}."""
    from jesse.models.RunnerJob import CodeBlob

    manifest = {}
    for path, content in bundle['files'].items():
        file_hash = digest(content)
        manifest[path.replace(os.sep, '/')] = file_hash
        updated = CodeBlob.update(last_used_at=now_ms).where(CodeBlob.hash == file_hash).execute()
        if not updated:
            CodeBlob.insert(hash=file_hash, content=content, size=len(content), created_at=now_ms,
                            last_used_at=now_ms).on_conflict_ignore().execute()
    return manifest


def materialize(manifest: dict, destination: str, cache_dir: str) -> None:
    """Write the manifest's files under `destination`, keeping a local copy of each by hash."""
    from jesse.models.RunnerJob import CodeBlob

    os.makedirs(cache_dir, exist_ok=True)
    missing = [h for h in set(manifest.values()) if not os.path.exists(os.path.join(cache_dir, h))]
    if missing:
        for blob in CodeBlob.select().where(CodeBlob.hash.in_(missing)):
            content = bytes(blob.content)
            if digest(content) != blob.hash:
                raise BundleError(f'A stored file does not match its hash ({blob.hash[:12]}).')
            temporary = os.path.join(cache_dir, f'{blob.hash}.part')
            with open(temporary, 'wb') as f:
                f.write(content)
            os.replace(temporary, os.path.join(cache_dir, blob.hash))
    for relative_path, file_hash in manifest.items():
        source = os.path.join(cache_dir, file_hash)
        if not os.path.exists(source):
            raise BundleError(f'The file {relative_path} of this job is no longer stored.')
        target = os.path.join(destination, *relative_path.split('/'))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(source, 'rb') as src, open(target, 'wb') as dst:
            dst.write(src.read())
