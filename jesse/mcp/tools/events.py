"""
Jesse MCP Event Tools

This module provides MCP tools for querying real-time events from the Jesse backend
via the WebSocket listener.

TOOLS:
- get_recent_events: Get recent events by category
- get_events_by_id: Get events for a specific ID
- get_websocket_status: Check WebSocket connection status
- clear_event_history: Clear stored events
"""

def register_event_tools(mcp):
    """
    Register WebSocket event monitoring tools with the MCP server.
    """

    @mcp.tool()
    def get_recent_events(
        category: str = "all",
        limit: int = 20
    ) -> dict:
        """
        Get recent real-time events from Jesse backend.

        Args:
            category: Event category ('backtest', 'candles', 'all')
            limit: Maximum number of events to return (default: 20)

        Returns:
            Dictionary with events and metadata
        """
        from jesse.mcp.ws_listener import get_events, is_connected

        if not is_connected():
            return {
                "status": "error",
                "message": "WebSocket not connected to Jesse backend. Events may not be available."
            }

        events = get_events(category, limit)

        return {
            "status": "success",
            "category": category,
            "events_count": len(events),
            "events": events,
            "message": f"Retrieved {len(events)} recent {category} events"
        }

    @mcp.tool()
    def get_events_by_id(
        event_id: str,
        category: str = "all"
    ) -> dict:
        """
        Get all events with the specified ID.

        Args:
            event_id: Event ID to filter by (e.g., import_id, backtest_id)
            category: Category to search in ('all' searches all categories)

        Returns:
            Dictionary with matching events
        """
        from jesse.mcp.ws_listener import get_events_by_id, is_connected

        if not is_connected():
            return {
                "status": "error",
                "message": "WebSocket not connected to Jesse backend."
            }

        events = get_events_by_id(event_id, None if category == "all" else category)

        return {
            "status": "success",
            "event_id": event_id,
            "category": category,
            "events_count": len(events),
            "events": events,
            "message": f"Found {len(events)} events with ID '{event_id}'"
        }

    @mcp.tool()
    def get_websocket_status() -> dict:
        """
        Check the status of the WebSocket connection to Jesse backend.

        Returns:
            Dictionary with connection status and event statistics
        """
        from jesse.mcp.ws_listener import is_connected, get_stats

        stats = get_stats()

        return {
            "status": "success",
            "websocket_connected": is_connected(),
            "event_counts": stats['categories'],
            "total_events": stats['total_events'],
            "message": f"WebSocket {'connected' if is_connected() else 'disconnected'}, {stats['total_events']} events stored"
        }

    @mcp.tool()
    def clear_event_history(
        category: str = "all"
    ) -> dict:
        """
        Clear stored event history.

        Args:
            category: Category to clear ('all' clears everything)

        Returns:
            Dictionary with clearing results
        """
        from jesse.mcp.ws_listener import clear_events

        cleared_count = clear_events(category)

        return {
            "status": "success",
            "category": category,
            "events_cleared": cleared_count,
            "message": f"Cleared {cleared_count} events from {category} category"
        }

