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
- LIVE_SESSIONS_LOCK: updating, starting, and deleting a live/paper session read its stored
  form, check it (a draft, running or not, open in a dashboard tab), and then write through
  /live/update-state, /live, or /live/sessions/{id}/remove. /live/update-state replaces the
  whole stored form, so two overlapping updates of one draft would lose one's changes, and a
  start overlapping an update would start (and store) the form it read before the update.
  Held for each of those whole read-check-write sequences. Creating and copying a draft write a
  new ID only, so they do not take it. Stopping does not take it either, so a stop never queues
  behind another call (/live/cancel is harmless to repeat or overlap). Against every API
  caller, including the dashboard, the /live routes protect themselves: starting, stopping,
  deleting, and saving a form are ordered by live_controller._LIFECYCLE_LOCK, and the routes
  refuse to delete or rewrite a session that is starting or running.

The locks are threading locks taken inside worker threads, never on the event loop. Only the
live tools take a second lock while holding one: they read settings under CONFIG_LOCK while
holding LIVE_SESSIONS_LOCK, and nothing takes them in the opposite order.
"""
import functools
import threading
from typing import Any, Callable, TypeVar

T = TypeVar('T')

CONFIG_LOCK = threading.Lock()
CREDENTIALS_LOCK = threading.Lock()
STRATEGY_FILES_LOCK = threading.Lock()
LIVE_SESSIONS_LOCK = threading.Lock()


def serialized(lock: threading.Lock, func: Callable[..., T]) -> Callable[..., T]:
    """Return `func` holding `lock` for the whole call; keeps its name for the offload log."""

    @functools.wraps(func)
    def call(*args: Any, **kwargs: Any) -> T:
        with lock:
            return func(*args, **kwargs)

    return call
