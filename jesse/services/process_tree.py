"""
Process-tree supervision for background jobs: one handle that reaches every process a job starts.

POSIX: the job leads its own process group (start_new_session), so killpg() reaches members the
script left running after it exited. A group ID can be reused by an unrelated process once its last
member exits, so after the first failed signal the group is never signalled again.

Windows: a Job Object with KILL_ON_JOB_CLOSE. The child is created already assigned to the job
through PROC_THREAD_ATTRIBUTE_JOB_LIST (Windows 10 and later), so it never runs outside the job, not
even for an instant; there is no suspended-then-assign window. Breakaway is never permitted, so every
descendant stays in the job. Only the job's handle closes with Jesse, and it is not inherited, so
when Jesse's process ends for any reason, including a crash, the kernel kills the whole tree.
Membership is tracked by the kernel, so there is no PID to race against and no unrelated process can
be signalled. Windows has no catchable termination for an arbitrary process, so stopping a job
terminates the job at once; the POSIX SIGTERM grace period does not apply.
"""
import ctypes
import errno
import os
import signal
import subprocess
from typing import Any, List, Mapping, Optional

IS_WINDOWS = os.name == 'nt'

# SIGKILL does not exist on Windows. Where it is missing, the value is only an argument: Windows stops
# a job the same way for every signal other than 0 (see ProcessTree.signal).
FORCE_KILL = signal.SIGKILL if hasattr(signal, 'SIGKILL') else signal.SIGTERM

