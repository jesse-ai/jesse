"""
Worker-thread offloading for MCP tools whose work blocks: Jesse API requests, local file
reads, CSV cleaning, and usage metering.

FastMCP (SDK 1.28) calls a synchronous tool function directly on the worker's event loop, so
while it waits nothing else on that worker runs: no other session's request, no ping, not
even the client's cancellation notice. Tools that `await run_blocking(service, ...)` keep the
event loop free while the unchanged synchronous service function runs in an AnyIO worker
thread. Only list_indicators, get_indicator_details, and get_exchange_api_key_requirements
stay synchronous: they only inspect loaded code and in-memory tables, taking well under a
millisecond (the first indicator call also imports jesse.indicators, about 10 ms), which a
thread hand-off would not shorten.

Thread safety: the services read the worker's startup configuration (jesse.mcp.mcp_config)
and Jesse's loaded environment values, build their results from local variables, and make
independent `requests` calls (the optional local usage meter uses redis-py, whose client is
thread-safe); a few also read project files relative to the working directory, which the
worker never changes. Several can therefore run at once, and the Jesse
API already serves its routes concurrently for the dashboard. The few routes that are unsafe
to overlap are serialized by the locks in services/locks.py.

Thread limit: AnyIO's default limiter for the worker's event loop (40 threads), shared with
anything else that offloads to threads there; further calls wait for a free slot.

Cancellation (MCP notifications/cancelled, a closed session, or worker shutdown):
- A call cancelled before its thread starts never runs: nothing is metered or sent to Jesse.
- A started call is never abandoned (abandon_on_cancel=False): the cancellation waits until
  the service function returns, so the worker never gives up on a request it already sent,
  and a metered run's credit check and start stay one unit. That wait has no strict upper
  bound: `requests` timeouts limit connecting and each wait for data, not a whole request,
  and a service may make several requests or wait for one of the locks first.
- Waiting does not make an operation atomic. A Jesse route does what it does whether or not
  the MCP request was cancelled: a started backtest, import, or research job keeps running
  until it ends or is cancelled with its own tool, and a multi-step change is as complete as
  the route made it. If a request times out or its connection fails, the service reports an
  error although Jesse may still finish the work, and a worker killed outright (the manager
  kills it 5 s after asking it to stop) returns nothing, while Jesse still completes requests
  it had received.
- The MCP SDK answers a cancelled request with its generic "Request cancelled" error as soon
  as the notice arrives, so that reply says nothing about the outcome. The outcome is logged
  here (service name plus status/error type or exception type; never arguments or results),
  and agent guidance tells assistants to check the current state before retrying.
- After a cancelled call finishes, the cancellation is raised instead of returning the
  result. The SDK expects that: once it has answered a cancelled request, a tool that still
  returns makes it respond a second time, which fails an assertion and ends the whole MCP
  session. Nothing between this function and the SDK's response awaits (tools only reshape
  the result synchronously), so no cancellation can arrive after the check.
"""
import functools
import logging
import math
from typing import Any, Callable, TypeVar

import anyio
import anyio.lowlevel
import anyio.to_thread

logger = logging.getLogger('jesse.mcp.tools')

T = TypeVar('T')


def _request_cancelled() -> bool:
    """True when an enclosing cancel scope (the SDK's per-request scope) has been cancelled."""
    return anyio.current_effective_deadline() == -math.inf


def _log_late_outcome(func: Callable[..., Any], outcome: str) -> None:
    logger.info(
        '%s finished after its MCP request was cancelled or its session closed (%s).',
        getattr(func, '__name__', 'tool call'), outcome,
    )


async def run_blocking(func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """
    Run a synchronous service call in a worker thread and return its result unchanged, or
    raise the request's cancellation once a cancelled call has finished (see module docs).
    """
    try:
        result = await anyio.to_thread.run_sync(functools.partial(func, *args, **kwargs))
    except Exception as exc:
        if _request_cancelled():
            _log_late_outcome(func, f'raised {type(exc).__name__}')
            await anyio.lowlevel.checkpoint_if_cancelled()
        raise
    if _request_cancelled():
        if isinstance(result, dict):
            error_type = result.get('error_type')
            outcome = f"status: {result.get('status')}" + (f', error_type: {error_type}' if error_type else '')
        else:
            outcome = f'returned {type(result).__name__}'
        _log_late_outcome(func, outcome)
        await anyio.lowlevel.checkpoint_if_cancelled()
    return result
