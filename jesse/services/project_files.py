"""
Project file access for MCP assistants, confined to strategies/ and research_scripts/.

Every operation resolves its path from the Jesse process's working directory (the project
root) one folder at a time with directory file descriptors and O_NOFOLLOW, so no symlink is
ever followed: not a symlinked root, not a symlinked strategy folder, and not a symlink that
another local process swaps in while an operation runs. Symlinks can be listed and deleted
(which removes only the link), but never read through, written through, copied, or moved.

Strategy folders (`strategies/<Name>`) are ordinary folders here: they can be created,
copied, moved or renamed, and deleted like any other folder. Only the two root folders are
protected: they are never moved, deleted, replaced, or written as files, and strategies/ is
never created (research_scripts/ is created on first use). Moving or copying never edits
file contents, so a renamed strategy keeps its old class name until its code is updated.

These checks confine the file API only. Code run from research_scripts/ (see
jesse.services.research_jobs) or loaded from a strategy has the Jesse process's full
privileges.
"""
import errno
import io
import os
import stat
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional, Sequence
from uuid import uuid4

STRATEGIES_ROOT = 'strategies'
RESEARCH_SCRIPTS_ROOT = 'research_scripts'
ROOTS = (STRATEGIES_ROOT, RESEARCH_SCRIPTS_ROOT)

# Listings are returned to an assistant's context window; 1,000 entries is roughly the
# largest listing that stays useful there. Narrow the path instead of paging.
DEFAULT_LIST_ENTRIES = 200
MAX_LIST_ENTRIES = 1000
# Text reads return at most this many lines and characters per call; callers page with
# start_line. 256K characters keeps a single tool result well inside MCP clients' limits.
DEFAULT_READ_LINES = 400
MAX_READ_LINES = 2000
MAX_READ_CHARS = 256 * 1024
# A NUL byte in the first 8 KiB marks a file as binary, the same heuristic git uses.
BINARY_SNIFF_BYTES = 8 * 1024
# Scripts, strategy modules, and configs are text well under 2 MiB. Larger payloads mean
# data or model files, which research scripts should write themselves.
MAX_WRITE_BYTES = 2 * 1024 * 1024
# Copies run inside one API request (the MCP tool waits up to two minutes). These caps keep a
# model-artifact promotion comfortably inside that window on ordinary disks.
MAX_COPY_BYTES = 1024 * 1024 * 1024
MAX_COPY_ENTRIES = 10_000
MAX_PATH_LENGTH = 1024
_COPY_CHUNK_BYTES = 1024 * 1024
_LINE_ENDINGS = ('\n', '\r')

_DIR_FLAGS = os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0) | getattr(os, 'O_NOFOLLOW', 0)
# O_NONBLOCK keeps open() from hanging on a FIFO; the fstat that follows then refuses it.
_FILE_READ_FLAGS = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
_FILE_CREATE_FLAGS = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0)
# Filesystems without hard links (some network, FUSE, and container volume mounts) report
# these when os.link is used for no-clobber publishing.
_NO_HARD_LINK_ERRNOS = {
    errno.EPERM, errno.EMLINK, errno.ENOSYS,
    getattr(errno, 'ENOTSUP', errno.EPERM), getattr(errno, 'EOPNOTSUPP', errno.EPERM),
}


def _platform_supported() -> bool:
    """The confinement relies on *at() system calls, which Windows does not provide."""
    return (
        hasattr(os, 'O_NOFOLLOW')
        and hasattr(os, 'O_DIRECTORY')
        and os.open in os.supports_dir_fd
        and os.scandir in os.supports_fd
        and os.link in os.supports_follow_symlinks
    )


class ProjectFileError(Exception):
    """A refused or failed request, carrying a stable error type and HTTP status for the API."""

    def __init__(self, error_type: str, message: str, status_code: int):
        super().__init__(message)
        self.error_type = error_type
        self.message = message
        self.status_code = status_code


def _error(error_type: str, message: str, status_code: int) -> ProjectFileError:
    return ProjectFileError(error_type, message, status_code)


def _not_found(display: str) -> ProjectFileError:
    return _error('not_found', f'{display} does not exist.', 404)