if IS_WINDOWS:
    import msvcrt

    _kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)

    _EXTENDED_STARTUPINFO_PRESENT = 0x00080000
    _CREATE_UNICODE_ENVIRONMENT = 0x00000400
    _STARTF_USESTDHANDLES = 0x00000100
    # PROC_THREAD_ATTRIBUTE_NUMBER | PROC_THREAD_ATTRIBUTE_INPUT for the two attributes used here.
    _PROC_THREAD_ATTRIBUTE_HANDLE_LIST = 0x00020002
    _PROC_THREAD_ATTRIBUTE_JOB_LIST = 0x0002000D
    _ERROR_INSUFFICIENT_BUFFER = 122
    _GENERIC_READ = 0x80000000
    _FILE_SHARE_READ_WRITE = 0x00000003
    _FILE_ATTRIBUTE_NORMAL = 0x00000080
    _OPEN_EXISTING = 3
    _HANDLE_FLAG_INHERIT = 0x00000001
    _JOB_OBJECT_BASIC_ACCOUNTING_INFORMATION = 1
    _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
    _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
    _WAIT_OBJECT_0 = 0
    _WAIT_TIMEOUT = 0x00000102
    _INFINITE = 0xFFFFFFFF
    _INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

    class _SecurityAttributes(ctypes.Structure):
        _fields_ = [('nLength', ctypes.c_uint32), ('lpSecurityDescriptor', ctypes.c_void_p),
                    ('bInheritHandle', ctypes.c_int)]

    class _StartupInfoW(ctypes.Structure):
        _fields_ = [
            ('cb', ctypes.c_uint32), ('lpReserved', ctypes.c_void_p), ('lpDesktop', ctypes.c_void_p),
            ('lpTitle', ctypes.c_void_p), ('dwX', ctypes.c_uint32), ('dwY', ctypes.c_uint32),
            ('dwXSize', ctypes.c_uint32), ('dwYSize', ctypes.c_uint32), ('dwXCountChars', ctypes.c_uint32),
            ('dwYCountChars', ctypes.c_uint32), ('dwFillAttribute', ctypes.c_uint32), ('dwFlags', ctypes.c_uint32),
            ('wShowWindow', ctypes.c_uint16), ('cbReserved2', ctypes.c_uint16), ('lpReserved2', ctypes.c_void_p),
            ('hStdInput', ctypes.c_void_p), ('hStdOutput', ctypes.c_void_p), ('hStdError', ctypes.c_void_p),
        ]

    class _StartupInfoExW(ctypes.Structure):
        _fields_ = [('StartupInfo', _StartupInfoW), ('lpAttributeList', ctypes.c_void_p)]

    class _ProcessInformation(ctypes.Structure):
        _fields_ = [('hProcess', ctypes.c_void_p), ('hThread', ctypes.c_void_p),
                    ('dwProcessId', ctypes.c_uint32), ('dwThreadId', ctypes.c_uint32)]

    class _IoCounters(ctypes.Structure):
        _fields_ = [(name, ctypes.c_uint64) for name in (
            'ReadOperationCount', 'WriteOperationCount', 'OtherOperationCount',
            'ReadTransferCount', 'WriteTransferCount', 'OtherTransferCount',
        )]

    class _BasicLimitInformation(ctypes.Structure):
        _fields_ = [
            ('PerProcessUserTimeLimit', ctypes.c_int64), ('PerJobUserTimeLimit', ctypes.c_int64),
            ('LimitFlags', ctypes.c_uint32), ('MinimumWorkingSetSize', ctypes.c_size_t),
            ('MaximumWorkingSetSize', ctypes.c_size_t), ('ActiveProcessLimit', ctypes.c_uint32),
            ('Affinity', ctypes.c_size_t), ('PriorityClass', ctypes.c_uint32), ('SchedulingClass', ctypes.c_uint32),
        ]

    class _ExtendedLimitInformation(ctypes.Structure):
        _fields_ = [
            ('BasicLimitInformation', _BasicLimitInformation), ('IoInfo', _IoCounters),
            ('ProcessMemoryLimit', ctypes.c_size_t), ('JobMemoryLimit', ctypes.c_size_t),
            ('PeakProcessMemoryUsed', ctypes.c_size_t), ('PeakJobMemoryUsed', ctypes.c_size_t),
        ]

    class _BasicAccountingInformation(ctypes.Structure):
        _fields_ = [
            ('TotalUserTime', ctypes.c_int64), ('TotalKernelTime', ctypes.c_int64),
            ('ThisPeriodTotalUserTime', ctypes.c_int64), ('ThisPeriodTotalKernelTime', ctypes.c_int64),
            ('TotalPageFaultCount', ctypes.c_uint32), ('TotalProcesses', ctypes.c_uint32),
            ('ActiveProcesses', ctypes.c_uint32), ('TotalTerminatedProcesses', ctypes.c_uint32),
        ]

    _kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
    _kernel32.CreateJobObjectW.restype = ctypes.c_void_p
    _kernel32.SetInformationJobObject.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
    _kernel32.SetInformationJobObject.restype = ctypes.c_int
    _kernel32.QueryInformationJobObject.argtypes = [
        ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p,
    ]
    _kernel32.QueryInformationJobObject.restype = ctypes.c_int
    _kernel32.TerminateJobObject.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    _kernel32.TerminateJobObject.restype = ctypes.c_int
    _kernel32.CreateFileW.argtypes = [
        ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32,
        ctypes.c_void_p,
    ]
    _kernel32.CreateFileW.restype = ctypes.c_void_p
    _kernel32.CreatePipe.argtypes = [
        ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p, ctypes.c_uint32,
    ]
    _kernel32.CreatePipe.restype = ctypes.c_int
    _kernel32.SetHandleInformation.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32]
    _kernel32.SetHandleInformation.restype = ctypes.c_int
    _kernel32.InitializeProcThreadAttributeList.argtypes = [
        ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.POINTER(ctypes.c_size_t),
    ]
    _kernel32.InitializeProcThreadAttributeList.restype = ctypes.c_int
    _kernel32.UpdateProcThreadAttribute.argtypes = [
        ctypes.c_void_p, ctypes.c_uint32, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t,
        ctypes.c_void_p, ctypes.c_void_p,
    ]
    _kernel32.UpdateProcThreadAttribute.restype = ctypes.c_int
    _kernel32.DeleteProcThreadAttributeList.argtypes = [ctypes.c_void_p]
    _kernel32.DeleteProcThreadAttributeList.restype = None
    _kernel32.CreateProcessW.argtypes = [
        ctypes.c_wchar_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_uint32,
        ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_void_p, ctypes.c_void_p,
    ]
    _kernel32.CreateProcessW.restype = ctypes.c_int
    _kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    _kernel32.WaitForSingleObject.restype = ctypes.c_uint32
    _kernel32.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
    _kernel32.GetExitCodeProcess.restype = ctypes.c_int
    _kernel32.TerminateProcess.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    _kernel32.TerminateProcess.restype = ctypes.c_int
    _kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    _kernel32.CloseHandle.restype = ctypes.c_int


