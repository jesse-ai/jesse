"""
Temporary analysis jobs: assistant-written Python that analyzes stored session results.

A job lives in its own workspace, storage/mcp/analysis/<job_id>/:

    analysis.py     the submitted code, run as `<this Python> analysis.py` from the workspace
    inputs/         snapshots of the requested sessions (<name>.json) plus manifest.json
    output/         files the code writes (charts, tables); the only place artifacts are served from
    job.json        the job record
    console.txt     combined stdout/stderr (capped)

This is separate from research_scripts/: nothing is written into the project's own folders.
Cleanup is lazy, with no timer: every new analysis first deletes workspaces whose job
finished more than RETENTION_HOURS ago, then the oldest beyond the MAX_KEPT_JOBS /
MAX_STORAGE_BYTES caps. A workspace therefore outlives its expiry until the next analysis
starts. Jobs this Jesse process is running or still preparing are never deleted.
Process management, limits on output, cancel, timeouts, and shutdown behavior are shared
with research jobs (jesse.services.research_jobs) under a separate concurrency limit.

Snapshots are written by Jesse from the database, so large result arrays never pass through
the assistant: one stored session each (jesse.services.session_results), or the live/paper
trades or orders of a date window across sessions (jesse.services.live_history), streamed to
disk one batch at a time.

The code is NOT sandboxed: it runs as the Jesse user with Jesse's environment, filesystem,
database, and network access. The workspace layout and the artifact path checks below only
decide which files Jesse serves back; they do not limit what the code can do. After a Jesse
crash, a job's process may outlive its record; cleanup treats that record as finished, so
the workspace can be deleted while the orphaned process still runs.
"""
import base64
import io
import json
import os
import re
import stat
import sys
import threading
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence, Set, Tuple
from uuid import uuid4

from jesse.services import live_history, research_jobs, session_results
from jesse.services.project_files import ProjectFileError

ANALYSIS_ROOT = os.path.join('storage', 'mcp', 'analysis')
CODE_FILE = 'analysis.py'
INPUTS_DIR = 'inputs'
OUTPUT_DIR = 'output'
RECORD_FILE = 'job.json'
CONSOLE_FILE = 'console.txt'
MANIFEST_FILE = 'manifest.json'

# Analyses are short numeric jobs (pandas/numpy/matplotlib over a few snapshots). Two at a
# time keeps them from competing with backtests; this limit is separate from research jobs.
MAX_CONCURRENT_ANALYSIS_JOBS = 2
# Reading a few snapshots and drawing charts takes seconds; the ceiling allows heavier
# statistics (bootstraps over long live histories) without letting a stuck job linger.
DEFAULT_TIMEOUT_MINUTES = 5
MAX_TIMEOUT_MINUTES = 30
# Analysis code is written by the assistant for one question; 256 KiB is far above that.
MAX_CODE_BYTES = 256 * 1024
MAX_INPUTS = 10
# One Monte Carlo session with a few hundred scenarios and their equity curves is typically
# a few to a few tens of MiB; these caps stop a single job from copying gigabytes.
MAX_INPUT_BYTES = 64 * 1024 * 1024
MAX_TOTAL_INPUT_BYTES = 256 * 1024 * 1024
# Analysis output should be results and summaries, not bulk data.
MAX_LOG_BYTES = 5 * 1024 * 1024
# Lifetime and disk caps for workspaces. A finished job's artifacts can be fetched for a day;
# beyond the count or byte caps the oldest finished workspaces are removed first.
RETENTION_HOURS = 24
MAX_KEPT_JOBS = 50
MAX_STORAGE_BYTES = 2 * 1024 * 1024 * 1024
# A workspace without a record is a job whose preparation failed or crashed; after an hour
# it cannot still be in preparation.
ORPHAN_WORKSPACE_SECONDS = 60 * 60
# Artifact listing and retrieval bounds.
MAX_ARTIFACTS_LISTED = 200
# Images are returned as MCP image content, base64-encoded. 3 MiB of image becomes 4 MiB of
# base64, under the ~5 MB per-image limit common to assistant clients and model APIs.
MAX_IMAGE_BYTES = 3 * 1024 * 1024
# Model APIs reject images larger than 8000 px on a side.
MAX_IMAGE_DIMENSION = 8000
# Text artifacts (CSV, JSON, Markdown) are returned up to this many characters.
MAX_TEXT_ARTIFACT_CHARS = 128 * 1024
LIST_LIMIT = 20

