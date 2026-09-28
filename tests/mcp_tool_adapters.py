"""Test helper: call MCP tool functions directly, whether they are sync or async."""
import functools
import inspect
from typing import Any, Callable

import anyio


def callable_tool(func: Callable[..., Any]) -> Callable[..., Any]:
    """
    Return `func` itself when it is synchronous. An async tool (one that offloads its API call
    to a worker thread) is wrapped so each call runs to completion in its own event loop, as
    FastMCP awaits it in production; `__wrapped__` keeps the original coroutine function.
    """
    if not inspect.iscoroutinefunction(func):
        return func

    @functools.wraps(func)
    def call(*args: Any, **kwargs: Any) -> Any:
        return anyio.run(functools.partial(func, *args, **kwargs))

    return call