class ProcessTree:
    """A started job's process and the handle that reaches all of its processes."""

    def __init__(self, process: Any, job: Optional[int] = None):
        # subprocess.Popen on POSIX; _WindowsProcess on Windows. Both provide pid, stdout, wait, kill.
        self.process = process
        self._job = job
        # POSIX only: set once a signal to the group fails because no member is left. After that
        # the group ID may be reused by an unrelated process, so it is never signalled again.
        self.group_gone = False

    @property
    def pid(self) -> int:
        return self.process.pid

    def signal(self, sig: int) -> bool:
        """
        Send `sig` to every member; False once none is left.

        POSIX: killpg(pid, sig); signal 0 only probes the group. Windows: signal 0 reports whether
        any member is alive, and any other signal terminates the job (there is no graceful
        equivalent), so sig's value is otherwise ignored.
        """
        if IS_WINDOWS:
            return _signal_job(self._job, sig)
        if self.group_gone:
            return False
        try:
            os.killpg(self.pid, sig)
            return True
        except (ProcessLookupError, PermissionError):
            # PermissionError: the ID now belongs to another user's group, so ours is gone.
            self.group_gone = True
            return False

    def close(self) -> None:
        """
        Release the process and job handles. Closing the job ends any member still running (kill on close).
        Call only after supervision has finished with the process.
        """
        if not IS_WINDOWS:
            return
        if isinstance(self.process, _WindowsProcess):
            self.process.close()
        if self._job is not None:
            _kernel32.CloseHandle(self._job)
            self._job = None


def spawn(argv: List[str], *, cwd: str, env: Mapping[str, str], stdin: Any, stdout: Any, stderr: Any) -> ProcessTree:
    """
    Start `argv` without a shell in its own process tree. Raises OSError if it cannot be started,
    and never leaves a started process outside the tree.

    Windows supports only the configuration the jobs use: stdin from the null device, stdout piped,
    and stderr merged into stdout.
    """
    if not IS_WINDOWS:
        process = subprocess.Popen(
            argv, cwd=cwd, env=dict(env), stdin=stdin, stdout=stdout, stderr=stderr,
            shell=False, start_new_session=True,
        )
        return ProcessTree(process)
    if stdin != subprocess.DEVNULL or stdout != subprocess.PIPE or stderr != subprocess.STDOUT:
        raise ValueError('Windows job processes support only stdin=DEVNULL, stdout=PIPE, stderr=STDOUT.')
    return _spawn_windows(argv, cwd, env)


# ---------------------------------------------------------------------------
# Windows
# ---------------------------------------------------------------------------

class _WindowsProcess:
    """
    The part of subprocess.Popen the supervisor uses, for a process created with its job already
    assigned. Popen cannot pass a PROC_THREAD_ATTRIBUTE_JOB_LIST, so this wraps CreateProcessW.
    """

    def __init__(self, pid: int, handle: int, args: List[str], stdout: Any):
        self.pid = pid
        self.args = args
        self.stdout = stdout
        self.returncode: Optional[int] = None
        self._handle: Optional[int] = handle

    def wait(self, timeout: Optional[float] = None) -> int:
        if self.returncode is not None:
            return self.returncode
        if self._handle is None:
            raise OSError(errno.EBADF, 'The process handle is closed.')
        milliseconds = _INFINITE if timeout is None else max(0, int(timeout * 1000))
        result = _kernel32.WaitForSingleObject(self._handle, milliseconds)
        if result == _WAIT_TIMEOUT:
            raise subprocess.TimeoutExpired(self.args, timeout)
        if result != _WAIT_OBJECT_0:
            raise ctypes.WinError(ctypes.get_last_error())
        code = ctypes.c_uint32()
        if not _kernel32.GetExitCodeProcess(self._handle, ctypes.byref(code)):
            raise ctypes.WinError(ctypes.get_last_error())
        self.returncode = code.value
        return code.value

    def poll(self) -> Optional[int]:
        try:
            return self.wait(0)
        except subprocess.TimeoutExpired:
            return None

    def kill(self) -> None:
        # Terminating a process that already exited fails with access denied; that is not an error.
        if self._handle is None or not _kernel32.TerminateProcess(self._handle, 1):
            if self.poll() is None:
                raise ctypes.WinError(ctypes.get_last_error())

    def close(self) -> None:
        if self._handle is not None:
            _kernel32.CloseHandle(self._handle)
            self._handle = None


