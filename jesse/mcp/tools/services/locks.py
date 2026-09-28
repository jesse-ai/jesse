"""
MCP-only locks that keep a few Jesse API operations one at a time within this MCP worker.

The tools run their API calls in worker threads (jesse/mcp/tools/offload.py), so calls from
parallel requests or sessions overlap in the Jesse API. Most routes are safe to overlap:
drafts get fresh UUIDs, session state and notes are field-level UPDATEs, stored candles have
a unique index, and reports are written with an exclusive create. The routes below check and
then write without a lock or constraint, so each lock keeps this worker's own calls to them
one at a time. The locks cover this worker's calls only; the dashboard and other API clients
can still reach the same routes concurrently.

- CONFIG_LOCK: /config/get saves back the whole config row it read
  (jesse.modes.data_provider.get_config), so a read overlapping /config/update can write the
  old settings back and silently undo the update. Held for every /config/get and
  /config/update request, including the run-config lookups of the draft and run tools.
- CREDENTIALS_LOCK: storing and deleting check first (name taken, key present) and then
  write, so overlapping calls could answer a generic Jesse error instead of "name_taken", or
  delete one key twice with both calls reporting success.
- STRATEGY_FILES_LOCK: create_strategy makes strategies/<Name> from the template
  (/strategy/make) and fills in its code with a second request (/strategy/save), while
  /strategy/import checks that the folder is missing and then writes into it with
  makedirs(exist_ok=True). An import overlapping a create of the same name could leave both
  reporting success with one's code replacing the other's, and two overlapping creates could
  answer a generic 500 instead of "strategy_exists". Held by create_strategy for both
  requests and by import_catalog_strategy.

The locks are threading locks taken inside worker threads, never on the event loop, and no
code holds one while taking another.
"""
import functools
import threading
from typing import Any, Callable, TypeVar

T = TypeVar('T')

CONFIG_LOCK = threading.Lock()
CREDENTIALS_LOCK = threading.Lock()
STRATEGY_FILES_LOCK = threading.Lock()


def serialized(lock: threading.Lock, func: Callable[..., T]) -> Callable[..., T]:
    """Return `func` holding `lock` for the whole call; keeps its name for the offload log."""

    @functools.wraps(func)
    def call(*args: Any, **kwargs: Any) -> T:
        with lock:
            return func(*args, **kwargs)

    return call