_NAME = re.compile(r'[A-Za-z0-9_-]{1,64}')
_DIR_FLAGS = os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0) | getattr(os, 'O_NOFOLLOW', 0)
_FILE_READ_FLAGS = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
_FILE_CREATE_FLAGS = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0)

IMAGE_FORMATS = ('image/png', 'image/jpeg', 'image/gif', 'image/webp')


def _error(error_type: str, message: str, status_code: int) -> ProjectFileError:
    return ProjectFileError(error_type, message, status_code)


def _workspace_path(job_id: str, *parts: str) -> str:
    return os.path.join(ANALYSIS_ROOT, job_id, *parts)


def _write_analysis_record(record: dict) -> None:
    research_jobs.write_record_file(record, _workspace_path(record['id'], RECORD_FILE))


ANALYSIS = research_jobs.JobScope(
    name='analysis',
    label='analysis job',
    max_concurrent=lambda: MAX_CONCURRENT_ANALYSIS_JOBS,
    max_log_bytes=lambda: MAX_LOG_BYTES,
    record_path=lambda job_id: _workspace_path(job_id, RECORD_FILE),
    log_path=lambda job_id: _workspace_path(job_id, CONSOLE_FILE),
    write_record=lambda record: _write_analysis_record(record),
    id_hint='the 32-character ID returned by run_analysis',
)

# Jobs between workspace creation and process start; cleanup never touches them.
_preparing: Set[str] = set()
# Serializes workspace creation, deletion, and cleanup decisions.
_workspace_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Workspace file access (never follows symlinks below the analysis root)
# ---------------------------------------------------------------------------

