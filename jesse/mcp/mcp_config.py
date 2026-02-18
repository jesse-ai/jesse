"""
Jesse MCP Configuration Store

This module provides a centralized configuration store for the MCP server.
All configuration values that need to be shared between the server and tools
are stored here to avoid circular imports.

The server sets these values before registering tools.
"""

# Jesse API configuration
JESSE_API_URL = None
JESSE_PASSWORD = None