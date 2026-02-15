"""
Jesse Indicator Tools

This module provides MCP tools for working with Jesse's technical indicators.

The tools include:
- list_indicators: List all available technical indicators in Jesse
- get_indicator_details: Get detailed information about a specific indicator
"""

import os
import inspect
import importlib.util
from typing import Dict, Any

from jesse import JESSE_DIR

def register_indicator_tools(mcp):
    """
    Register the indicator tools with the MCP server.

    Args:
        mcp: The MCP server instance.

    Returns:
        None
    """

    @mcp.tool()
    def list_indicators() -> dict:
        """
        List all available technical indicators in Jesse.

        Returns a comprehensive list of all indicators available through
        the jesse.indicators module, which can be used for technical analysis
        in trading strategies.

        Returns:
            dict: Contains status, count, and list of all available indicators
        """
        try:
            import jesse.indicators as ta

            # Get all indicator names from the module
            indicator_names = [name for name in dir(ta) if not name.startswith('_')]

            return {
                "status": "success",
                "count": len(indicator_names),
                "indicators": sorted(indicator_names),
                "message": f"Found {len(indicator_names)} indicators available in Jesse"
            }

        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "message": "Failed to list indicators"
            }

    @mcp.tool()
    def get_indicator_details(indicator_name: str) -> dict:
        """
        Get detailed information about a specific technical indicator.

        This tool provides comprehensive documentation for any Jesse indicator
        including parameters, return values, usage examples, and implementation details.

        Args:
            indicator_name: Name of the indicator (e.g., 'rsi', 'macd', 'sma')

        Returns:
            dict: Contains status, indicator details, or error information
        """
        try:
            # Find the indicator file
            indicator_file = os.path.join(JESSE_DIR, 'indicators', f"{indicator_name}.py")

            if not os.path.exists(indicator_file):
                return {
                    "status": "error",
                    "error": f"Indicator '{indicator_name}' not found",
                    "message": f"Could not find indicator file: {indicator_file}"
                }

            # Load the module
            spec = importlib.util.spec_from_file_location(indicator_name, indicator_file)
            if spec is None or spec.loader is None:
                return {
                    "status": "error",
                    "error": "Could not load indicator module",
                    "message": f"Failed to load module for indicator: {indicator_name}"
                }

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Get the main function (assumed to have same name as file)
            if not hasattr(module, indicator_name):
                return {
                    "status": "error",
                    "error": f"Function '{indicator_name}' not found in module",
                    "message": f"The indicator module exists but doesn't contain function: {indicator_name}"
                }

            func = getattr(module, indicator_name)

            # Extract function information
            sig = inspect.signature(func)
            docstring = func.__doc__ or ""

            # Parse parameters
            parameters = {}
            for param_name, param in sig.parameters.items():
                param_info = {
                    "name": param_name,
                    "default": param.default if param.default != inspect.Parameter.empty else None,
                    "annotation": str(param.annotation) if param.annotation != inspect.Parameter.empty else None,
                    "kind": str(param.kind)
                }
                parameters[param_name] = param_info

            # Parse return annotation
            return_annotation = str(sig.return_annotation) if sig.return_annotation != inspect.Signature.empty else None

            # Extract namedtuple info if applicable
            namedtuple_info = None
            for name, obj in module.__dict__.items():
                if hasattr(obj, '_fields') and hasattr(obj, '_field_defaults'):  # namedtuple
                    namedtuple_info = {
                        "name": name,
                        "fields": list(obj._fields),
                        "defaults": dict(obj._field_defaults) if obj._field_defaults else {}
                    }
                    break

            # Generate usage example
            usage_example = _generate_usage_example(indicator_name, parameters)

            return {
                "status": "success",
                "indicator_name": indicator_name,
                "signature": str(sig),
                "parameters": parameters,
                "return_annotation": return_annotation,
                "docstring": docstring.strip() if docstring else "",
                "namedtuple_info": namedtuple_info,
                "usage_example": usage_example,
                "file_path": indicator_file,
                "message": f"Successfully retrieved details for indicator: {indicator_name}"
            }

        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "indicator_name": indicator_name,
                "message": f"Failed to get details for indicator: {indicator_name}"
            }


def _generate_usage_example(indicator_name: str, parameters: Dict[str, Any]) -> str:
    """Generate a basic usage example for the indicator."""
    try:
        # Build parameter string
        param_strs = []
        for param_name, param_info in parameters.items():
            if param_name == "candles":
                param_strs.append("self.candles")
            elif param_info["default"] is not None:
                # Skip common defaults for brevity
                if param_name in ["sequential", "source_type"] and param_info["default"] == False:
                    continue
                if param_name == "source_type" and param_info["default"] == "close":
                    continue
                param_strs.append(f"{param_name}={param_info['default']}")
            else:
                param_strs.append(f"{param_name}=...")

        params = ", ".join(param_strs)

        # Generate import and usage
        example = f"""import jesse.indicators as ta

# Basic usage
result = ta.{indicator_name}({params})"""

        # Add sequential example if applicable
        if any(p["name"] == "sequential" for p in parameters.values()):
            example += f"""

# Get full series (sequential=True)
result = ta.{indicator_name}({params.replace('self.candles', 'self.candles') + ', sequential=True'})"""

        return example

    except Exception:
        return f"import jesse.indicators as ta\nresult = ta.{indicator_name}(...)"