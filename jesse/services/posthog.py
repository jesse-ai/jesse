"""
PostHog Error Tracking Service for Jesse Trading Framework

This service provides automatic error tracking capabilities using PostHog.
Configuration is loaded from the main config via data provider.
Automatically captures unhandled exceptions when enabled.
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional

try:
    from posthog import Posthog, capture, identify_context
    POSTHOG_AVAILABLE = True
except ImportError:
    POSTHOG_AVAILABLE = False
    Posthog = None
    identify_context = None
    capture = None

import jesse.helpers as jh


class PostHogService:
    """
    PostHog Error Tracking Service for Jesse
    
    Provides automatic error tracking capabilities using PostHog.
    Configuration is loaded from the .env file using jesse.services.env.
    Uses PostHog's capture_exception method for proper exception tracking.
    Automatically captures unhandled exceptions when enabled.
    """

    def __init__(self):
        self._api_key = None
        self._host = None
        self._client = None
        self._current_user_token = None  # Store current user's auth token
        self._logger = logging.getLogger(__name__)

    def _get_posthog_config(self) -> Dict[str, Any]:
        """Get PostHog configuration from environment variables"""
        from jesse.services.env import ENV_VALUES
        return {
            'api_key': ENV_VALUES.get('POSTHOG_API_KEY', ''),
            'host': ENV_VALUES.get('POSTHOG_HOST', 'https://eu.i.posthog.com'),
            'debug': ENV_VALUES.get('POSTHOG_DEBUG', 'false').lower() == 'true',
        }

    def _initialize(self) -> None:
        """Initialize PostHog client if available and configured."""
        if not POSTHOG_AVAILABLE:
            self._logger.warning("PostHog not available. Install with: pip install posthog")
            return

        # Get configuration from config.py
        posthog_config = self._get_posthog_config()

        self._api_key = posthog_config.get('api_key')
        self._host = posthog_config.get('host', 'https://eu.i.posthog.com')

        if not self._api_key:
            self._logger.warning("PostHog API key not configured in Jesse config. Posthog can't initialize.")
            return

        try:
            # Create PostHog client instance
            self._client = Posthog(
                self._api_key,
                host=self._host,
                enable_exception_autocapture=False,  # Disable auto-capture
                debug=posthog_config.get("debug", False),
            )

            self._logger.info(
                f"PostHog client initialized successfully."
            )

        except Exception as e:
            self._logger.error(f"Failed to initialize PostHog: {e}")
            self._client = None
            return

    def identify_user(self, auth_token: str, system_data: Optional[Dict[str, Any]] = None) -> None:
        """
        Identify a user in PostHog using their auth token.
        
        Args:
            auth_token: The user's authentication token (used as user ID)
            system_data: Optional system information dictionary
        """
        if not self._client:
            self._logger.warning("PostHog not initialized. Cannot identify user.")
            return

        try:
            # Set user properties
            properties = {
                'jesse_mode': jh.app_mode(),
                'auth_type': 'password_based',
                'timestamp': datetime.now().isoformat(),
            }

            # Add system data if provided
            if system_data:
                properties.update(system_data)

            # Identify the user context (only takes distinct_id)
            identify_context(auth_token)

            # Set user properties using client's capture method
            self._client.capture(
                event="$identify",
                distinct_id=auth_token,
                properties={
                    "$set": properties
                }
            )
            
            # Store the current user token for background thread exceptions
            self._current_user_token = auth_token

            self._logger.debug(f"User identified in PostHog")
            return

        except Exception as e:
            self._logger.error(f"Failed to identify user: {e}")
            return

    def capture_exception(
        self,
        error: Exception,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Track errors for debugging and monitoring using PostHog's capture_exception method.
        
        Args:
            error: The exception that occurred
            context: Additional context about the error
        """

        if not self._client:
            self._logger.warning("PostHog not initialized. Cannot track error.")
            return

        try:
            # Prepare context properties for the exception
            # Get system info with error handling
            system_info = {}
            try:
                from jesse.services.general_info import get_general_info
                general_info = get_general_info(has_live=jh.has_live_trade_plugin())
                system_info = general_info.get('system_info', {})
            except Exception as e:
                self._logger.warning(f"Failed to get system info: {e}")

            properties = {
                'jesse_mode': jh.app_mode(),
                'timestamp': datetime.now().isoformat(),
                'system_info': system_info,
                'context': context or {}
            }

            # Use PostHog's official capture_exception method
            # Use stored user token if available, otherwise fall back to anonymous user
            if self._current_user_token:
                self._client.capture_exception(error, distinct_id=self._current_user_token, properties=properties)
            else:
                self._client.capture_exception(error, properties=properties)
            self._logger.debug(f"Exception tracked: {type(error).__name__}")

        except Exception as e:
            self._logger.error(f"Failed to track exception: {e}")
            return

    def flush(self) -> None:
        """Flush any pending events to PostHog."""
        if not self._client:
            self._logger.warning("PostHog not initialized. Cannot flush events.")
            return

        try:
            self._client.flush()
        except Exception as e:
            self._logger.error(f"Failed to flush PostHog events: {e}")
            return

    def shutdown(self) -> None:
        """Shutdown the PostHog service and flush any pending events."""

        if not self._client:
            self._logger.warning("PostHog not initialized. Cannot shutdown.")
            return

        try:
            self.flush()
            self._client.shutdown()
            self._logger.info("PostHog service shutdown")
            self._client = None
        except Exception as e:
            self._logger.error(f"Error during shutdown: {e}")
            # Still set client to None even if shutdown fails
            self._client = None
            return


# Global instance
_posthog_service = None


def get_posthog_service() -> PostHogService:
    """Get the global PostHog service instance."""
    global _posthog_service
    if _posthog_service is None:
        _posthog_service = PostHogService()
    return _posthog_service
