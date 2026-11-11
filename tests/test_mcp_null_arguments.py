import pytest
from mcp.server.fastmcp import FastMCP
from pydantic import ValidationError

from jesse.mcp.tools import register_tools


@pytest.fixture(scope='module')
def tools():
    mcp = FastMCP('null-arguments')
    register_tools(mcp)
    return mcp._tool_manager


def _null_default_arguments(tools):
    for tool in tools.list_tools():
        for name, field in tool.fn_metadata.arg_model.model_fields.items():
            if not field.is_required() and field.default is None:
                yield tool, field.alias or name


def test_every_argument_advertising_a_null_default_accepts_null(tools):
    rejected = []
    for tool, key in _null_default_arguments(tools):
        metadata = tool.fn_metadata
        try:
            metadata.arg_model.model_validate(metadata.pre_parse_json({key: None}))
        except ValidationError as e:
            # other required arguments are missing here; only an error about this key counts
            if any(error['loc'][:1] == (key,) for error in e.errors()):
                rejected.append(f'{tool.name}.{key}')
    assert rejected == []


def test_null_behaves_like_the_omitted_argument(tools):
    metadata = tools.get_tool('purge_backtest_sessions').fn_metadata
    omitted = metadata.arg_model.model_validate(metadata.pre_parse_json({})).model_dump_one_level()
    null = metadata.arg_model.model_validate(metadata.pre_parse_json({'days_old': None})).model_dump_one_level()
    assert null == omitted


def test_json_text_arguments_stay_text(tools):
    metadata = tools.get_tool('update_backtest_notes').fn_metadata
    arguments = metadata.pre_parse_json({'session_id': 's', 'title': None, 'strategy_codes': '{"a": "b"}'})
    parsed = metadata.arg_model.model_validate(arguments).model_dump_one_level()
    assert parsed['title'] is None
    assert parsed['strategy_codes'] == '{"a": "b"}'


def test_other_arguments_keep_fastmcp_json_decoding(tools):
    assert tools.get_tool('run_analysis').fn_metadata.pre_parse_json({'inputs': '[]'}) == {'inputs': []}
    # the history tools still receive their text exactly as sent
    assert tools.get_tool('get_live_trades').fn_metadata.pre_parse_json({'symbol': 'null'}) == {'symbol': 'null'}
