"""
Directory-relative file access that never follows links, shared by the project file, analysis,
and research services.

Every operation takes an open directory and one child name, never a full path, so no link can
redirect a lookup and an ancestor cannot be swapped out from under an operation.

Directories and files are both integer CRT descriptors on every platform (on Windows the
descriptor wraps a Win32 handle, so os.close, os.fstat and os.read work unchanged).

POSIX uses directory descriptors with O_NOFOLLOW and the *at() calls.

Windows has no *at() calls in the standard library, so this module calls the native NT API
(ntdll) through ctypes and keeps the same guarantees:

1. Each child is opened with NtCreateFile relative to the directory handle the caller holds
   (RootDirectory). The name is a single component (see component_problem), so the kernel never
   re-resolves a path from the root.
2. Directories are opened without FILE_SHARE_DELETE. While Jesse holds an ancestor, no other
   process can rename, move, or delete it, so the chain from the root to any open directory
   cannot be replaced. The chain is therefore the one that was walked.
3. Every open passes FILE_OPEN_REPARSE_POINT, so a junction, symbolic link, or mount point in the
   final component is opened as the link itself and never traversed. The handle that will be used
   is then checked for FILE_ATTRIBUTE_REPARSE_POINT. Checks are made on handles, not on names, so
   a link swapped in after a lookup is refused rather than followed.
4. Windows aliases are refused before any open: alternate data streams (':'), device names such
   as CON or NUL (also with an extension), and names ending in a dot or space, which Win32 strips
   but NT does not.

Not prevented on either platform: a hard link to a file outside the project (it is a plain file
to both), and a leaf replaced between listing and opening (the object that is opened is still
checked on its handle).
"""
import errno
import os
import stat
import struct
from typing import List, Optional

IS_WINDOWS = os.name == 'nt'

# NAME_MAX on POSIX. On Windows the same number is the NTFS component limit in UTF-16 code units
# (what the file system counts), which is not the same as Python characters: an emoji is two units.
MAX_NAME_LENGTH = 255

# A no-follow POSIX open of a link fails with ELOOP; a directory open without the flag would follow it.
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

_WINDOWS_INVALID_CHARACTERS = frozenset('<>:"/\\|?*')
_WINDOWS_RESERVED_NAMES = frozenset(
    {'CON', 'PRN', 'AUX', 'NUL', 'CONIN$', 'CONOUT$'}  # CONIN$/CONOUT$ are the console handles Win32 opens.
    # The superscript digits are also device names on Windows (COM¹, LPT²).
    | {f'{prefix}{digit}' for prefix in ('COM', 'LPT') for digit in '0123456789¹²³'}
)


def supported() -> bool:
    """Whether this host can confine operations to directories it has opened."""
    if IS_WINDOWS:
        return True
    return (
        hasattr(os, 'O_NOFOLLOW')
        and hasattr(os, 'O_DIRECTORY')
        and os.open in os.supports_dir_fd
        and os.scandir in os.supports_fd
        and os.link in os.supports_follow_symlinks
    )


def extended_path(path: str) -> str:
    """
    A path Win32 accepts beyond MAX_PATH (260 characters), as an absolute `\\\\?\\` path on Windows.

    Use only for paths built from validated components: the extended prefix turns off Win32's
    normalisation, so "." and ".." are refused here rather than resolved. Links along the path are still
    followed exactly as without the prefix. POSIX paths are returned unchanged.
    """
    if not IS_WINDOWS:
        return path
    absolute = path if os.path.isabs(path) else os.path.join(os.getcwd(), path)
    absolute = absolute.replace('/', '\\')
    if any(part in ('.', '..') for part in absolute.split('\\')):
        raise ValueError(f'{path!r} contains "." or ".." components, which extended paths cannot resolve.')
    if absolute.startswith('\\\\?\\'):
        return absolute
    if absolute.startswith('\\\\'):
        return '\\\\?\\UNC\\' + absolute[2:]
    return '\\\\?\\' + absolute


