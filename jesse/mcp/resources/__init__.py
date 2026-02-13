from jesse.mcp.resources.strategy import register_strategy_resources
from jesse.mcp.resources.indicator import register_indicator_resources
from jesse.mcp.resources.position import register_position_resources
from jesse.mcp.resources.backtest import register_backtest_resources
from jesse.mcp.resources.candle import register_data_resources
from jesse.mcp.resources.configuration import register_config_resources
from jesse.mcp.resources.backtest_management import register_backtest_management_resources

def register_resources(mcp)-> None:
    register_strategy_resources(mcp)
    register_indicator_resources(mcp)
    register_position_resources(mcp)
    register_backtest_resources(mcp)
    register_data_resources(mcp)
    register_config_resources(mcp)
    register_backtest_management_resources(mcp)