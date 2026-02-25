"""
Jesse MCP Resources Registration Module

This module provides dynamic registration of MCP (Model Context Protocol) resources
for the Jesse trading framework. It automatically discovers and registers all
documentation files as MCP resources, making Jesse's comprehensive guides and
reference materials available to MCP clients.

Resource Discovery:
The system automatically scans this directory for .md files and registers them
as MCP resources with URIs in the format: jesse://{filename_without_extension}

Available Resources:
- backtest_management: Complete backtesting workflow and candle import guidance
- candle_management: Data import procedures and warmup requirements
- strategy: Strategy development guides and templates
- indicator_cheatsheet: Technical indicators reference and usage examples
- position_risk: Position sizing and risk management references
- utilities: Helper functions and calculation utilities
- And more documentation files as they are added...

Adding New Resources:
To add new MCP resources, simply create a new .md file in this directory.
The system will automatically register it with the URI: jesse://{filename}

Example:
    Create `new_feature.md` → Available as `jesse://new_feature`

The dynamic approach ensures all documentation stays current and accessible
without manual registration code.
"""

def register_resources(mcp) -> None:
    """
    Register all Jesse MCP resources with the provided MCP server instance.

    This function serves as the single entry point for registering all MCP resources,
    ensuring that documentation and reference materials for all Jesse components
    are made available through the MCP protocol.

    Args:
        mcp: The MCP server instance to register resources with
    """
    # read all the md files and register them as resources for the mcp
    import os
    from functools import partial

    def resource_template(content):
        """Template function for MCP resources."""
        return content

    for file in os.listdir(os.path.dirname(__file__)):
        if file.endswith('.md'):
            with open(os.path.join(os.path.dirname(__file__), file), 'r') as f:
                content = f.read()
            resource_name = file.replace('.md', '')
            uri = f"jesse://{resource_name}"

            # Create unique function for this resource using partial
            resource_func = partial(resource_template, content)
            resource_func.__name__ = f"{resource_name}"  # Give it a unique name

            # Apply the MCP resource decorator
            decorated_func = mcp.resource(uri)(resource_func)

            # Store reference to prevent garbage collection of dynamically created functions
            # FastMCP only holds weak references to registered resources, so we need to
            # keep strong references on the MCP instance to prevent premature GC
            setattr(mcp, f"_resource_{resource_name}", decorated_func)