def component_problem(name: str) -> Optional[str]:
    """
    Return why `name` is not a safe single path component on Windows, or None when it is.

    Applied only on Windows (project_files.parse_path and the NT operations below); POSIX
    uses its native filename rules. Win32 and NT resolve these names
    differently, so one API can name a different object than another: "name:stream" addresses
    an NTFS alternate data stream; "CON" and "NUL" address devices even with an extension; and
    Win32 strips trailing dots and spaces, so "a." and "a" name the same file through one API
    and different files through another.
    """
    if name in ('', '.', '..'):
        return 'is empty or a relative marker'
    try:
        units = len(name.encode('utf-16-le')) // 2
    except UnicodeEncodeError:
        # A lone surrogate has no UTF-16 encoding that a file name could store, so it is refused here
        # rather than being truncated or substituted by an encoder.
        return 'contains an unpaired surrogate, which cannot be stored in a Windows file name'
    if units > MAX_NAME_LENGTH:
        return f'is longer than {MAX_NAME_LENGTH} UTF-16 code units'
    if any(ch < ' ' or ch in _WINDOWS_INVALID_CHARACTERS for ch in name):
        return 'contains a character Windows does not allow (":" starts an alternate data stream)'
    if name.endswith((' ', '.')):
        return 'ends with a space or dot, which Windows silently strips'
    # The device check ignores spaces before the first dot: "NUL .txt" is still the NUL device.
    if name.split('.', 1)[0].rstrip(' ').upper() in _WINDOWS_RESERVED_NAMES:
        return 'is a reserved Windows device name'
    return None


def _windows_name(name: str) -> bytes:
    """Validate a component and return its UTF-16LE encoding, the exact bytes NT is given."""
    problem = component_problem(name)
    if problem is not None:
        raise OSError(errno.EINVAL, f'Windows does not allow the name {name!r}: it {problem}.')
    return name.encode('utf-16-le')


# ---------------------------------------------------------------------------
# Windows native API
# ---------------------------------------------------------------------------

if IS_WINDOWS:
    import ctypes
    import msvcrt

    _ntdll = ctypes.WinDLL('ntdll')
    _kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)

_SYNCHRONIZE = 0x00100000
_DELETE = 0x00010000
_FILE_LIST_DIRECTORY = 0x0001
_FILE_READ_DATA = 0x0001
_FILE_WRITE_DATA = 0x0002
_FILE_TRAVERSE = 0x0020
_FILE_READ_ATTRIBUTES = 0x0080
_FILE_SHARE_READ = 0x0001
_FILE_SHARE_WRITE = 0x0002
_FILE_SHARE_DELETE = 0x0004
# Directories are opened with no delete sharing; see the module docstring (guarantee 2).
_SHARE_NO_DELETE = _FILE_SHARE_READ | _FILE_SHARE_WRITE
_SHARE_ALL = _SHARE_NO_DELETE | _FILE_SHARE_DELETE
_FILE_OPEN = 0x00000001
_FILE_CREATE = 0x00000002
_FILE_DIRECTORY_FILE = 0x00000001
_FILE_NON_DIRECTORY_FILE = 0x00000040
_FILE_SYNCHRONOUS_IO_NONALERT = 0x00000020
# Guarantee 3: open the final component as a link, never through it.
_FILE_OPEN_REPARSE_POINT = 0x00200000
_OPEN_LINK_OPTIONS = _FILE_OPEN_REPARSE_POINT | _FILE_SYNCHRONOUS_IO_NONALERT
_OBJ_CASE_INSENSITIVE = 0x00000040  # What Win32 passes for every path it opens.
_FILE_ATTRIBUTE_DIRECTORY = 0x00000010
_FILE_ATTRIBUTE_REPARSE_POINT = 0x00000400
_FILE_ATTRIBUTE_NORMAL = 0x00000080
_FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
_OPEN_EXISTING = 3
_FILE_DIRECTORY_INFORMATION = 1
_FILE_RENAME_INFORMATION = 10
_FILE_DISPOSITION_INFORMATION = 13
_STATUS_NO_MORE_FILES = 0x80000006
# One directory query returns as many whole entries as fit; 64 KiB holds hundreds of the longest
# names, and the listing loops for more, so the size only trades calls for memory.
_LIST_BUFFER_BYTES = 64 * 1024
_FILETIME_EPOCH_OFFSET = 116444736000000000  # 100 ns ticks from 1601-01-01 to 1970-01-01
_INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value if IS_WINDOWS else None
_DIRECTORY_ACCESS = _FILE_LIST_DIRECTORY | _FILE_TRAVERSE | _FILE_READ_ATTRIBUTES | _SYNCHRONIZE