def _symlink_refused(display: str) -> ProjectFileError:
    return _error(
        'unsafe_path',
        f'{display} is a symlink. Project file tools never follow, read, write, copy, or move '
        'symlinks; delete_project_path removes only the link itself.',
        403,
    )


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def parse_path(path: str) -> List[str]:
    """
    Split a project-relative path such as "research_scripts/ml/train.py" into components.

    Only relative "/"-separated paths under one of ROOTS are accepted. "." and ".."
    components, backslashes, NUL bytes, and absolute or drive-letter paths are refused
    outright rather than normalized, so the requested path is exactly the path used.
    """
    if not _platform_supported():
        raise _error('unsupported_platform', 'Project file tools require Linux or macOS (including Docker).', 501)
    if not isinstance(path, str) or not path.strip():
        raise _error('invalid_path', 'A path such as "research_scripts/my_script.py" is required.', 400)
    if len(path) > MAX_PATH_LENGTH:
        raise _error('invalid_path', f'Paths are limited to {MAX_PATH_LENGTH} characters.', 400)
    if '\x00' in path or '\\' in path:
        raise _error('invalid_path', 'Paths must use "/" separators and cannot contain backslashes or NUL.', 400)
    if path.startswith('/') or path.startswith('~') or (len(path) > 1 and path[1] == ':'):
        raise _error('invalid_path', 'Use a project-relative path starting with strategies/ or research_scripts/, not an absolute path.', 400)
    parts = [part for part in path.split('/') if part]
    if any(part in ('.', '..') for part in parts):
        raise _error('invalid_path', 'Paths cannot contain "." or ".." components.', 400)
    if not parts or parts[0] not in ROOTS:
        raise _error('invalid_path', 'Paths must start with strategies/ or research_scripts/.', 400)
    return parts


def display_path(parts: Sequence[str]) -> str:
    return '/'.join(parts)


def _require_mutable(parts: Sequence[str], action: str) -> None:
    """Refuse changes to a root folder itself; everything below the roots may change."""
    if len(parts) == 1:
        raise _error('protected_path', f'{display_path(parts)}/ is a root folder; it cannot be {action}.', 403)


def _lstat(dir_fd: int, name: str) -> Optional[os.stat_result]:
    try:
        return os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None


def _entry_type(mode: int) -> str:
    if stat.S_ISLNK(mode):
        return 'symlink'
    if stat.S_ISDIR(mode):
        return 'directory'
    if stat.S_ISREG(mode):
        return 'file'
    return 'other'


def _iso_mtime(st: os.stat_result) -> str:
    return datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat(timespec='seconds')


def _os_error(exc: OSError, display: str) -> ProjectFileError:
    """Map an unexpected OSError to a stable error, naming only the project-relative path."""
    if exc.errno in (errno.EACCES, errno.EPERM):
        return _error('permission_denied', f'The Jesse process is not allowed to access {display}.', 403)
    if exc.errno == errno.ENAMETOOLONG:
        return _error('invalid_path', f'{display} has a name that is too long for the filesystem.', 400)
    if exc.errno == errno.ENOSPC:
        return _error('io_error', 'The disk is full.', 507)
    if exc.errno == errno.EXDEV:
        return _error(
            'cross_device',
            f'{display} is on a different filesystem. Copy it with copy_project_path, then delete the source.',
            409,
        )
    return _error('io_error', f'Could not access {display}: {exc.strerror or exc}.', 500)


def _open_child_dir(dir_fd: int, name: str, display: str) -> int:
    """Open a sub-folder without following a symlink, classifying failures for the caller."""
    try:
        return os.open(name, _DIR_FLAGS, dir_fd=dir_fd)
    except FileNotFoundError:
        raise _not_found(display)
    except OSError as exc:
        st = _lstat(dir_fd, name)
        if st is not None and stat.S_ISLNK(st.st_mode):
            raise _symlink_refused(display)
        if exc.errno == errno.ENOTDIR or (st is not None and not stat.S_ISDIR(st.st_mode)):
            raise _error('wrong_type', f'{display} is not a folder.', 409)
        raise _os_error(exc, display)


