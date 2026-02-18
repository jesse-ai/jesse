"""
Jesse General Service Functions

This module contains the core general service functions used by Jesse's
MCP tools. These functions handle basic operations and utilities.

The functions are separated from the MCP tool wrappers to allow for better
code organization and reusability.
"""


def get_jesse_status():
    """
    Get the current status of Jesse.

    Returns:
        Dictionary with Jesse status information
    """
    return {
        "status": "running",
        "version": "1.0.0",
        "message": "Jesse is running"
    }


def greet_user(name: str):
    """
    Generate a greeting message for the user.

    Args:
        name: The name of the user to greet

    Returns:
        Dictionary with greeting information
    """
    return {
        "status": "success",
        "action": "greeting",
        "user_name": name,
        "message": f"Hello, {name}! How can I help you today?"
    }