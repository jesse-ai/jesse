"""
MCP Tools Registration Module

HOW TO CREATE A NEW TOOL FILE:
-------------------------------
1. Create a file in jesse/mcp/tools/ (e.g., my_tools.py)

2. Define a registration function:
   
   def register_my_tools(mcp):
       @mcp.tool()
       def my_tool(param: str) -> str:
           \"\"\"Tool description with Args and Returns.\"\"\"
           return "result"
   
   Function name pattern: register_<category>_tools

3. Import and register in this file:
   from jesse.mcp.tools.my_tools import register_my_tools
   Then call: register_my_tools(mcp) in register_tools()

ACCESSING JESSE API URL:
------------------------
import jesse.mcp.tools as tools_module
api_url = tools_module.JESSE_API_URL  # Access at runtime, not import time
if api_url is None:
    return "❌ Error: API URL not configured"

EXAMPLES:
---------
See general.py for simple tools
See strategy.py for API-using tools
"""

from jesse.mcp.tools.strategy import register_strategy_tools
from jesse.mcp.tools.backtest import register_backtest_tools
from jesse.mcp.tools.config import register_config_tools
from jesse.mcp.tools.candles import register_candles_tools

# Global variable to store the Jesse API URL
# Will be set by the MCP server (server.py) before tools are registered
JESSE_API_URL = None
JESSE_PASSWORD = None

def register_tools(mcp):
    """
    Register all tools for the MCP server.
    
    To add new tools: create a file in tools/, define register_<category>_tools(mcp),
    import it here, and call it in this function.
    
    Args:
        mcp: The MCP server instance (FastMCP object).
    """
    # Register tools by category
    # Order doesn't matter, but grouping by domain improves maintainability

    # Strategy-related tools (creating/managing trading strategies)
    register_strategy_tools(mcp)

    # Backtest-related tools (running and managing backtests)
    register_backtest_tools(mcp)

    # Configuration management tools (same as dashboard uses)
    register_config_tools(mcp)

    # Candle data management tools (importing/managing historical data)
    register_candles_tools(mcp)
