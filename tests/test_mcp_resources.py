from jesse.mcp.agent_rules import _load_packaged_rules
from jesse.mcp.resources import register_resources
from jesse.mcp.tools.strategy import register_strategy_tools


class FakeMCP:
    def __init__(self):
        self.resources = {}

    def resource(self, uri):
        def decorator(func):
            self.resources[uri] = func
            return func

        return decorator

    def tool(self):
        def decorator(func):
            self.resources[f'tool://{func.__name__}'] = func
            return func

        return decorator


def test_charts_resource_is_registered_with_live_chart_guidance():
    mcp = FakeMCP()

    register_resources(mcp)

    charts = mcp.resources['jesse://charts']()
    assert 'def update_chart(self) -> None:' in charts
    assert 'approximately once per second' in charts
    assert 'replace that candle\'s most recent point' in charts
    assert 'latest 1,000 candle points' in charts
    assert 'Warm-up candles' in charts
    assert 'not replayed' in charts


def test_charts_resource_documents_every_strategy_chart_method():
    mcp = FakeMCP()

    register_resources(mcp)

    charts = mcp.resources['jesse://charts']()
    assert 'add_line_to_candle_chart' in charts
    assert 'add_horizontal_line_to_candle_chart' in charts
    assert 'add_extra_line_chart' in charts
    assert 'add_horizontal_line_to_extra_chart' in charts
    assert "line_style='solid'" in charts
    assert "`'dotted'`" in charts


def test_strategy_resource_points_chart_requests_to_dedicated_resource():
    mcp = FakeMCP()

    register_resources(mcp)

    strategy = mcp.resources['jesse://strategy']()
    assert '**jesse://charts**' in strategy
    assert 'def update_chart(self) -> None:' in strategy
    assert 'Keep `update_chart()` visualization-only' in strategy


def test_packaged_agent_rules_point_chart_requests_to_resource():
    rules = _load_packaged_rules()

    assert 'jesse://charts - Strategy chart APIs' in rules
    assert 'Consult `jesse://charts` before adding or changing strategy charts.' in rules


def test_strategy_tool_descriptions_expose_update_chart_lifecycle():
    mcp = FakeMCP()

    register_strategy_tools(mcp)

    create_docs = mcp.resources['tool://create_strategy'].__doc__
    read_docs = mcp.resources['tool://read_strategy'].__doc__
    write_docs = mcp.resources['tool://write_strategy'].__doc__
    assert create_docs is not None and 'forming candle in live/paper sessions' in create_docs
    assert read_docs is not None and 'visualization-only chart calculations' in read_docs
    assert write_docs is not None and 'intrabar live/paper updates' in write_docs
