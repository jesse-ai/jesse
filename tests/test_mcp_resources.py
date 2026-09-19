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


def test_strategy_resource_documents_the_trading_hours_api():
    mcp = FakeMCP()

    register_resources(mcp)

    strategy = mcp.resources['jesse://strategy']()
    assert '## Trading Hours' in strategy
    assert 'def trading_hours(self):' in strategy
    assert '`is_trading_hours`' in strategy
    assert 'utils.filter_candles_by_hours(self.candles, self.trading_hours())' in strategy
    # every key the schedule validator accepts must be documented
    for key in ('`timezone`', '`hours`', '`closed`', '`overrides`'):
        assert key in strategy
    # the two rules an assistant most easily gets wrong
    assert 'The engine enforces nothing' in strategy
    assert 'Do **not** gate `update_position()` or exits' in strategy


def test_documented_trading_hours_names_exist_in_the_real_api():
    from jesse import utils
    from jesse.services.trading_hours import _ALLOWED_KEYS
    from jesse.strategies import Strategy

    assert callable(utils.filter_candles_by_hours)
    assert callable(utils.is_in_trading_hours)
    assert callable(Strategy.trading_hours)
    assert isinstance(Strategy.is_trading_hours, property)
    assert _ALLOWED_KEYS == {'timezone', 'hours', 'closed', 'overrides'}


def test_utilities_and_examples_resources_cover_trading_hours():
    mcp = FakeMCP()

    register_resources(mcp)

    utilities = mcp.resources['jesse://utilities']()
    assert '### filter_candles_by_hours(candles, hours)' in utilities
    assert '### is_in_trading_hours(timestamp, hours)' in utilities

    examples = mcp.resources['jesse://strategy_examples']()
    assert 'class SessionBreakout(Strategy):' in examples
    assert 'if not self.is_trading_hours:' in examples


def test_candle_docs_state_that_only_one_minute_candles_are_imported():
    mcp = FakeMCP()

    register_resources(mcp)

    candle = mcp.resources['jesse://candle']()
    assert 'one-minute candles only' in candle
    assert 'Timeframes are never imported' in candle
    assert 'timeframes are imported automatically' not in candle.lower()

    from jesse.mcp.tools import candles as candle_tools
    import inspect

    source = inspect.getsource(candle_tools)
    assert 'Only one-minute candles are imported and stored' in source
    assert 'timeframes are imported automatically' not in source.lower()


def test_packaged_agent_rules_mention_trading_hours():
    rules = _load_packaged_rules()

    assert 'self.is_trading_hours' in rules
    assert 'utils.filter_candles_by_hours(self.candles, self.trading_hours())' in rules