# NTSTATUS values are signed; the table is keyed by the unsigned form.
_NTSTATUS_ERRNO = {
    0xC0000034: errno.ENOENT,        # OBJECT_NAME_NOT_FOUND
    0xC000003A: errno.ENOENT,        # OBJECT_PATH_NOT_FOUND
    0xC0000056: errno.ENOENT,        # DELETE_PENDING: the name is already being removed
    0xC0000035: errno.EEXIST,        # OBJECT_NAME_COLLISION
    0xC0000022: errno.EACCES,        # ACCESS_DENIED
    0xC0000043: errno.EBUSY,         # SHARING_VIOLATION: another process holds the file open
    0xC0000121: errno.EBUSY,         # CANNOT_DELETE: an open handle elsewhere lacks delete sharing
    0xC0000103: errno.ENOTDIR,       # NOT_A_DIRECTORY
    0xC00000BA: errno.EISDIR,        # FILE_IS_A_DIRECTORY
    0xC0000101: errno.ENOTEMPTY,     # DIRECTORY_NOT_EMPTY
    0xC000050B: errno.ELOOP,         # REPARSE_POINT_ENCOUNTERED
    0x8000002D: errno.ELOOP,         # STOPPED_ON_SYMLINK
    0xC00000D4: errno.EXDEV,         # NOT_SAME_DEVICE
    0xC0000033: errno.EINVAL,        # OBJECT_NAME_INVALID
    0xC0000106: errno.ENAMETOOLONG,  # NAME_TOO_LONG
    0xC000007F: errno.ENOSPC,        # DISK_FULL
    0xC000009A: errno.ENOMEM,        # INSUFFICIENT_RESOURCES
}


def _check_status(status: int) -> None:
    if status >= 0:
        return
    unsigned = status & 0xFFFFFFFF
    code = _NTSTATUS_ERRNO.get(unsigned, errno.EIO)
    raise OSError(code, f'{os.strerror(code)} (NT status 0x{unsigned:08X})')


if IS_WINDOWS:
    class _UnicodeString(ctypes.Structure):
        _fields_ = [('Length', ctypes.c_ushort), ('MaximumLength', ctypes.c_ushort), ('Buffer', ctypes.c_void_p)]

    class _ObjectAttributes(ctypes.Structure):
        _fields_ = [
            ('Length', ctypes.c_ulong), ('RootDirectory', ctypes.c_void_p), ('ObjectName', ctypes.c_void_p),
            ('Attributes', ctypes.c_ulong), ('SecurityDescriptor', ctypes.c_void_p),
            ('SecurityQualityOfService', ctypes.c_void_p),
        ]

    class _IoStatusBlock(ctypes.Structure):
        _fields_ = [('Status', ctypes.c_size_t), ('Information', ctypes.c_size_t)]

    class _ByHandleFileInformation(ctypes.Structure):
        _fields_ = [(name, ctypes.c_ulong) for name in (
            'Attributes', 'CreatedLow', 'CreatedHigh', 'AccessedLow', 'AccessedHigh', 'WrittenLow', 'WrittenHigh',
            'VolumeSerial', 'SizeHigh', 'SizeLow', 'Links', 'IndexHigh', 'IndexLow',
        )]

    class _RenameInformation(ctypes.Structure):
        # Sized for the longest component; FileNameLength says how much of FileName is used.
        _fields_ = [
            ('ReplaceIfExists', ctypes.c_ubyte), ('RootDirectory', ctypes.c_void_p),
            ('FileNameLength', ctypes.c_ulong), ('FileName', ctypes.c_ubyte * (2 * MAX_NAME_LENGTH)),
        ]

    # The argument types matter: without them ctypes passes 64-bit handles truncated to 32 bits.
    _ntdll.NtCreateFile.argtypes = [
        ctypes.POINTER(ctypes.c_void_p), ctypes.c_ulong, ctypes.POINTER(_ObjectAttributes),
        ctypes.POINTER(_IoStatusBlock), ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong,
        ctypes.c_ulong, ctypes.c_void_p, ctypes.c_ulong,
    ]
    _ntdll.NtCreateFile.restype = ctypes.c_long
    _ntdll.NtSetInformationFile.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(_IoStatusBlock), ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong,
    ]
    _ntdll.NtSetInformationFile.restype = ctypes.c_long
    _ntdll.NtQueryDirectoryFile.argtypes = [
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(_IoStatusBlock),
        ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ubyte, ctypes.c_void_p, ctypes.c_ubyte,
    ]
    _ntdll.NtQueryDirectoryFile.restype = ctypes.c_long
    _kernel32.CreateFileW.argtypes = [
        ctypes.c_wchar_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong,
        ctypes.c_void_p,
    ]
    _kernel32.CreateFileW.restype = ctypes.c_void_p
    _kernel32.GetFileInformationByHandle.argtypes = [ctypes.c_void_p, ctypes.POINTER(_ByHandleFileInformation)]
    _kernel32.GetFileInformationByHandle.restype = ctypes.c_int