def _environment_block(env: Mapping[str, str]) -> str:
    """
    The UTF-16 environment block CreateProcessW expects: NAME=value entries, each NUL-terminated,
    sorted case-insensitively as subprocess does, and one more NUL at the end.
    """
    entries = sorted(env.items(), key=lambda item: item[0].upper())
    return ''.join(f'{key}={value}\0' for key, value in entries) + '\0'


def _create_job() -> int:
    job = _kernel32.CreateJobObjectW(None, None)
    if not job:
        raise ctypes.WinError(ctypes.get_last_error())
    info = _ExtendedLimitInformation()
    info.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not _kernel32.SetInformationJobObject(
        job, _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION, ctypes.byref(info), ctypes.sizeof(info),
    ):
        error = ctypes.get_last_error()
        _kernel32.CloseHandle(job)
        raise ctypes.WinError(error)
    return job


def _open_null_device() -> int:
    """The NUL device for stdin, inheritable so the child receives it through the handle list."""
    security = _SecurityAttributes(ctypes.sizeof(_SecurityAttributes), None, 1)
    handle = _kernel32.CreateFileW(
        'NUL', _GENERIC_READ, _FILE_SHARE_READ_WRITE, ctypes.addressof(security), _OPEN_EXISTING,
        _FILE_ATTRIBUTE_NORMAL, None,
    )
    if not handle or handle == _INVALID_HANDLE_VALUE:
        raise ctypes.WinError(ctypes.get_last_error())
    return handle


def _create_pipe() -> tuple:
    """
    An anonymous pipe as (read, write). Only the write end is inherited by the child; the read end
    stays private to Jesse, so the child cannot hold it open after it exits.
    """
    security = _SecurityAttributes(ctypes.sizeof(_SecurityAttributes), None, 1)
    read_handle = ctypes.c_void_p()
    write_handle = ctypes.c_void_p()
    if not _kernel32.CreatePipe(ctypes.byref(read_handle), ctypes.byref(write_handle),
                                ctypes.addressof(security), 0):
        raise ctypes.WinError(ctypes.get_last_error())
    if not _kernel32.SetHandleInformation(read_handle, _HANDLE_FLAG_INHERIT, 0):
        error = ctypes.get_last_error()
        _close_all([read_handle.value, write_handle.value])
        raise ctypes.WinError(error)
    return read_handle.value, write_handle.value


def _close_all(handles: List[Optional[int]]) -> None:
    for handle in handles:
        if handle:
            _kernel32.CloseHandle(handle)


