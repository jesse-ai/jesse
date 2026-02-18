"""
Jesse Authentication Service Functions

This module contains authentication-related utility functions used by Jesse's
MCP tools. These functions handle password hashing and authentication token generation.
"""

def hash_password(password: str) -> str:
    """
    Hash a password using SHA256 for Jesse API authentication.

    Args:
        password: Raw password string

    Returns:
        SHA256 hashed password as hex string
    """
    from hashlib import sha256
    return sha256(password.encode('utf-8')).hexdigest()