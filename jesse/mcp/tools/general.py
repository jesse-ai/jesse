def register_general_tools(mcp):
    """
    Register the tools for the general operations.
    
    Args:
        mcp: The MCP server instance.
        
    Returns:
        None
    """
    # Tool: get jesse status
    @mcp.tool()
    def get_jesse_status():
        return {
            "status": "running",
            "version": "1.0.0",
            "message": "Jesse is running"
        }

    # Tool: greet user
    @mcp.tool()
    def greet_user(name: str):
        return {
            "status": "success",
            "action": "greeting",
            "user_name": name,
            "message": f"Hello, {name}! How can I help you today?"
        }