def _win_handle(fd: int) -> int:
    return msvcrt.get_osfhandle(fd)


def _adopt(handle: int, flags: int) -> int:
    """Wrap a handle in a CRT descriptor, which then owns it: os.close() closes the handle."""
    return msvcrt.open_osfhandle(handle, flags)


def _nt_open(parent_fd: int, name: str, access: int, share: int, disposition: int, options: int,
             attributes: int = 0) -> int:
    """Open `name` relative to the directory `parent_fd`; returns the raw handle."""
    encoded = _windows_name(name)
    # Lengths are in bytes of UTF-16. Using the character count here would cut a name such as
    # "rocket🚀.txt" short, because the emoji takes two code units.
    text = ctypes.create_string_buffer(encoded + b'\0\0')
    unicode_name = _UnicodeString(len(encoded), len(encoded) + 2, ctypes.addressof(text))
    attrs = _ObjectAttributes(
        ctypes.sizeof(_ObjectAttributes), _win_handle(parent_fd), ctypes.addressof(unicode_name),
        _OBJ_CASE_INSENSITIVE, None, None,
    )
    handle = ctypes.c_void_p()
    iosb = _IoStatusBlock()
    status = _ntdll.NtCreateFile(
        ctypes.byref(handle), access, ctypes.byref(attrs), ctypes.byref(iosb), None, attributes,
        share, disposition, options, None, 0,
    )
    _check_status(status)
    return handle.value


def _handle_info(fd: int) -> 'ctypes.Structure':  # _ByHandleFileInformation; defined only on Windows
    info = _ByHandleFileInformation()
    if not _kernel32.GetFileInformationByHandle(_win_handle(fd), ctypes.byref(info)):
        raise ctypes.WinError(ctypes.get_last_error())
    return info


