import os
import pickle
import tempfile
from contextlib import contextmanager
from time import sleep, time
from typing import Any
from functools import lru_cache

import jesse.helpers as jh

try:
    import fcntl
except ImportError:  # Windows
    fcntl = None
    import msvcrt

# Runner jobs run in a folder of their own; this points their cache at the runner project's
# storage/temp/ instead (see services/runner_worker.py). Processes the job starts inherit it.
CACHE_DIR_ENV = 'JESSE_CACHE_DIR'
INDEX_NAME = 'cache_database.pickle'


class Cache:
    """
    A file cache of pickled values (candles loaded from the database) in one folder per machine.

    Several processes use the same folder at once (parallel backtests, a runner's jobs), so each
    value file is written whole before it replaces the old one, and the index of expiry times
    (cache_database.pickle) is read again and merged under a file lock every time it changes.
    """

    def __init__(self, path: str) -> None:
        self.driver = jh.get_config('env.caching.driver', 'pickle')
        self.db = {}
        self.use_path(path)

    def use_path(self, path: str) -> None:
        self.path = os.path.join(path, '')
        if self.driver == 'pickle':
            os.makedirs(self.path, exist_ok=True)
            self.db = self._read_db()

    def _data_path(self, key: str) -> str:
        return f"{self.path}{key}.pickle"

    def set_value(self, key: str, data: Any, expire_seconds: int = 60 * 60) -> None:
        if self.driver is None:
            return

        # store the file first, so the index never points to a missing or half-written one
        data_path = self._data_path(key)
        self._write_atomically(data_path, data)

        expire_at = None if expire_seconds is None else time() + expire_seconds
        with self._locked_db():
            self.db[key] = {
                'expire_seconds': expire_seconds,
                'expire_at': expire_at,
                'path': data_path,
            }

    def get_value(self, key: str) -> Any:
        if self.driver is None:
            raise ValueError('Caching driver is not set.')

        item = self.db.get(key)
        if item is None:
            # another process may have stored it since this one read the index
            self.db = self._read_db()
            item = self.db.get(key)
            if item is None:
                return False

        data_path = self._data_path(key)

        # if expired, remove file, and database record
        if item['expire_at'] is not None and time() > item['expire_at']:
            self._forget(key)
            return False

        try:
            with open(data_path, 'rb') as f:
                cache_value = pickle.load(f)
        except (EOFError, pickle.UnpicklingError, FileNotFoundError):
            # If the file is missing or broken, remove the record and return False
            self._forget(key)
            return False

        # renew cache expiration time
        if item['expire_at'] is not None:
            with self._locked_db():
                if key in self.db and self.db[key]['expire_at'] is not None:
                    self.db[key]['expire_at'] = time() + self.db[key]['expire_seconds']

        return cache_value

    def _forget(self, key: str) -> None:
        with self._locked_db():
            self.db.pop(key, None)
            try:
                os.remove(self._data_path(key))
            except FileNotFoundError:
                pass

    def _read_db(self) -> dict:
        try:
            with open(f"{self.path}{INDEX_NAME}", 'rb') as f:
                db = pickle.load(f)
        except FileNotFoundError:
            return {}
        except (EOFError, pickle.UnpicklingError, UnicodeDecodeError):
            # File got broken
            return {}
        return db if isinstance(db, dict) else {}

    @contextmanager
    def _locked_db(self):
        """Read the index again under the lock, let the caller change self.db, then store it."""
        with open(f"{self.path}cache_database.lock", 'a+b') as lock:
            _lock(lock)
            try:
                self.db = self._read_db()
                yield
                self._write_atomically(f"{self.path}{INDEX_NAME}", self.db)
            finally:
                _unlock(lock)

    def _write_atomically(self, path: str, data: Any) -> None:
        descriptor, temporary = tempfile.mkstemp(dir=self.path, suffix='.tmp')
        try:
            with os.fdopen(descriptor, 'wb') as f:
                pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)
            for attempt in range(100):
                try:
                    os.replace(temporary, path)
                    break
                except PermissionError:
                    # Windows refuses while another process is reading the file
                    if attempt == 99:
                        raise
                    sleep(0.05)
        except BaseException:
            try:
                os.remove(temporary)
            except FileNotFoundError:
                pass
            raise

    def flush(self) -> None:
        if self.driver is None:
            return

        # Every value file in the folder, including ones the index lost track of
        with self._locked_db():
            for name in os.listdir(self.path):
                if name.endswith('.pickle') and name != INDEX_NAME:
                    try:
                        os.remove(f"{self.path}{name}")
                    except FileNotFoundError:
                        pass
            self.db = {}


def _lock(f) -> None:
    if fcntl is not None:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
    else:
        f.seek(0)
        while True:
            try:
                msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)
                return
            except OSError:  # LK_LOCK gives up after 10 seconds
                continue


def _unlock(f) -> None:
    if fcntl is not None:
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    else:
        f.seek(0)
        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)


cache = Cache(os.environ.get(CACHE_DIR_ENV) or "storage/temp/")


# Using functools.lru_cache
def cached(method):
    def decorated(self, *args, **kwargs):
        cached_method = self._cached_methods.get(method)
        if cached_method is None:
            cached_method = lru_cache()(method)
            self._cached_methods[method] = cached_method
        return cached_method(self, *args, **kwargs)

    return decorated