def open_directory(parts: Sequence[str], create: bool = False) -> int:
    """
    Open the folder at `parts` (root first) and return its descriptor; the caller closes it.

    With `create`, missing folders are made one level at a time, still without following
    symlinks, including a missing strategy folder. research_scripts/ is created on first
    use; strategies/ is never created here.
    """
    fd = os.open('.', os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
    try:
        for index, name in enumerate(parts):
            display = display_path(parts[:index + 1])
            try:
                child = _open_child_dir(fd, name, display)
            except ProjectFileError as exc:
                creatable = create and not (parts[0] == STRATEGIES_ROOT and index == 0)
                if exc.error_type != 'not_found' or not creatable:
                    if exc.error_type == 'not_found' and parts[0] == STRATEGIES_ROOT and index == 1:
                        raise _error(
                            'strategy_not_found',
                            f'Strategy folder {display} does not exist. Check the name with '
                            'list_project_files("strategies").',
                            404,
                        )
                    raise
                try:
                    os.mkdir(name, 0o777, dir_fd=fd)
                except FileExistsError:
                    pass
                except OSError as mkdir_error:
                    raise _os_error(mkdir_error, display)
                child = _open_child_dir(fd, name, display)
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def open_regular_file(parts: Sequence[str]) -> int:
    """Open an existing regular file for reading without following symlinks at any level."""
    parent_fd = open_directory(parts[:-1])
    display = display_path(parts)
    try:
        try:
            fd = os.open(parts[-1], _FILE_READ_FLAGS, dir_fd=parent_fd)
        except FileNotFoundError:
            raise _not_found(display)
        except OSError as exc:
            st = _lstat(parent_fd, parts[-1])
            if st is not None and stat.S_ISLNK(st.st_mode):
                raise _symlink_refused(display)
            raise _os_error(exc, display)
    finally:
        os.close(parent_fd)
    st = os.fstat(fd)
    if not stat.S_ISREG(st.st_mode):
        os.close(fd)
        kind = 'a folder; use list_project_files' if stat.S_ISDIR(st.st_mode) else 'not a regular file'
        raise _error('wrong_type', f'{display} is {kind}.', 409)
    return fd


# ---------------------------------------------------------------------------
# Listing and reading
# ---------------------------------------------------------------------------

def list_files(path: str = '', recursive: bool = False, max_entries: int = DEFAULT_LIST_ENTRIES) -> dict:
    """
    List a folder's entries (recursively when asked) without following symlinks.

    An empty path lists the two roots. Symlinks are reported with type "symlink" and
    never descended into. Output stops at `max_entries` with `truncated` set.
    """
    if not isinstance(max_entries, int) or not 1 <= max_entries <= MAX_LIST_ENTRIES:
        raise _error('invalid_request', f'max_entries must be between 1 and {MAX_LIST_ENTRIES}.', 400)

    if not path or not path.strip('/'):
        entries = []
        project_fd = os.open('.', os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
        try:
            for root in ROOTS:
                st = _lstat(project_fd, root)
                entries.append({
                    'path': root,
                    'type': _entry_type(st.st_mode) if st else 'missing',
                })
        finally:
            os.close(project_fd)
        return {'path': '', 'entries': entries, 'truncated': False}

    parts = parse_path(path)
    entries: List[Dict] = []
    truncated = False

    def walk(dir_fd: int, prefix: Sequence[str]) -> None:
        nonlocal truncated
        with os.scandir(dir_fd) as iterator:
            children = sorted(iterator, key=lambda entry: entry.name)
        for child in children:
            if len(entries) >= max_entries:
                truncated = True
                return
            child_parts = [*prefix, child.name]
            try:
                st = child.stat(follow_symlinks=False)
            except FileNotFoundError:
                continue  # Removed while listing.
            item = {'path': display_path(child_parts), 'type': _entry_type(st.st_mode), 'modified_at': _iso_mtime(st)}
            if stat.S_ISREG(st.st_mode):
                item['size_bytes'] = st.st_size
            entries.append(item)
            if recursive and stat.S_ISDIR(st.st_mode):
                try:
                    sub_fd = _open_child_dir(dir_fd, child.name, item['path'])
                except ProjectFileError:
                    continue  # Swapped for a symlink or removed while listing; never followed.
                try:
                    walk(sub_fd, child_parts)
                finally:
                    os.close(sub_fd)
            if truncated:
                return

    dir_fd = open_directory(parts)
    try:
        walk(dir_fd, parts)
    finally:
        os.close(dir_fd)
    return {'path': display_path(parts), 'entries': entries, 'truncated': truncated}


def _binary_metadata(display: str, st: os.stat_result) -> dict:
    return {
        'path': display,
        'kind': 'binary',
        'size_bytes': st.st_size,
        'modified_at': _iso_mtime(st),
        'message': (
            f'{display} is a binary file; its contents are not returned. Use copy_project_path to '
            'promote artifacts such as trained models into a strategy folder.'
        ),
    }


def read_text_file(path: str, start_line: int = 1, max_lines: int = DEFAULT_READ_LINES) -> dict:
    """
    Return up to `max_lines` lines of a UTF-8 text file starting at `start_line` (1-based).

    Line endings are returned unchanged. Binary files (a NUL byte near the start, or content
    that is not UTF-8) return size and modification metadata only, never their bytes. At most
    MAX_READ_CHARS characters are returned; a longer single line is cut with
    `line_truncated` set.
    """
    if not isinstance(start_line, int) or start_line < 1:
        raise _error('invalid_request', 'start_line must be 1 or greater.', 400)
    if not isinstance(max_lines, int) or not 1 <= max_lines <= MAX_READ_LINES:
        raise _error('invalid_request', f'max_lines must be between 1 and {MAX_READ_LINES}.', 400)

    parts = parse_path(path)
    display = display_path(parts)
    raw = os.fdopen(open_regular_file(parts), 'rb')
    st = os.fstat(raw.fileno())
    if b'\x00' in raw.read(BINARY_SNIFF_BYTES):
        raw.close()
        return _binary_metadata(display, st)
    raw.seek(0)

    lines: List[str] = []
    chars = 0
    has_more = False
    line_truncated = False
    # newline='' recognizes "\n", "\r\n" and "\r" without translating them. readline() is
    # always given a limit so one enormous line is never buffered whole.
    with io.TextIOWrapper(raw, encoding='utf-8', errors='strict', newline='') as text:
        try:
            current = 1
            while current < start_line:
                piece = text.readline(MAX_READ_CHARS)
                if not piece:
                    break
                if piece.endswith(_LINE_ENDINGS):
                    current += 1
            while True:
                if len(lines) >= max_lines or chars >= MAX_READ_CHARS:
                    has_more = bool(text.readline(1))
                    break
                room = MAX_READ_CHARS - chars
                piece = text.readline(room)
                if not piece:
                    break
                if len(piece) == room and not piece.endswith(_LINE_ENDINGS) and text.readline(1):
                    # The line does not fit. Return it cut only when it is the first line;
                    # otherwise stop before it so the next call starts on it.
                    has_more = True
                    if not lines:
                        lines.append(piece)
                        line_truncated = True
                    break
                lines.append(piece)
                chars += len(piece)
        except UnicodeDecodeError:
            return _binary_metadata(display, st)

    result = {
        'path': display,
        'kind': 'text',
        'content': ''.join(lines),
        'start_line': start_line,
        'end_line': start_line + len(lines) - 1 if lines else None,
        'has_more': has_more,
        'size_bytes': st.st_size,
        'modified_at': _iso_mtime(st),
    }
    if has_more:
        result['next_start_line'] = start_line + len(lines)
    if line_truncated:
        result['line_truncated'] = True
    return result


# ---------------------------------------------------------------------------
# Writing, folders, moving, copying, deleting
# ---------------------------------------------------------------------------

def _temp_name() -> str:
    # Fixed-length name so long target names cannot push it over the filesystem limit.
    return f'.jesse-{uuid4().hex}.tmp'


def _create_file(dir_fd: int, name: str) -> int:
    """Create a new file exclusively; O_EXCL also refuses an existing symlink."""
    return os.open(name, _FILE_CREATE_FLAGS, 0o666, dir_fd=dir_fd)


def _rename_into_reserved_name(src_fd: int, src_name: str, dst_fd: int, dst_name: str, dst_display: str) -> None:
    """
    No-clobber rename for filesystems without hard links.

    The destination name is first claimed with an exclusive create (which fails if anything,
    including a symlink, already has that name), then the source is renamed over that empty
    placeholder. A file created concurrently by someone else is therefore never replaced;
    the only visible intermediate state is our own empty placeholder. If the rename fails the
    placeholder is removed only while it is still the file we created.
    """
    try:
        placeholder = _create_file(dst_fd, dst_name)
    except FileExistsError:
        raise _error('already_exists', f'{dst_display} already exists. Pass overwrite=true to replace it.', 409)
    try:
        ours = os.fstat(placeholder)
    finally:
        os.close(placeholder)
    try:
        os.rename(src_name, dst_name, src_dir_fd=src_fd, dst_dir_fd=dst_fd)
    except BaseException:
        current = _lstat(dst_fd, dst_name)
        if current is not None and (current.st_dev, current.st_ino) == (ours.st_dev, ours.st_ino):
            try:
                os.unlink(dst_name, dir_fd=dst_fd)
            except FileNotFoundError:
                pass
        raise


def _publish_target(dir_fd: int, name: str, overwrite: bool, display: str) -> Optional[os.stat_result]:
    """Return the destination's current entry (None if free), refusing what publishing may not replace."""
    existing = _lstat(dir_fd, name)
    if existing is not None:
        if not overwrite:
            raise _error('already_exists', f'{display} already exists. Pass overwrite=true to replace it.', 409)
        if stat.S_ISLNK(existing.st_mode):
            raise _symlink_refused(display)
        if not stat.S_ISREG(existing.st_mode):
            raise _error('wrong_type', f'{display} is not a regular file; overwrite only replaces files.', 409)
    return existing


def _publish(dir_fd: int, temp: str, name: str, overwrite: bool, display: str) -> bool:
    """
    Move a finished temporary file into place and return whether a file was replaced.

    Without overwrite, a hard link publishes atomically and fails if the name exists, so a
    file created concurrently is never clobbered; filesystems without hard links use an
    exclusively created placeholder instead (_rename_into_reserved_name). With overwrite,
    os.replace swaps the directory entry, so a symlink at the destination is replaced rather
    than followed.
    """
    try:
        if _publish_target(dir_fd, name, overwrite, display) is not None:
            os.replace(temp, name, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
            return True
        try:
            os.link(temp, name, src_dir_fd=dir_fd, dst_dir_fd=dir_fd, follow_symlinks=False)
        except FileExistsError:
            raise _error('already_exists', f'{display} already exists. Pass overwrite=true to replace it.', 409)
        except OSError as exc:
            if exc.errno not in _NO_HARD_LINK_ERRNOS:
                raise
            _rename_into_reserved_name(dir_fd, temp, dir_fd, name, display)
        return False
    except OSError as exc:
        if exc.errno == errno.EISDIR:
            raise _error('wrong_type', f'{display} is a folder; overwrite only replaces files.', 409)
        raise _os_error(exc, display)
    finally:
        try:
            os.unlink(temp, dir_fd=dir_fd)
        except FileNotFoundError:
            pass


def write_text_file(path: str, content: str, overwrite: bool = False) -> dict:
    """
    Write UTF-8 text to a file, creating missing parent folders.

    The text is stored exactly as sent (no newline translation). The file appears
    complete or not at all, and an existing file is replaced only with `overwrite`.
    """
    parts = parse_path(path)
    _require_mutable(parts, 'written')
    display = display_path(parts)
    if not isinstance(content, str):
        raise _error('invalid_request', 'content must be text.', 400)
    data = content.encode('utf-8')
    if len(data) > MAX_WRITE_BYTES:
        raise _error('too_large', f'Content is limited to {MAX_WRITE_BYTES // (1024 * 1024)} MiB per write.', 413)

    parent_fd = open_directory(parts[:-1], create=True)
    try:
        temp = _temp_name()
        try:
            fd = _create_file(parent_fd, temp)
            with os.fdopen(fd, 'wb') as f:
                f.write(data)
        except OSError as exc:
            try:
                os.unlink(temp, dir_fd=parent_fd)
            except FileNotFoundError:
                pass
            raise _os_error(exc, display)
        overwritten = _publish(parent_fd, temp, parts[-1], overwrite, display)
    finally:
        os.close(parent_fd)
    return {'path': display, 'size_bytes': len(data), 'overwritten': overwritten}


def write_file_from_chunks(path: str, chunks: Iterable[bytes], overwrite: bool = False) -> dict:
    """
    Stream generated bytes into a project file, creating missing parent folders.

    Unlike write_text_file there is no size cap: this is for data Jesse itself produces from
    the project's own database (candle exports), which can be far larger than anything an
    assistant sends. Confinement and publishing are identical: the path is resolved without
    following symlinks, the bytes go to a temporary file, and the file appears complete or not
    at all. If producing a chunk raises, the temporary file is removed and nothing is published.
    A destination that cannot be replaced is refused before the first chunk is produced, so a
    retry without overwrite never regenerates the data just to fail; publishing checks again.
    """
    parts = parse_path(path)
    _require_mutable(parts, 'written')
    display = display_path(parts)

    parent_fd = open_directory(parts[:-1], create=True)
    try:
        try:
            _publish_target(parent_fd, parts[-1], overwrite, display)
        except OSError as exc:
            raise _os_error(exc, display)
        temp = _temp_name()
        size = 0
        try:
            fd = _create_file(parent_fd, temp)
            with os.fdopen(fd, 'wb') as f:
                for chunk in chunks:
                    f.write(chunk)
                    size += len(chunk)
        except BaseException as exc:
            try:
                os.unlink(temp, dir_fd=parent_fd)
            except FileNotFoundError:
                pass
            if isinstance(exc, OSError):
                raise _os_error(exc, display)
            raise
        overwritten = _publish(parent_fd, temp, parts[-1], overwrite, display)
    finally:
        os.close(parent_fd)
    return {'path': display, 'size_bytes': size, 'overwritten': overwritten}


def make_directory(path: str) -> dict:
    """Create a folder and any missing parents; an existing folder is reported, not an error."""
    parts = parse_path(path)
    _require_mutable(parts, 'created')
    display = display_path(parts)
    parent_fd = open_directory(parts[:-1], create=True)
    try:
        try:
            os.mkdir(parts[-1], 0o777, dir_fd=parent_fd)
            created = True
        except FileExistsError:
            os.close(_open_child_dir(parent_fd, parts[-1], display))  # Must be a real folder.
            created = False
        except OSError as exc:
            raise _os_error(exc, display)
    finally:
        os.close(parent_fd)
    return {'path': display, 'created': created}


def _is_inside(inner: Sequence[str], outer: Sequence[str]) -> bool:
    return len(inner) >= len(outer) and list(inner[:len(outer)]) == list(outer)


def move_path(source: str, destination: str, overwrite: bool = False) -> dict:
    """
    Move or rename a file or folder within or between the two roots.

    Symlinks are never moved. Folders are never merged: a folder moves only to a path that
    does not exist. `overwrite` replaces an existing destination file with a source file.
    """
    src_parts, dst_parts = parse_path(source), parse_path(destination)
    _require_mutable(src_parts, 'moved')
    _require_mutable(dst_parts, 'replaced or created by a move')
    src_display, dst_display = display_path(src_parts), display_path(dst_parts)
    if src_parts == dst_parts:
        raise _error('invalid_request', 'Source and destination are the same path.', 400)
    if _is_inside(dst_parts, src_parts):
        raise _error('invalid_request', 'A folder cannot be moved into itself.', 400)

    src_parent = open_directory(src_parts[:-1])
    try:
        src_stat = _lstat(src_parent, src_parts[-1])
        if src_stat is None:
            raise _not_found(src_display)
        if stat.S_ISLNK(src_stat.st_mode):
            raise _symlink_refused(src_display)
        is_dir = stat.S_ISDIR(src_stat.st_mode)
        if not is_dir and not stat.S_ISREG(src_stat.st_mode):
            raise _error('wrong_type', f'{src_display} is not a regular file or folder.', 409)

        dst_parent = open_directory(dst_parts[:-1], create=True)
        try:
            dst_stat = _lstat(dst_parent, dst_parts[-1])
            overwritten = False
            if dst_stat is not None:
                if not overwrite:
                    raise _error('already_exists', f'{dst_display} already exists. Pass overwrite=true to replace a file.', 409)
                if is_dir or not stat.S_ISREG(dst_stat.st_mode):
                    raise _error(
                        'wrong_type',
                        'overwrite only replaces a file with a file. Delete the destination first to replace a folder.',
                        409,
                    )
                overwritten = True
            try:
                if overwritten:
                    os.replace(src_parts[-1], dst_parts[-1], src_dir_fd=src_parent, dst_dir_fd=dst_parent)
                elif is_dir:
                    # rename() never follows symlinks. A folder cannot be hard-linked, so a same-named
                    # folder created after the check above is still replaced if it is empty; a
                    # non-empty folder or a file makes rename() fail, so no file data can be lost.
                    os.rename(src_parts[-1], dst_parts[-1], src_dir_fd=src_parent, dst_dir_fd=dst_parent)
                else:
                    _move_file_no_clobber(src_parent, src_parts[-1], dst_parent, dst_parts[-1], dst_display)
            except OSError as exc:
                if exc.errno == errno.EINVAL:
                    raise _error('invalid_request', 'A folder cannot be moved into itself.', 400)
                if exc.errno in (errno.ENOTEMPTY, errno.EEXIST, errno.EISDIR, errno.ENOTDIR):
                    raise _error('already_exists', f'{dst_display} already exists.', 409)
                raise _os_error(exc, src_display)
        finally:
            os.close(dst_parent)
    finally:
        os.close(src_parent)
    return {'source': src_display, 'destination': dst_display, 'type': 'directory' if is_dir else 'file', 'overwritten': overwritten}


def _move_file_no_clobber(src_fd: int, src_name: str, dst_fd: int, dst_name: str, dst_display: str) -> None:
    """Hard-link then unlink, so a destination created concurrently is never replaced."""
    try:
        os.link(src_name, dst_name, src_dir_fd=src_fd, dst_dir_fd=dst_fd, follow_symlinks=False)
    except FileExistsError:
        raise _error('already_exists', f'{dst_display} already exists. Pass overwrite=true to replace it.', 409)
    except OSError as exc:
        if exc.errno not in _NO_HARD_LINK_ERRNOS:
            raise
        _rename_into_reserved_name(src_fd, src_name, dst_fd, dst_name, dst_display)
        return
    os.unlink(src_name, dir_fd=src_fd)


@dataclass
class _CopyBudget:
    entries: int = 0
    bytes: int = 0

    def add_entry(self) -> None:
        self.entries += 1
        if self.entries > MAX_COPY_ENTRIES:
            raise _error('too_large', f'Copies are limited to {MAX_COPY_ENTRIES} files and folders.', 413)

    def add_bytes(self, count: int) -> None:
        self.bytes += count
        if self.bytes > MAX_COPY_BYTES:
            raise _error('too_large', f'Copies are limited to {MAX_COPY_BYTES // (1024 ** 3)} GiB.', 413)


def _copy_file_contents(src_fd: int, dst_fd: int, budget: _CopyBudget) -> None:
    while True:
        chunk = os.read(src_fd, _COPY_CHUNK_BYTES)
        if not chunk:
            return
        budget.add_bytes(len(chunk))
        view = memoryview(chunk)
        while view:
            written = os.write(dst_fd, view)
            view = view[written:]


def _copy_tree(src_dir: int, dst_dir: int, prefix: Sequence[str], budget: _CopyBudget) -> None:
    """Copy a folder's contents; any symlink or special file aborts the whole copy."""
    with os.scandir(src_dir) as iterator:
        children = sorted(iterator, key=lambda entry: entry.name)
    for child in children:
        budget.add_entry()
        child_parts = [*prefix, child.name]
        display = display_path(child_parts)
        st = child.stat(follow_symlinks=False)
        if stat.S_ISLNK(st.st_mode):
            raise _symlink_refused(display)
        if stat.S_ISDIR(st.st_mode):
            os.mkdir(child.name, 0o777, dir_fd=dst_dir)
            sub_src = _open_child_dir(src_dir, child.name, display)
            try:
                sub_dst = _open_child_dir(dst_dir, child.name, display)
                try:
                    _copy_tree(sub_src, sub_dst, child_parts, budget)
                finally:
                    os.close(sub_dst)
            finally:
                os.close(sub_src)
        elif stat.S_ISREG(st.st_mode):
            try:
                in_fd = os.open(child.name, _FILE_READ_FLAGS, dir_fd=src_dir)
            except OSError as exc:
                if exc.errno == errno.ELOOP:
                    raise _symlink_refused(display)
                raise
            try:
                if not stat.S_ISREG(os.fstat(in_fd).st_mode):
                    raise _error('wrong_type', f'{display} is not a regular file.', 409)
                out_fd = _create_file(dst_dir, child.name)
                try:
                    _copy_file_contents(in_fd, out_fd, budget)
                finally:
                    os.close(out_fd)
            finally:
                os.close(in_fd)
        else:
            raise _error('wrong_type', f'{display} is not a regular file or folder; it cannot be copied.', 409)


def copy_path(source: str, destination: str, overwrite: bool = False) -> dict:
    """
    Copy a file or folder within or between the two roots, e.g. to promote a trained model
    from research_scripts/ into a strategy folder.

    The copy is built under a temporary name and published only when complete. A file
    copy replaces an existing destination file only with `overwrite`. Folder copies never
    merge: the destination must not exist. Any symlink in the source refuses the copy.
    """
    src_parts, dst_parts = parse_path(source), parse_path(destination)
    _require_mutable(dst_parts, 'created by a copy')
    src_display, dst_display = display_path(src_parts), display_path(dst_parts)
    if _is_inside(dst_parts, src_parts):
        raise _error('invalid_request', 'The destination cannot be the source or inside it.', 400)

    budget = _CopyBudget()
    src_parent = open_directory(src_parts[:-1]) if len(src_parts) > 1 else None
    try:
        if src_parent is None:
            src_is_dir = True
        else:
            src_stat = _lstat(src_parent, src_parts[-1])
            if src_stat is None:
                raise _not_found(src_display)
            if stat.S_ISLNK(src_stat.st_mode):
                raise _symlink_refused(src_display)
            src_is_dir = stat.S_ISDIR(src_stat.st_mode)

        dst_parent = open_directory(dst_parts[:-1], create=True)
        try:
            if not src_is_dir:
                in_fd = open_regular_file(src_parts)
                try:
                    temp = _temp_name()
                    try:
                        out_fd = _create_file(dst_parent, temp)
                        try:
                            _copy_file_contents(in_fd, out_fd, budget)
                        finally:
                            os.close(out_fd)
                    except BaseException:
                        try:
                            os.unlink(temp, dir_fd=dst_parent)
                        except FileNotFoundError:
                            pass
                        raise
                    overwritten = _publish(dst_parent, temp, dst_parts[-1], overwrite, dst_display)
                finally:
                    os.close(in_fd)
                return {'source': src_display, 'destination': dst_display, 'type': 'file',
                        'size_bytes': budget.bytes, 'overwritten': overwritten}

            if _lstat(dst_parent, dst_parts[-1]) is not None:
                raise _error(
                    'already_exists',
                    f'{dst_display} already exists. Folder copies never merge or overwrite; delete it first or pick a new name.',
                    409,
                )
            temp = _temp_name()
            os.mkdir(temp, 0o777, dir_fd=dst_parent)
            try:
                src_dir = open_directory(src_parts)
                try:
                    temp_dir = _open_child_dir(dst_parent, temp, dst_display)
                    try:
                        _copy_tree(src_dir, temp_dir, src_parts, budget)
                    finally:
                        os.close(temp_dir)
                finally:
                    os.close(src_dir)
                # rename() of a folder fails if the name is now a non-empty folder or a file; an
                # empty folder created there since the check is replaced (it holds no data).
                os.rename(temp, dst_parts[-1], src_dir_fd=dst_parent, dst_dir_fd=dst_parent)
            except BaseException:
                _remove_tree_quietly(dst_parent, temp)
                raise
            return {'source': src_display, 'destination': dst_display, 'type': 'directory',
                    'size_bytes': budget.bytes, 'entries': budget.entries, 'overwritten': False}
        except OSError as exc:
            if exc.errno in (errno.ENOTEMPTY, errno.EEXIST, errno.ENOTDIR):
                raise _error('already_exists', f'{dst_display} already exists.', 409)
            raise _os_error(exc, dst_display)
        finally:
            os.close(dst_parent)
    finally:
        if src_parent is not None:
            os.close(src_parent)


def _remove_tree(dir_fd: int, name: str, display: str, counts: Dict[str, int]) -> None:
    """Delete a folder's contents and the folder; symlinks inside are unlinked, never followed."""
    sub_fd = _open_child_dir(dir_fd, name, display)
    try:
        with os.scandir(sub_fd) as iterator:
            children = list(iterator)
        for child in children:
            if child.is_dir(follow_symlinks=False):
                _remove_tree(sub_fd, child.name, f'{display}/{child.name}', counts)
            else:
                os.unlink(child.name, dir_fd=sub_fd)
                counts['files'] += 1
    finally:
        os.close(sub_fd)
    os.rmdir(name, dir_fd=dir_fd)
    counts['directories'] += 1


def _remove_tree_quietly(dir_fd: int, name: str) -> None:
    try:
        _remove_tree(dir_fd, name, name, {'files': 0, 'directories': 0})
    except (OSError, ProjectFileError):
        pass


def delete_path(path: str, recursive: bool = False) -> dict:
    """
    Delete a file, a symlink (only the link), or a folder.

    A folder, including a whole strategy folder, must be empty unless `recursive` is true.
    Root folders are refused.
    """
    parts = parse_path(path)
    _require_mutable(parts, 'deleted')
    display = display_path(parts)
    counts = {'files': 0, 'directories': 0}
    parent_fd = open_directory(parts[:-1])
    try:
        st = _lstat(parent_fd, parts[-1])
        if st is None:
            raise _not_found(display)
        kind = _entry_type(st.st_mode)
        try:
            if stat.S_ISDIR(st.st_mode):
                if recursive:
                    _remove_tree(parent_fd, parts[-1], display, counts)
                else:
                    try:
                        os.rmdir(parts[-1], dir_fd=parent_fd)
                    except OSError as exc:
                        if exc.errno in (errno.ENOTEMPTY, errno.EEXIST):
                            raise _error(
                                'directory_not_empty',
                                f'{display} is not empty. Pass recursive=true to delete it and everything inside.',
                                409,
                            )
                        raise
                    counts['directories'] += 1
            else:
                os.unlink(parts[-1], dir_fd=parent_fd)
                counts['files'] += 1
        except FileNotFoundError:
            raise _not_found(display)
        except OSError as exc:
            raise _os_error(exc, display)
    finally:
        os.close(parent_fd)
    return {'path': display, 'type': kind, 'deleted_files': counts['files'], 'deleted_directories': counts['directories']}