def _spawn_windows(argv: List[str], cwd: str, env: Mapping[str, str]) -> ProcessTree:
    job = _create_job()
    handles: List[Optional[int]] = []
    try:
        null_input = _open_null_device()
        handles.append(null_input)
        read_end, write_end = _create_pipe()
        handles.extend([read_end, write_end])

        # Only these two handles are inherited. Python already makes other handles non-inheritable,
        # and the list keeps the job handle and any other private handle out of the child.
        inherited = (ctypes.c_void_p * 2)(null_input, write_end)
        jobs = (ctypes.c_void_p * 1)(job)
        size = ctypes.c_size_t(0)
        # The first call only reports the buffer size; it is expected to fail with insufficient buffer.
        _kernel32.InitializeProcThreadAttributeList(None, 2, 0, ctypes.byref(size))
        # The attribute list must be pointer-aligned, which a byte buffer does not guarantee.
        pointer_slots = (size.value + ctypes.sizeof(ctypes.c_void_p) - 1) // ctypes.sizeof(ctypes.c_void_p)
        attribute_buffer = (ctypes.c_void_p * pointer_slots)()
        attributes = ctypes.addressof(attribute_buffer)
        if not _kernel32.InitializeProcThreadAttributeList(attributes, 2, 0, ctypes.byref(size)):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            if not _kernel32.UpdateProcThreadAttribute(
                attributes, 0, _PROC_THREAD_ATTRIBUTE_HANDLE_LIST, ctypes.addressof(inherited),
                ctypes.sizeof(inherited), None, None,
            ):
                raise ctypes.WinError(ctypes.get_last_error())
            # JOB_LIST makes the new process a member of the job before its first thread runs.
            if not _kernel32.UpdateProcThreadAttribute(
                attributes, 0, _PROC_THREAD_ATTRIBUTE_JOB_LIST, ctypes.addressof(jobs),
                ctypes.sizeof(jobs), None, None,
            ):
                raise ctypes.WinError(ctypes.get_last_error())

            startup = _StartupInfoExW()
            startup.StartupInfo.cb = ctypes.sizeof(_StartupInfoExW)
            startup.StartupInfo.dwFlags = _STARTF_USESTDHANDLES
            startup.StartupInfo.hStdInput = null_input
            startup.StartupInfo.hStdOutput = write_end
            startup.StartupInfo.hStdError = write_end
            startup.lpAttributeList = attributes

            command_line = ctypes.create_unicode_buffer(subprocess.list2cmdline(argv))
            environment = ctypes.create_unicode_buffer(_environment_block(env))
            info = _ProcessInformation()
            created = _kernel32.CreateProcessW(
                None, ctypes.addressof(command_line), None, None, 1,
                _EXTENDED_STARTUPINFO_PRESENT | _CREATE_UNICODE_ENVIRONMENT,
                ctypes.addressof(environment), cwd, ctypes.addressof(startup), ctypes.addressof(info),
            )
            if not created:
                raise ctypes.WinError(ctypes.get_last_error())
        finally:
            _kernel32.DeleteProcThreadAttributeList(attributes)

        # The child owns its copies now. Jesse's write end must close, or reading the pipe never
        # reaches end-of-file after the child and its descendants exit.
        _close_all([null_input, write_end, info.hThread])
        handles.clear()
        # The child is already running in the job, so every failure below stops it before the job
        # handle is released by the outer handler.
        try:
            descriptor = msvcrt.open_osfhandle(read_end, os.O_RDONLY | os.O_BINARY)
        except BaseException:
            _kernel32.TerminateJobObject(job, 1)
            _close_all([read_end, info.hProcess])
            raise
        try:
            # From here the CRT descriptor owns read_end: os.close releases it, and the pump's
            # file object does the same at end-of-output.
            stdout = os.fdopen(descriptor, 'rb')
        except BaseException:
            _kernel32.TerminateJobObject(job, 1)
            os.close(descriptor)
            _close_all([info.hProcess])
            raise
        return ProcessTree(_WindowsProcess(info.dwProcessId, info.hProcess, argv, stdout), job)
    except BaseException:
        _close_all(handles)
        _kernel32.CloseHandle(job)
        raise


def _signal_job(job: Optional[int], sig: int) -> bool:
    if job is None:
        return False
    alive = _active_processes(job)
    if sig == 0:
        return alive > 0
    if alive == 0:
        return False
    if not _kernel32.TerminateJobObject(job, 1):
        raise ctypes.WinError(ctypes.get_last_error())
    return True


def _active_processes(job: int) -> int:
    info = _BasicAccountingInformation()
    if not _kernel32.QueryInformationJobObject(
        job, _JOB_OBJECT_BASIC_ACCOUNTING_INFORMATION, ctypes.byref(info), ctypes.sizeof(info), None,
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    return info.ActiveProcesses
