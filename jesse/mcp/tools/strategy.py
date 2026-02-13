def register_strategy_tools(mcp):
    """
    Register the tools for the strategy related operations.

    This module provides MCP tools for managing Jesse trading strategies:
    - create_strategy: Creates a new strategy with basic template code
    - read_strategy: Reads the content of an existing strategy using Jesse's API
    - write_strategy: Updates the content of an existing strategy using Jesse's API

    All tools require authentication via Jesse admin password.

    Args:
        mcp: The MCP server instance.

    Returns:
        None
    """
    # Import the module to access JESSE_API_URL dynamically
    import jesse.mcp.tools as tools_module
    
    @mcp.tool()
    def create_strategy(name: str) -> dict:
        """
        Create a new trading strategy in Jesse.

        Args:
            name: Name of the new strategy to create
            password: Jesse admin password for authentication

        Returns:
            Success or error message
        """
        import requests
        from hashlib import sha256

        # Get the current API URL value (accessed at runtime, not import time)
        api_url = tools_module.JESSE_API_URL
        
        if api_url is None:
            return "❌ Error: Jesse API URL is not configured. Please restart the MCP server."

        # Get the current Jesse password value (accessed at runtime, not import time)
        password = tools_module.JESSE_PASSWORD
        if password is None:
            return "❌ Error: Jesse password is not configured. Please restart the MCP server."

        # Generate auth token (SHA256 hash of password)
        auth_token = sha256(password.encode('utf-8')).hexdigest()

        try:
            # Make authenticated request to create the strategy
            response = requests.post(
                f'{api_url}/strategy/make',
                json={'name': name},
                headers={'Authorization': auth_token},  # Jesse uses token directly, not Bearer format
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                if data.get('status') == 'success':
                    return {
                        "status": "success",
                        "action": "strategy_created",
                        "strategy_name": name,
                        "message": f"Strategy '{name}' created successfully",
                        "path": data.get('message')
                    }
                else:
                    return {
                        "status": "error",
                        "action": "strategy_creation_failed",
                        "strategy_name": name,
                        "error_type": "api_error",
                        "message": data.get('message', 'Unknown error')
                    }
            elif response.status_code == 401:
                return {
                    "status": "error",
                    "action": "strategy_creation_failed",
                    "strategy_name": name,
                    "error_type": "authentication_failed",
                    "message": "Invalid password provided"
                }
            elif response.status_code == 409:
                return {
                    "status": "error",
                    "action": "strategy_creation_failed",
                    "strategy_name": name,
                    "error_type": "strategy_exists",
                    "message": f"Strategy '{name}' already exists"
                }
            else:
                return {
                    "status": "error",
                    "action": "strategy_creation_failed",
                    "strategy_name": name,
                    "error_type": "http_error",
                    "http_status": response.status_code,
                    "message": response.text
                }

        except requests.exceptions.RequestException as e:
            return {
                "status": "error",
                "action": "strategy_creation_failed",
                "strategy_name": name,
                "error_type": "connection_error",
                "message": f"Could not connect to Jesse API at {api_url}",
                "details": str(e)
            }

    
    @mcp.tool()
    def read_strategy(name: str) -> dict:
        """
        Read the content of a trading strategy using Jesse's API.

        Args:
            name: Name of the strategy to read
            password: Jesse admin password for authentication

        Returns:
            Dictionary containing strategy content or error message
        """
        import requests
        from hashlib import sha256

        # Get the current API URL value (accessed at runtime, not import time)
        api_url = tools_module.JESSE_API_URL

        if api_url is None:
            return "❌ Error: Jesse API URL is not configured. Please restart the MCP server."

        # Get the current Jesse password value (accessed at runtime, not import time)
        password = tools_module.JESSE_PASSWORD
        if password is None:
            return "❌ Error: Jesse password is not configured. Please restart the MCP server."

        # Generate auth token (SHA256 hash of password)
        auth_token = sha256(password.encode('utf-8')).hexdigest()

        try:
            # Make authenticated request to get the strategy
            response = requests.post(
                f'{api_url}/strategy/get',
                json={'name': name},
                headers={'Authorization': auth_token},  # Jesse uses token directly, not Bearer format
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                if data.get('status') == 'success':
                    return {
                        "status": "success",
                        "action": "strategy_read",
                        "strategy_name": name,
                        "message": f"Strategy '{name}' content read successfully",
                        "content": data.get('content')
                    }
                else:
                    return {
                        "status": "error",
                        "action": "strategy_read_failed",
                        "strategy_name": name,
                        "error_type": "api_error",
                        "message": data.get('message', 'Unknown error')
                    }
            elif response.status_code == 401:
                return {
                    "status": "error",
                    "action": "strategy_read_failed",
                    "strategy_name": name,
                    "error_type": "authentication_failed",
                    "message": "Invalid password provided"
                }
            elif response.status_code == 404:
                return {
                    "status": "error",
                    "action": "strategy_read_failed",
                    "strategy_name": name,
                    "error_type": "strategy_not_found",
                    "message": f"Strategy '{name}' not found"
                }
            else:
                return {
                    "status": "error",
                    "action": "strategy_read_failed",
                    "strategy_name": name,
                    "error_type": "http_error",
                    "http_status": response.status_code,
                    "message": response.text
                }

        except requests.exceptions.RequestException as e:
            return {
                "status": "error",
                "action": "strategy_read_failed",
                "strategy_name": name,
                "error_type": "connection_error",
                "message": f"Could not connect to Jesse API at {api_url}",
                "details": str(e)
            }
    
    @mcp.tool()
    def write_strategy(name: str, content: str) -> dict:
        """
        Write content to a trading strategy using Jesse's API.

        Args:
            name: Name of the strategy to write to
            content: The Python code content to write to the strategy file
            password: Jesse admin password for authentication

        Returns:
            Dictionary containing success confirmation or error message
        """
        import requests
        from hashlib import sha256

        # Get the current API URL value (accessed at runtime, not import time)
        api_url = tools_module.JESSE_API_URL

        if api_url is None:
            return "❌ Error: Jesse API URL is not configured. Please restart the MCP server."

        # Get the current Jesse password value (accessed at runtime, not import time)
        password = tools_module.JESSE_PASSWORD
        if password is None:
            return "❌ Error: Jesse password is not configured. Please restart the MCP server."

        # Generate auth token (SHA256 hash of password)
        auth_token = sha256(password.encode('utf-8')).hexdigest()

        try:
            # Make authenticated request to save the strategy
            response = requests.post(
                f'{api_url}/strategy/save',
                json={'name': name, 'content': content},
                headers={'Authorization': auth_token},  # Jesse uses token directly, not Bearer format
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                if data.get('status') == 'success':
                    return {
                        "status": "success",
                        "action": "strategy_updated",
                        "strategy_name": name,
                        "message": f"Strategy '{name}' content updated successfully"
                    }
                else:
                    return {
                        "status": "error",
                        "action": "strategy_write_failed",
                        "strategy_name": name,
                        "error_type": "api_error",
                        "message": data.get('message', 'Unknown error')
                    }
            elif response.status_code == 401:
                return {
                    "status": "error",
                    "action": "strategy_write_failed",
                    "strategy_name": name,
                    "error_type": "authentication_failed",
                    "message": "Invalid password provided"
                }
            elif response.status_code == 404:
                return {
                    "status": "error",
                    "action": "strategy_write_failed",
                    "strategy_name": name,
                    "error_type": "strategy_not_found",
                    "message": f"Strategy '{name}' not found"
                }
            else:
                return {
                    "status": "error",
                    "action": "strategy_write_failed",
                    "strategy_name": name,
                    "error_type": "http_error",
                    "http_status": response.status_code,
                    "message": response.text
                }

        except requests.exceptions.RequestException as e:
            return {
                "status": "error",
                "action": "strategy_write_failed",
                "strategy_name": name,
                "error_type": "connection_error",
                "message": f"Could not connect to Jesse API at {api_url}",
                "details": str(e)
            }