def _open_root(create: bool = False) -> int:
    """
    Open storage/mcp/analysis. The root itself is part of Jesse's own storage folder and is
    opened normally; every path below it is opened with O_NOFOLLOW.
    """
    if create:
        os.makedirs(ANALYSIS_ROOT, exist_ok=True)
    try:
        return os.open(ANALYSIS_ROOT, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
    except FileNotFoundError:
        raise _error('not_found', 'No analysis job exists yet.', 404)


def _open_dir(dir_fd: int, name: str, missing_message: str) -> int:
    try:
        return os.open(name, _DIR_FLAGS, dir_fd=dir_fd)
    except FileNotFoundError:
        raise _error('not_found', missing_message, 404)
    except OSError:
        st = _lstat(dir_fd, name)
        if st is not None and stat.S_ISLNK(st.st_mode):
            raise _error('unsafe_path', f'{name} is a symlink; analysis files are never read through symlinks.', 403)
        raise _error('wrong_type', f'{name} is not a folder.', 409)


def _lstat(dir_fd: int, name: str) -> Optional[os.stat_result]:
    try:
        return os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None


def _gone_message(job_id: str) -> str:
    return (f'Analysis job {job_id} does not exist or was cleaned up. Workspaces are deleted once '
            f'{RETENTION_HOURS} hours have passed since the job finished (when a later analysis starts); '
            'rerun the analysis to recreate its files.')


def _open_workspace(job_id: str) -> int:
    root = _open_root()
    try:
        return _open_dir(root, job_id, _gone_message(job_id))
    finally:
        os.close(root)


def _write_new_file(dir_fd: int, name: str, chunks, cap: int, label: str) -> int:
    """Create `name` exclusively and write chunks, refusing with too_large past `cap` bytes."""
    fd = os.open(name, _FILE_CREATE_FLAGS, 0o600, dir_fd=dir_fd)
    written = 0
    try:
        with os.fdopen(fd, 'wb') as f:
            for chunk in chunks:
                data = chunk.encode('utf-8') if isinstance(chunk, str) else chunk
                written += len(data)
                if written > cap:
                    raise _error('too_large', f'{label} is larger than {cap // (1024 * 1024)} MiB.', 413)
                f.write(data)
    except BaseException:
        try:
            os.unlink(name, dir_fd=dir_fd)
        except OSError:
            pass
        raise
    return written


def _remove_tree(dir_fd: int, name: str) -> None:
    """Delete a folder and everything in it; symlinks are unlinked, never followed."""
    try:
        sub = os.open(name, _DIR_FLAGS, dir_fd=dir_fd)
    except FileNotFoundError:
        return
    try:
        with os.scandir(sub) as entries:
            children = list(entries)
        for child in children:
            if child.is_dir(follow_symlinks=False):
                _remove_tree(sub, child.name)
            else:
                try:
                    os.unlink(child.name, dir_fd=sub)
                except FileNotFoundError:
                    pass
    finally:
        os.close(sub)
    try:
        os.rmdir(name, dir_fd=dir_fd)
    except FileNotFoundError:
        pass


def _tree_size(dir_fd: int, name: str) -> int:
    """Bytes used by regular files below a folder, without following symlinks."""
    try:
        sub = os.open(name, _DIR_FLAGS, dir_fd=dir_fd)
    except OSError:
        return 0
    total = 0
    try:
        with os.scandir(sub) as entries:
            for entry in entries:
                try:
                    st = entry.stat(follow_symlinks=False)
                except OSError:
                    continue
                if stat.S_ISDIR(st.st_mode):
                    total += _tree_size(sub, entry.name)
                elif stat.S_ISREG(st.st_mode):
                    total += st.st_size
    finally:
        os.close(sub)
    return total


def _remove_trash(root_fd: int, name: str) -> None:
    """
    Best-effort removal of a renamed-away workspace. Whatever cannot be removed now (a folder
    the analysis code made unwritable, nesting deeper than Python's recursion limit) stays
    under its .trash- name and is retried by the next cleanup, so it can never make later
    runs or deletions fail.
    """
    try:
        _remove_tree(root_fd, name)
    except (OSError, RecursionError):
        pass


def _discard(root_fd: int, job_id: str) -> None:
    """
    Remove a workspace: first rename it to a hidden trash name (atomic, so it disappears for
    every later lookup at once), then delete the renamed tree. Files a reader already opened
    stay readable until closed.
    """
    trash = f'.trash-{job_id}-{uuid4().hex}'
    try:
        os.rename(job_id, trash, src_dir_fd=root_fd, dst_dir_fd=root_fd)
    except FileNotFoundError:
        return
    _remove_trash(root_fd, trash)


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

def _iso_to_epoch(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).timestamp()
    except (TypeError, ValueError):
        return None


def _expires_at(record: dict) -> Optional[str]:
    finished = _iso_to_epoch(record.get('finished_at'))
    if finished is None or record.get('status') == research_jobs.RUNNING:
        return None
    return datetime.fromtimestamp(finished + RETENTION_HOURS * 3600, timezone.utc).isoformat(timespec='seconds')


def cleanup_workspaces(now: Optional[float] = None) -> List[str]:
    """
    Delete expired and excess workspaces and return their job IDs.

    Called when an analysis starts (there is no timer). Never deletes a job that this
    process is running or still preparing. Anything else counts as finished, including a
    record left "running" by a previous Jesse process (at its finish time once a status read
    marked it interrupted, otherwise at its start time), even though after a crash its
    orphaned process may still be running. Failures are skipped, never raised, so one bad
    workspace cannot block new analyses.
    """
    now = time.time() if now is None else now
    removed: List[str] = []

    def discard(root_fd: int, name: str) -> None:
        try:
            _discard(root_fd, name)
        except OSError:
            return  # Could not rename it away (e.g. permissions); retried next time.
        removed.append(name)

    with _workspace_lock:
        if not os.path.isdir(ANALYSIS_ROOT):
            return removed
        protected = research_jobs.running_job_ids(ANALYSIS) | _preparing
        root = _open_root()
        try:
            candidates: List[Tuple[float, str]] = []
            for entry in os.scandir(root):
                name = entry.name
                if name.startswith('.trash-'):
                    _remove_trash(root, name)  # Left over from an interrupted or failed deletion.
                    continue
                if not research_jobs.JOB_ID_PATTERN.fullmatch(name) or name in protected:
                    continue
                try:
                    st = entry.stat(follow_symlinks=False)
                except OSError:
                    continue
                if not stat.S_ISDIR(st.st_mode):
                    continue
                try:
                    record = research_jobs.read_record_file(_workspace_path(name, RECORD_FILE), ANALYSIS.label, name)
                except ProjectFileError:
                    record = None
                if record is None:
                    if now - st.st_mtime > ORPHAN_WORKSPACE_SECONDS:
                        discard(root, name)
                    continue
                finished = (_iso_to_epoch(record.get('finished_at')) or _iso_to_epoch(record.get('started_at'))
                            or st.st_mtime)
                if now - finished > RETENTION_HOURS * 3600:
                    discard(root, name)
                else:
                    candidates.append((finished, name))

            candidates.sort(reverse=True)
            kept = []
            for index, (_finished, name) in enumerate(candidates):
                if index >= MAX_KEPT_JOBS:
                    discard(root, name)
                else:
                    kept.append(name)
            sizes = {name: _tree_size(root, name) for name in kept}
            total = sum(sizes.values()) + sum(_tree_size(root, name) for name in protected
                                              if research_jobs.JOB_ID_PATTERN.fullmatch(name))
            for name in reversed(kept):  # Oldest first.
                if total <= MAX_STORAGE_BYTES:
                    break
                discard(root, name)
                total -= sizes[name]
        finally:
            os.close(root)
    return removed


# ---------------------------------------------------------------------------
# Running
# ---------------------------------------------------------------------------

def _validate_inputs(inputs: object) -> List[dict]:
    """
    Validate the inputs. Each is a stored session ({"session_type", "session_id", "name"}) or a
    live history dataset ({"dataset": "live_trades" | "live_orders", "name", window and
    filters}); a dataset's window is resolved here, once, and recorded in the manifest.
    """
    if inputs is None:
        return []
    if not isinstance(inputs, list):
        raise _error('invalid_request', 'inputs must be a list of {"session_type", "session_id", "name"} or '
                     '{"dataset", "name", ...} objects.', 400)
    if len(inputs) > MAX_INPUTS:
        raise _error('invalid_request', f'At most {MAX_INPUTS} inputs are allowed.', 400)
    validated = []
    names = set()
    for item in inputs:
        if not isinstance(item, dict):
            raise _error('invalid_request', 'Each input must be an object with session_type and session_id, or with dataset.', 400)
        if item.get('dataset') is not None:
            query = live_history.validate_dataset_input(item)
            entry = {'dataset': query['dataset'], 'query': query}
            default_name = query['dataset']
        else:
            session_type, session_id = item.get('session_type'), item.get('session_id')
            if session_type not in session_results.SESSION_TYPES:
                raise _error('invalid_request', f'session_type must be one of: {", ".join(session_results.SESSION_TYPES)} '
                             f'(or use "dataset": {" or ".join(live_history.DATASETS)}).', 400)
            if not isinstance(session_id, str):
                raise _error('invalid_request', 'session_id must be a session UUID.', 400)
            entry = {'session_type': session_type, 'session_id': session_id}
            default_name = f'{session_type}_{session_id.replace("-", "")[:8]}'
        name = item.get('name') or default_name
        if not isinstance(name, str) or not _NAME.fullmatch(name) or name == 'manifest':
            raise _error('invalid_request', 'Input names use 1-64 letters, digits, "_" or "-" (and cannot be "manifest").', 400)
        if name in names:
            raise _error('invalid_request', f'Input name "{name}" is used twice.', 400)
        names.add(name)
        validated.append({**entry, 'name': name})
    return validated


def _write_inputs(workspace_fd: int, inputs: List[dict]) -> List[dict]:
    """Export each session or dataset and write its snapshot; returns the manifest entries."""
    inputs_fd = _open_dir(workspace_fd, INPUTS_DIR, 'The inputs folder is missing.')
    manifest = []
    total = 0
    try:
        for item in inputs:
            file_name = f'{item["name"]}.json'
            if 'dataset' in item:
                # Streamed batch by batch, so a large window never sits in memory as one object.
                stats: Dict[str, int] = {}
                chunks = live_history.iter_dataset_json(item['query'], stats)
                try:
                    size = _write_new_file(inputs_fd, file_name, chunks, MAX_INPUT_BYTES, f'The {item["dataset"]} snapshot')
                finally:
                    # Ends the snapshot's read transaction at once when writing stopped early
                    # (byte cap, disk error), instead of whenever the generator is collected.
                    chunks.close()
                entry = {'name': item['name'], 'file': f'{INPUTS_DIR}/{file_name}', 'dataset': item['dataset'],
                         **live_history.public_query(item['query']), 'count': stats.get('count'), 'size_bytes': size}
            else:
                data = session_results.export_session(item['session_type'], item['session_id'])
                encoder = json.JSONEncoder(default=str, separators=(',', ':'))
                size = _write_new_file(inputs_fd, file_name, encoder.iterencode(data), MAX_INPUT_BYTES,
                                       f'The snapshot of {item["session_type"]} session {item["session_id"]}')
                summary = data.get('summary') or {}
                entry = {
                    'name': item['name'],
                    'file': f'{INPUTS_DIR}/{file_name}',
                    'session_type': item['session_type'],
                    'session_id': summary.get('session_id', item['session_id']),
                    'session_status': summary.get('session_status'),
                    'title': summary.get('title'),
                    'size_bytes': size,
                }
            total += size
            if total > MAX_TOTAL_INPUT_BYTES:
                raise _error('too_large', f'All inputs together are larger than {MAX_TOTAL_INPUT_BYTES // (1024 * 1024)} MiB.', 413)
            manifest.append(entry)
        _write_new_file(inputs_fd, MANIFEST_FILE, [json.dumps(manifest, indent=2)], MAX_INPUT_BYTES, 'The manifest')
    finally:
        os.close(inputs_fd)
    return manifest


def start_analysis(code: str, inputs: Optional[list] = None, timeout_minutes: int = DEFAULT_TIMEOUT_MINUTES) -> dict:
    """
    Snapshot the requested sessions into a new workspace and start the code in the background.

    Returns the job record immediately; poll get_job for status, output, and artifacts.
    """
    if not isinstance(code, str) or not code.strip():
        raise _error('invalid_request', 'code must be the Python source to run.', 400)
    code_bytes = code.encode('utf-8')
    if len(code_bytes) > MAX_CODE_BYTES:
        raise _error('too_large', f'code is limited to {MAX_CODE_BYTES // 1024} KiB.', 413)
    research_jobs.validate_timeout(timeout_minutes, MAX_TIMEOUT_MINUTES)
    validated = _validate_inputs(inputs)
    job_id = _reserve_slot()
    # From here on the reservation is released in `finally`, whatever fails.
    try:
        try:
            cleanup_workspaces()
        except (OSError, RecursionError):
            pass  # Cleanup is best-effort and retried by the next run; it must not block this one.
        with _workspace_lock:
            try:
                root = _open_root(create=True)
                try:
                    os.mkdir(job_id, 0o700, dir_fd=root)
                finally:
                    os.close(root)
            except OSError as exc:
                raise _error('io_error', f'Could not create the analysis workspace: {exc.strerror or exc}.', 500)
        record = _prepare_and_launch(job_id, validated, code_bytes, timeout_minutes)
    finally:
        with _workspace_lock:
            _preparing.discard(job_id)
    return _public(record)


def _reserve_slot() -> str:
    """
    Reserve one of the MAX_CONCURRENT_ANALYSIS_JOBS slots for a new job and return its ID.

    Jobs being prepared count as well as running ones, so concurrent calls cannot each write up
    to MAX_TOTAL_INPUT_BYTES of snapshots only for all but two to be refused at launch. The
    union of both sets counts a job once while it moves from preparing to running (launch
    registers it as running before start_analysis releases the reservation). Lock order is
    _workspace_lock, then research_jobs' job lock, as everywhere in this module.
    """
    with _workspace_lock:
        busy = research_jobs.running_job_ids(ANALYSIS) | _preparing
        if len(busy) >= MAX_CONCURRENT_ANALYSIS_JOBS:
            raise _error('too_many_jobs', f'{len(busy)} analysis jobs are already running or being prepared (limit '
                         f'{MAX_CONCURRENT_ANALYSIS_JOBS}). Wait for one to finish or cancel it first.', 429)
        job_id = uuid4().hex
        _preparing.add(job_id)
    return job_id


def _prepare_and_launch(job_id: str, validated: List[dict], code_bytes: bytes, timeout_minutes: int) -> dict:
    """
    Write the snapshots and code into the created workspace and start the job, returning its
    launch record; a failure removes the workspace.
    """
    try:
        workspace = _open_workspace(job_id)
        try:
            os.mkdir(INPUTS_DIR, 0o700, dir_fd=workspace)
            os.mkdir(OUTPUT_DIR, 0o700, dir_fd=workspace)
            manifest = _write_inputs(workspace, validated)
            _write_new_file(workspace, CODE_FILE, [code_bytes], MAX_CODE_BYTES, 'code')
        except OSError as exc:
            # A local disk problem (e.g. a full disk), not a session read failure.
            raise _error('io_error', f'Could not prepare the analysis workspace: {exc.strerror or exc}.', 500)
        finally:
            os.close(workspace)
        return research_jobs.launch(
            ANALYSIS,
            job_id,
            [sys.executable, CODE_FILE],
            os.path.abspath(_workspace_path(job_id)),
            {
                'kind': 'analysis',
                'workspace': _workspace_path(job_id).replace(os.sep, '/'),
                'inputs': manifest,
            },
            timeout_minutes,
            # Charts render to files only; there is no display on a server.
            {'MPLBACKEND': 'Agg'},
        )
    except BaseException:
        with _workspace_lock:
            root = _open_root()
            try:
                if job_id not in research_jobs.running_job_ids(ANALYSIS):
                    _discard(root, job_id)
            finally:
                os.close(root)
        raise


def _public(record: dict) -> dict:
    result = dict(record)
    result.pop('log_path', None)
    expires = _expires_at(result)
    result['expires_at'] = expires
    # expires_at is the earliest deletion time: cleanup runs only when a new analysis starts.
    result['lifetime'] = (f'Deleted when a later analysis starts, once {RETENTION_HOURS} hours have passed since it '
                          f'finished (expires_at), or earlier when finished jobs exceed the {MAX_KEPT_JOBS}-job or '
                          f'{MAX_STORAGE_BYTES // 1024 ** 3} GiB caps (oldest first).')
    return result


# ---------------------------------------------------------------------------
# Status, output, artifacts
# ---------------------------------------------------------------------------

def get_job(job_id: str, tail_lines: int = 50) -> dict:
    """A job's record, its artifacts, and the end of its console output."""
    research_jobs.check_job_id(job_id, ANALYSIS)
    try:
        record = research_jobs.get_scoped_job(job_id, ANALYSIS)
    except ProjectFileError as exc:
        if exc.error_type == 'not_found':
            raise _error('not_found', _gone_message(job_id), 404)
        raise
    output = research_jobs.read_scoped_output(job_id, tail_lines, ANALYSIS)
    try:
        artifacts = list_artifacts(job_id)
    except ProjectFileError as exc:
        if exc.error_type != 'not_found':
            raise
        artifacts = {'artifacts': [], 'truncated': False}
    return {
        'job': _public(record),
        'artifacts': artifacts['artifacts'],
        'artifacts_truncated': artifacts['truncated'],
        'output': output['output'],
        'output_lines_returned': output['lines_returned'],
        'earlier_output_omitted': output['earlier_output_omitted'],
        'output_truncated': output['output_truncated'],
    }


def list_jobs(limit: int = LIST_LIMIT) -> List[dict]:
    """The newest analysis jobs first."""
    ids: Set[str] = set(research_jobs.running_job_ids(ANALYSIS))
    try:
        ids.update(name for name in os.listdir(ANALYSIS_ROOT) if research_jobs.JOB_ID_PATTERN.fullmatch(name))
    except FileNotFoundError:
        pass
    records = []
    for job_id in ids:
        try:
            records.append(_public(research_jobs.get_scoped_job(job_id, ANALYSIS)))
        except ProjectFileError:
            continue
    records.sort(key=lambda record: record.get('started_at') or '', reverse=True)
    return records[:limit]


def cancel_job(job_id: str) -> dict:
    result = research_jobs.cancel_scoped_job(job_id, ANALYSIS)
    return {**result, 'job': _public(result['job'])}


def delete_job(job_id: str) -> dict:
    """Delete a finished job's workspace now; running jobs must be cancelled first."""
    research_jobs.check_job_id(job_id, ANALYSIS)
    with _workspace_lock:
        if job_id in research_jobs.running_job_ids(ANALYSIS) or job_id in _preparing:
            raise _error('job_running', 'The analysis job is still running. Cancel it first.', 409)
        root = _open_root()
        try:
            if _lstat(root, job_id) is None:
                raise _error('not_found', _gone_message(job_id), 404)
            _discard(root, job_id)
        except OSError as exc:
            raise _error('io_error', f'Could not delete analysis job {job_id}: {exc.strerror or exc}.', 500)
        finally:
            os.close(root)
    return {'job_id': job_id, 'deleted': True}


def _sniff(fd: int) -> Tuple[str, Optional[str]]:
    """Classify a file as ('image', mime), ('text', None) or ('binary', None) from its first bytes."""
    head = os.pread(fd, 8192, 0)
    mime = _image_mime(head)
    if mime:
        return 'image', mime
    if b'\x00' in head:
        return 'binary', None
    try:
        head.decode('utf-8')
    except UnicodeDecodeError as exc:
        # A multi-byte character cut at the end of the sniffed block is still text.
        if exc.start < len(head) - 3:
            return 'binary', None
    return 'text', None


def _image_mime(head: bytes) -> Optional[str]:
    if head.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'image/png'
    if head.startswith(b'\xff\xd8\xff'):
        return 'image/jpeg'
    if head[:6] in (b'GIF87a', b'GIF89a'):
        return 'image/gif'
    if head[:4] == b'RIFF' and head[8:12] == b'WEBP':
        return 'image/webp'
    return None


def _image_size(data: bytes, mime: str) -> Optional[Tuple[int, int]]:
    """Width and height from an image header, or None when the header is malformed."""
    try:
        if mime == 'image/png':
            if data[12:16] != b'IHDR':
                return None
            return int.from_bytes(data[16:20], 'big'), int.from_bytes(data[20:24], 'big')
        if mime == 'image/gif':
            return int.from_bytes(data[6:8], 'little'), int.from_bytes(data[8:10], 'little')
        if mime == 'image/webp':
            chunk = data[12:16]
            if chunk == b'VP8 ':
                return int.from_bytes(data[26:28], 'little') & 0x3FFF, int.from_bytes(data[28:30], 'little') & 0x3FFF
            if chunk == b'VP8L':
                bits = int.from_bytes(data[21:25], 'little')
                return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
            if chunk == b'VP8X':
                return int.from_bytes(data[24:27], 'little') + 1, int.from_bytes(data[27:30], 'little') + 1
            return None
        # JPEG: walk the segments to the first start-of-frame marker.
        index = 2
        while index + 9 < len(data):
            if data[index] != 0xFF:
                return None
            marker = data[index + 1]
            if marker == 0xFF:
                index += 1
                continue
            if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                index += 2
                continue
            length = int.from_bytes(data[index + 2:index + 4], 'big')
            if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                return int.from_bytes(data[index + 7:index + 9], 'big'), int.from_bytes(data[index + 5:index + 7], 'big')
            if marker in (0xD9, 0xDA) or length < 2:
                return None
            index += 2 + length
        return None
    except (IndexError, ValueError):
        return None


def _verify_image(data: bytes) -> bool:
    """Decode-check the image with Pillow (installed with matplotlib) after size checks passed."""
    try:
        from PIL import Image
    except ImportError:
        return True
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.verify()
        return True
    except Exception:
        return False


def _parse_artifact_path(path: object) -> List[str]:
    if not isinstance(path, str) or not path.strip():
        raise _error('invalid_path', 'path must name a file in the job\'s output folder, e.g. "equity.png".', 400)
    if len(path) > 1024 or '\x00' in path or '\\' in path or path.startswith(('/', '~')) or (len(path) > 1 and path[1] == ':'):
        raise _error('invalid_path', 'Use a relative path inside the job\'s output folder, e.g. "charts/equity.png".', 400)
    parts = [part for part in path.split('/') if part]
    if any(part in ('.', '..') for part in parts):
        raise _error('invalid_path', 'Artifact paths cannot contain "." or ".." components.', 400)
    if parts and parts[0] == OUTPUT_DIR:
        parts = parts[1:]
    if not parts:
        raise _error('invalid_path', 'path must name a file inside the output folder.', 400)
    return parts


def _open_output(job_id: str) -> int:
    workspace = _open_workspace(job_id)
    try:
        return _open_dir(workspace, OUTPUT_DIR, f'Analysis job {job_id} has no output folder.')
    finally:
        os.close(workspace)


def list_artifacts(job_id: str) -> dict:
    """Files under the job's output folder (symlinks listed but never followed or served)."""
    research_jobs.check_job_id(job_id, ANALYSIS)
    output_fd = _open_output(job_id)
    artifacts: List[dict] = []
    truncated = False

    def walk(dir_fd: int, prefix: Sequence[str]) -> None:
        nonlocal truncated
        with os.scandir(dir_fd) as iterator:
            children = sorted(iterator, key=lambda entry: entry.name)
        for child in children:
            if len(artifacts) >= MAX_ARTIFACTS_LISTED:
                truncated = True
                return
            path = '/'.join([*prefix, child.name])
            try:
                st = child.stat(follow_symlinks=False)
            except OSError:
                continue
            if stat.S_ISDIR(st.st_mode):
                try:
                    sub = os.open(child.name, _DIR_FLAGS, dir_fd=dir_fd)
                except OSError:
                    continue
                try:
                    walk(sub, [*prefix, child.name])
                finally:
                    os.close(sub)
                continue
            item: Dict[str, object] = {'path': path, 'size_bytes': st.st_size}
            if stat.S_ISLNK(st.st_mode):
                item.update(kind='symlink', size_bytes=None)
            elif stat.S_ISREG(st.st_mode):
                try:
                    fd = os.open(child.name, _FILE_READ_FLAGS, dir_fd=dir_fd)
                except OSError:
                    continue
                try:
                    kind, mime = _sniff(fd)
                finally:
                    os.close(fd)
                item['kind'] = kind
                if mime:
                    item['mime_type'] = mime
            else:
                item['kind'] = 'other'
            artifacts.append(item)
            if truncated:
                return

    try:
        walk(output_fd, [])
    finally:
        os.close(output_fd)
    return {'artifacts': artifacts, 'truncated': truncated}


def read_artifact(job_id: str, path: str) -> dict:
    """
    Return one artifact of the job: an image as base64 with its format and size, text up to
    MAX_TEXT_ARTIFACT_CHARS, or only metadata for other binary files.

    The path is resolved inside the job's output folder one component at a time without
    following symlinks, so no other workspace or storage file can be reached.
    """
    research_jobs.check_job_id(job_id, ANALYSIS)
    parts = _parse_artifact_path(path)
    display = '/'.join(parts)
    dir_fd = _open_output(job_id)
    try:
        for name in parts[:-1]:
            child = _open_dir(dir_fd, name, f'{display} does not exist in the output folder.')
            os.close(dir_fd)
            dir_fd = child
        try:
            fd = os.open(parts[-1], _FILE_READ_FLAGS, dir_fd=dir_fd)
        except FileNotFoundError:
            raise _error('not_found', f'{display} does not exist in the output folder of analysis job {job_id}.', 404)
        except OSError:
            st = _lstat(dir_fd, parts[-1])
            if st is not None and stat.S_ISLNK(st.st_mode):
                raise _error('unsafe_path', f'{display} is a symlink; only regular files are returned.', 403)
            raise _error('wrong_type', f'{display} cannot be opened as a file.', 409)
    finally:
        os.close(dir_fd)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise _error('wrong_type', f'{display} is not a regular file.', 409)
        kind, mime = _sniff(fd)
        base = {'job_id': job_id, 'path': display, 'size_bytes': st.st_size,
                'modified_at': datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat(timespec='seconds')}
        if kind == 'image' and mime:
            if st.st_size > MAX_IMAGE_BYTES:
                raise _error('artifact_too_large', f'{display} is {st.st_size} bytes; images are returned up to '
                             f'{MAX_IMAGE_BYTES // (1024 * 1024)} MiB. Save it smaller (lower dpi or figure size).', 413)
            data = os.pread(fd, MAX_IMAGE_BYTES + 1, 0)
            if len(data) != st.st_size:
                raise _error('artifact_changed', f'{display} changed while it was being read; fetch it again.', 409)
            size = _image_size(data, mime)
            if size is None:
                raise _error('invalid_image', f'{display} starts like a {mime} file but is not a valid image.', 422)
            width, height = size
            # Dimensions are checked before Pillow opens the image: Pillow refuses very large
            # pixel counts as decompression bombs, which would misreport a legitimately
            # oversized chart as invalid instead of telling the caller to shrink it.
            if not (1 <= width <= MAX_IMAGE_DIMENSION and 1 <= height <= MAX_IMAGE_DIMENSION):
                raise _error('artifact_too_large', f'{display} is {width}x{height} pixels; images are returned up to '
                             f'{MAX_IMAGE_DIMENSION} pixels per side. Save it smaller (lower dpi or figure size).', 413)
            if not _verify_image(data):
                raise _error('invalid_image', f'{display} starts like a {mime} file but is not a valid image.', 422)
            return {**base, 'kind': 'image', 'mime_type': mime, 'width': width, 'height': height,
                    'data_base64': base64.b64encode(data).decode('ascii')}
        if kind == 'text':
            raw = os.pread(fd, MAX_TEXT_ARTIFACT_CHARS * 4 + 4, 0)
            text = raw.decode('utf-8', errors='replace')
            truncated = len(text) > MAX_TEXT_ARTIFACT_CHARS or len(raw) < st.st_size
            return {**base, 'kind': 'text', 'content': text[:MAX_TEXT_ARTIFACT_CHARS], 'truncated': truncated}
        return {**base, 'kind': 'binary', 'message': (
            f'{display} is a binary file; only PNG, JPEG, GIF and WebP images and text files are returned.')}
    finally:
        os.close(fd)
