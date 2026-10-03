"""
Refuse unknown arguments of selected MCP tools instead of silently dropping them, and keep
their argument values exactly as sent.

FastMCP (checked on SDK 1.28.1) validates tool arguments with a pydantic model that ignores
extra keys, so a misspelled filter such as "symbl" or "recent_day" reaches the tool as its
default and silently widens the selection. For the tools passed to `refuse_unknown_arguments`,
the argument model keeps extra keys and the call answers an invalid_request error that names
only the accepted arguments, never the given names or values.

Raising from the argument model instead would surface pydantic's error text, which quotes every
argument value. The advertised input schema and description are computed when a tool is
registered and do not change; the wrapper keeps the original function as `__wrapped__`, so its
signature, annotations, and docstring stay the same.

FastMCP (SDK 1.28.1, FuncMetadata.pre_parse_json) also JSON-decodes every string argument whose
parameter is not annotated exactly `str`, to help clients that send lists and objects as JSON
text. For tools whose arguments are all scalars that is harmful: the text "null" becomes None,
so symbol="null" or start="null" would silently read as an omitted filter, and '["x"]' would
turn into a list. `keep_raw_argument_values` makes the named tools skip that step; their
services validate the raw values strictly.
"""
import functools
from typing import Any, Callable, Dict

from mcp.server.fastmcp.utilities.func_metadata import FuncMetadata
from pydantic import ConfigDict

# Carries the unknown argument names from the argument model to the wrapper. FastMCP passes
# arguments as keyword arguments, and no tool parameter can have this name (FastMCP refuses
# parameter names starting with "_").
_UNKNOWN = '__unknown_arguments__'


def _strict_model(base: type) -> type:
    """The tool's argument model, keeping extra keys and reporting their names to the wrapper."""

    class StrictArguments(base):
        model_config = ConfigDict(extra='allow')

        def model_dump_one_level(self) -> Dict[str, Any]:
            values = super().model_dump_one_level()
            if self.model_extra:
                values[_UNKNOWN] = sorted(self.model_extra)
            return values

    StrictArguments.__name__ = StrictArguments.__qualname__ = base.__name__
    return StrictArguments


def _refusing(fn: Callable[..., Any], name: str, accepted: str) -> Callable[..., Any]:
    @functools.wraps(fn)
    async def call(*args: Any, **kwargs: Any) -> Any:
        if kwargs.pop(_UNKNOWN, None):
            return {'status': 'error', 'action': name, 'error_type': 'invalid_request',
                    'message': f'Unknown argument(s); {name} accepts only: {accepted}.'}
        return await fn(*args, **kwargs)

    return call


def refuse_unknown_arguments(mcp: Any, *names: str) -> None:
    """Make the named (async) tools refuse unknown arguments. Test doubles without FastMCP's registry are left alone."""
    manager = getattr(mcp, '_tool_manager', None)
    if manager is None:
        return
    for name in names:
        tool = manager.get_tool(name)
        accepted = ', '.join(tool.fn_metadata.arg_model.model_fields)
        tool.fn_metadata.arg_model = _strict_model(tool.fn_metadata.arg_model)
        tool.fn = _refusing(tool.fn, name, accepted)


class _RawArgumentValues(FuncMetadata):
    """FuncMetadata that passes argument values to validation exactly as the client sent them."""

    def pre_parse_json(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return dict(data)


def keep_raw_argument_values(mcp: Any, *names: str) -> None:
    """Skip FastMCP's JSON decoding of string arguments for the named tools (scalar-only arguments)."""
    manager = getattr(mcp, '_tool_manager', None)
    if manager is None:
        return
    for name in names:
        tool = manager.get_tool(name)
        metadata = tool.fn_metadata
        tool.fn_metadata = _RawArgumentValues(
            **{field: getattr(metadata, field) for field in FuncMetadata.model_fields})
