import datetime
import os
import sqlite3


def process_exited(pid: int) -> bool:
    """
    True once `pid` has exited, without disturbing a live process.

    POSIX probes with signal 0. On Windows os.kill(pid, 0) is not a probe: 0 is CTRL_C_EVENT, so it
    would send Ctrl+C to the console. The process is observed through a SYNCHRONIZE handle instead.
    A PID that names no process at all (ERROR_INVALID_PARAMETER) counts as exited.
    """
    if os.name != 'nt':
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        return False

    import ctypes

    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    kernel32.WaitForSingleObject.restype = ctypes.c_uint32
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.restype = ctypes.c_int
    synchronize, query_limited = 0x00100000, 0x1000
    handle = kernel32.OpenProcess(synchronize | query_limited, False, pid)
    if not handle:
        error = ctypes.get_last_error()
        if error == 87:  # ERROR_INVALID_PARAMETER
            return True
        raise ctypes.WinError(error)
    try:
        result = kernel32.WaitForSingleObject(handle, 0)
        failed = ctypes.get_last_error()
    finally:
        kernel32.CloseHandle(handle)
    if result == 0:  # WAIT_OBJECT_0: the process has terminated
        return True
    if result == 0x102:  # WAIT_TIMEOUT: still running
        return False
    raise ctypes.WinError(failed)


def pytest_configure(config):
    # Route tests share the fully registered app, while production CLI imports
    # stay lightweight until startup has reserved its port and prepared services.
    import jesse.app

    # SQLite unit fixtures retain the standard ISO format without Python 3.12's
    # deprecated implicit datetime adapter. Production PostgreSQL is unaffected.
    sqlite3.register_adapter(datetime.datetime, lambda value: value.isoformat(' '))

    config.addinivalue_line(
        'markers',
        'slow: long-running regression backtests (deselect with -m "not slow")',
    )