def _windows_stat(attributes: int, size: int, written: int, index: int, serial: int, links: int) -> os.stat_result:
    if attributes & _FILE_ATTRIBUTE_REPARSE_POINT:
        mode = stat.S_IFLNK | 0o777
    elif attributes & _FILE_ATTRIBUTE_DIRECTORY:
        mode = stat.S_IFDIR | 0o777
    else:
        mode = stat.S_IFREG | 0o666
    seconds = max(0, (written - _FILETIME_EPOCH_OFFSET) // 10_000_000)
    return os.stat_result((mode, index, serial, links, 0, 0, size, seconds, seconds, seconds))


def _stat_from_handle(fd: int) -> os.stat_result:
    info = _handle_info(fd)
    return _windows_stat(
        info.Attributes,
        (info.SizeHigh << 32) | info.SizeLow,
        (info.WrittenHigh << 32) | info.WrittenLow,
        (info.IndexHigh << 32) | info.IndexLow,
        info.VolumeSerial,
        info.Links,
    )


def _require_kind(fd: int, name: str, directory: bool) -> None:
    """Refuse a link, and a handle whose type is not the one the caller asked for."""
    attributes = _handle_info(fd).Attributes
    if attributes & _FILE_ATTRIBUTE_REPARSE_POINT:
        raise OSError(errno.ELOOP, f'{name} is a symbolic link or junction, which is never followed.')
    is_directory = bool(attributes & _FILE_ATTRIBUTE_DIRECTORY)
    if directory and not is_directory:
        raise NotADirectoryError(errno.ENOTDIR, f'{name} is not a folder.')
    if not directory and is_directory:
        raise IsADirectoryError(errno.EISDIR, f'{name} is a folder.')


def _set_disposition(fd: int) -> None:
    """Mark the handle's object for deletion. Unlike FILE_DELETE_ON_CLOSE, errors are reported here."""
    flag = ctypes.create_string_buffer(b'\x01', 1)
    iosb = _IoStatusBlock()
    status = _ntdll.NtSetInformationFile(
        _win_handle(fd), ctypes.byref(iosb), flag, 1, _FILE_DISPOSITION_INFORMATION,
    )
    _check_status(status)


class _WindowsEntry:
    """A directory entry with the attributes the listing already returned (no extra open per entry)."""

    __slots__ = ('name', '_stat')

    def __init__(self, name: str, st: os.stat_result):
        self.name = name
        self._stat = st

    def stat(self, *, follow_symlinks: bool = True) -> os.stat_result:
        # Entries are always reported without following links, so the flag is accepted but unused.
        return self._stat

    def is_dir(self, *, follow_symlinks: bool = True) -> bool:
        return stat.S_ISDIR(self._stat.st_mode)


def _scandir_windows(dir_fd: int) -> List[_WindowsEntry]:
    # FILE_DIRECTORY_INFORMATION: NextEntryOffset, FileIndex, four FILETIMEs, EndOfFile,
    # AllocationSize, FileAttributes, FileNameLength, then the UTF-16 name at byte 64.
    layout = '<IIqqqqqqII'
    header = struct.calcsize(layout)
    handle = _win_handle(dir_fd)
    entries: List[_WindowsEntry] = []
    buffer = ctypes.create_string_buffer(_LIST_BUFFER_BYTES)
    restart = 1
    while True:
        iosb = _IoStatusBlock()
        status = _ntdll.NtQueryDirectoryFile(
            handle, None, None, None, ctypes.byref(iosb), buffer, len(buffer),
            _FILE_DIRECTORY_INFORMATION, 0, None, restart,
        )
        if (status & 0xFFFFFFFF) == _STATUS_NO_MORE_FILES:
            return entries
        _check_status(status)
        restart = 0
        data = ctypes.string_at(buffer, iosb.Information)
        offset = 0
        while True:
            (next_offset, _index, _created, _accessed, written, _changed, size, _allocated,
             attributes, name_length) = struct.unpack_from(layout, data, offset)
            name = data[offset + header: offset + header + name_length].decode('utf-16-le', 'surrogatepass')
            if name not in ('.', '..'):
                entry_stat = _windows_stat(attributes, size, written, 0, 0, 1)
                entries.append(_WindowsEntry(name, entry_stat))
            if next_offset == 0:
                break
            offset += next_offset


def _delete_entry(dir_fd: int, name: str, folder: bool) -> None:
    """
    Delete a file, link, or junction (folder=False) or an empty folder or junction (folder=True).

    The handle is opened as the link itself, so a junction or symbolic link is removed and its
    target is left alone.
    """
    fd = _adopt(
        _nt_open(dir_fd, name, _DELETE | _FILE_READ_ATTRIBUTES | _SYNCHRONIZE, _SHARE_ALL, _FILE_OPEN,
                 _OPEN_LINK_OPTIONS),
        os.O_RDONLY,
    )
    try:
        attributes = _handle_info(fd).Attributes
        is_link = bool(attributes & _FILE_ATTRIBUTE_REPARSE_POINT)
        is_directory = bool(attributes & _FILE_ATTRIBUTE_DIRECTORY)
        if folder and not is_directory:
            raise NotADirectoryError(errno.ENOTDIR, f'{name} is not a folder.')
        if not folder and is_directory and not is_link:
            raise IsADirectoryError(errno.EISDIR, f'{name} is a folder.')
        _set_disposition(fd)
    finally:
        os.close(fd)


# ---------------------------------------------------------------------------
# Public operations (identical contract on every platform)
# ---------------------------------------------------------------------------

def open_path(path: str) -> int:
    """
    Open a directory by path and return its descriptor. Used only for trusted roots (the project
    folder and Jesse's own storage folders), so links in the trusted root path are followed.
    Everything below the returned descriptor is opened with the functions in this module.
    """
    if not IS_WINDOWS:
        return os.open(path, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
    # FILE_SHARE_DELETE is omitted here as well, so the root cannot be renamed while Jesse uses it.
    handle = _kernel32.CreateFileW(
        path, _DIRECTORY_ACCESS, _SHARE_NO_DELETE, None, _OPEN_EXISTING, _FILE_FLAG_BACKUP_SEMANTICS, None,
    )
    if handle is None or handle == _INVALID_HANDLE_VALUE:
        raise ctypes.WinError(ctypes.get_last_error())
    fd = _adopt(handle, os.O_RDONLY)
    try:
        _require_kind(fd, path, directory=True)
    except BaseException:
        os.close(fd)
        raise
    return fd


def open_dir(dir_fd: int, name: str) -> int:
    """Open a child folder without following links; FileNotFoundError, ELOOP for a link, or ENOTDIR."""
    if not IS_WINDOWS:
        return os.open(name, _DIR_FLAGS, dir_fd=dir_fd)
    fd = _adopt(
        _nt_open(dir_fd, name, _DIRECTORY_ACCESS, _SHARE_NO_DELETE, _FILE_OPEN,
                 _FILE_DIRECTORY_FILE | _OPEN_LINK_OPTIONS),
        os.O_RDONLY,
    )
    try:
        _require_kind(fd, name, directory=True)
    except BaseException:
        os.close(fd)
        raise
    return fd


def make_dir(dir_fd: int, name: str, mode: int = 0o777) -> None:
    """
    Create one folder; FileExistsError when the name is taken.

    On Windows `mode` is not applied: the folder inherits its parent's ACL. Jesse does not set a
    private DACL, so access follows the parent folder's permissions.
    """
    if not IS_WINDOWS:
        os.mkdir(name, mode, dir_fd=dir_fd)
        return
    handle = _nt_open(dir_fd, name, _DIRECTORY_ACCESS, _SHARE_NO_DELETE, _FILE_CREATE,
                      _FILE_DIRECTORY_FILE | _OPEN_LINK_OPTIONS)
    os.close(_adopt(handle, os.O_RDONLY))


def lstat(dir_fd: int, name: str) -> os.stat_result:
    """Attributes of a child without following it (a link reports S_IFLNK)."""
    if not IS_WINDOWS:
        return os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
    fd = _adopt(
        _nt_open(dir_fd, name, _FILE_READ_ATTRIBUTES | _SYNCHRONIZE, _SHARE_ALL, _FILE_OPEN, _OPEN_LINK_OPTIONS),
        os.O_RDONLY,
    )
    try:
        return _stat_from_handle(fd)
    finally:
        os.close(fd)


def scandir(dir_fd: int) -> list:
    """
    The entries of a folder, each with `name`, `stat(follow_symlinks=False)` and
    `is_dir(follow_symlinks=False)`. The POSIX entries remain valid only while `dir_fd` is open.
    """
    if not IS_WINDOWS:
        with os.scandir(dir_fd) as iterator:
            return list(iterator)
    return _scandir_windows(dir_fd)


def open_read(dir_fd: int, name: str) -> int:
    """Open an existing child for reading. On POSIX a folder opens and is refused by the caller's fstat."""
    if not IS_WINDOWS:
        return os.open(name, _FILE_READ_FLAGS, dir_fd=dir_fd)
    fd = _adopt(
        _nt_open(dir_fd, name, _FILE_READ_DATA | _FILE_READ_ATTRIBUTES | _SYNCHRONIZE, _SHARE_ALL, _FILE_OPEN,
                 _OPEN_LINK_OPTIONS),
        os.O_RDONLY | os.O_BINARY,
    )
    try:
        _require_kind(fd, name, directory=False)
    except BaseException:
        os.close(fd)
        raise
    return fd


def create_file(dir_fd: int, name: str, mode: int = 0o666) -> int:
    """
    Create a new file for writing; FileExistsError if the name is taken, including by a link.

    On Windows `mode` is not applied; the file takes its parent folder's inherited ACL (see make_dir).
    """
    if not IS_WINDOWS:
        return os.open(name, _FILE_CREATE_FLAGS, mode, dir_fd=dir_fd)
    return _adopt(
        _nt_open(dir_fd, name, _FILE_WRITE_DATA | _FILE_READ_ATTRIBUTES | _SYNCHRONIZE, _SHARE_ALL, _FILE_CREATE,
                 _FILE_NON_DIRECTORY_FILE | _OPEN_LINK_OPTIONS, _FILE_ATTRIBUTE_NORMAL),
        os.O_WRONLY | os.O_BINARY,
    )


def read_at(fd: int, size: int, offset: int) -> bytes:
    """Read at `offset`: POSIX uses pread; Windows callers supply a private descriptor for seeking."""
    if not IS_WINDOWS:
        return os.pread(fd, size, offset)
    os.lseek(fd, offset, os.SEEK_SET)
    chunks = []
    remaining = size
    while remaining > 0:
        chunk = os.read(fd, remaining)
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    return b''.join(chunks)


def unlink(dir_fd: int, name: str) -> None:
    """Remove a file or a link (never its target). Folders are refused; use rmdir."""
    if not IS_WINDOWS:
        os.unlink(name, dir_fd=dir_fd)
        return
    _delete_entry(dir_fd, name, folder=False)


def rmdir(dir_fd: int, name: str) -> None:
    """Remove an empty folder or junction; OSError ENOTEMPTY when it has contents."""
    if not IS_WINDOWS:
        os.rmdir(name, dir_fd=dir_fd)
        return
    _delete_entry(dir_fd, name, folder=True)


def rename(src_dir_fd: int, src: str, dst_dir_fd: int, dst: str, *, replace: bool) -> None:
    """
    Move a child to a new name, atomically, without following links.

    With `replace`, an existing destination file is replaced (and a link at the destination is
    replaced, not followed). Without it, an existing destination raises FileExistsError and is
    never changed. Callers check the destination's type first; folders replace only empty folders
    on POSIX.
    """
    if not IS_WINDOWS:
        if replace:
            os.replace(src, dst, src_dir_fd=src_dir_fd, dst_dir_fd=dst_dir_fd)
            return
        if stat.S_ISDIR(os.stat(src, dir_fd=src_dir_fd, follow_symlinks=False).st_mode):
            # rename(2) cannot hard-link a folder. It replaces an empty destination folder, a race
            # the folder-move and folder-copy callers already accept.
            os.rename(src, dst, src_dir_fd=src_dir_fd, dst_dir_fd=dst_dir_fd)
            return
        try:
            os.link(src, dst, src_dir_fd=src_dir_fd, dst_dir_fd=dst_dir_fd, follow_symlinks=False)
        except FileExistsError:
            raise
        except OSError as exc:
            if exc.errno not in _NO_HARD_LINK_ERRNOS:
                raise
            rename_into_reserved_name(src_dir_fd, src, dst_dir_fd, dst)
            return
        os.unlink(src, dir_fd=src_dir_fd)
        return

    encoded = _windows_name(dst)
    fd = _adopt(
        _nt_open(src_dir_fd, src, _DELETE | _FILE_READ_ATTRIBUTES | _SYNCHRONIZE, _SHARE_ALL, _FILE_OPEN,
                 _OPEN_LINK_OPTIONS),
        os.O_RDONLY,
    )
    try:
        info = _RenameInformation()
        # _windows_name already limits this to MAX_NAME_LENGTH units; the check guards the fixed buffer.
        if len(encoded) > ctypes.sizeof(info.FileName):
            raise OSError(errno.ENAMETOOLONG, f'{dst!r} is too long for a Windows file name.')
        info.ReplaceIfExists = 1 if replace else 0
        info.RootDirectory = _win_handle(dst_dir_fd)
        info.FileNameLength = len(encoded)
        ctypes.memmove(info.FileName, encoded, len(encoded))
        iosb = _IoStatusBlock()
        status = _ntdll.NtSetInformationFile(
            _win_handle(fd), ctypes.byref(iosb), ctypes.addressof(info), ctypes.sizeof(info),
            _FILE_RENAME_INFORMATION,
        )
        _check_status(status)
    finally:
        os.close(fd)


def rename_into_reserved_name(src_fd: int, src_name: str, dst_fd: int, dst_name: str,
                              dst_display: Optional[str] = None) -> None:
    """
    POSIX fallback for no-clobber renames on filesystems without hard links.

    The destination name is first claimed with an exclusive create (which fails if anything,
    including a symlink, already has that name), then the source is renamed over that empty
    placeholder. A file created concurrently by someone else is therefore never replaced; the only
    visible intermediate state is our own empty placeholder. If the rename fails, the placeholder is
    removed only while it is still the file we created.
    """
    display = dst_display or dst_name
    try:
        placeholder = create_file(dst_fd, dst_name)
    except FileExistsError:
        raise FileExistsError(errno.EEXIST, f'{display} already exists.')
    try:
        ours = os.fstat(placeholder)
    finally:
        os.close(placeholder)
    try:
        os.rename(src_name, dst_name, src_dir_fd=src_fd, dst_dir_fd=dst_fd)
    except BaseException:
        current = _posix_lstat_or_none(dst_fd, dst_name)
        if current is not None and (current.st_dev, current.st_ino) == (ours.st_dev, ours.st_ino):
            try:
                os.unlink(dst_name, dir_fd=dst_fd)
            except FileNotFoundError:
                pass
        raise


def _posix_lstat_or_none(dir_fd: int, name: str) -> Optional[os.stat_result]:
    try:
        return os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None
