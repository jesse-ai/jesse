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
        self._api_key = 'phc_unujHScjdDE6abNg0ZTDKX3phU9JIffj9IlBPCjU9Bl'
        self._host = 'https://eu.i.posthog.com'
        self._debug = True # should be false in production
        self._client = None
        self._current_distinct_id = None # we use this as the the id for the user
        self._anonymous_id = jh.generate_os_based_uuid() # we use this as the anonymous id for the user
        self._logger = logging.getLogger(__name__)


    def _initialize(self) -> None:
        """Initialize PostHog client if available and configured."""
        if not POSTHOG_AVAILABLE:
            self._logger.warning("PostHog not available. Install with: pip install posthog")
            return

        if not self._api_key:
            self._logger.warning("PostHog API key not configured. Posthog can't initialize.")
            return

        try:
            # Create PostHog client instance
            self._client = Posthog(
                self._api_key,
                host=self._host,
                enable_exception_autocapture=False,  # Disable auto-capture
                debug=self._debug,
            )

            self._logger.info(
                f"PostHog client initialized successfully."
            )

        except Exception as e:
            self._logger.error(f"Failed to initialize PostHog: {e}")
            self._client = None
            return

    def identify_user(self, distinct_id: str | None = None, additionalProperties: Optional[Dict[str, Any]] = None) -> None:
        """
        Identify a user in PostHog using a distinct id.
        If user was previously anonymous and now has a distinct_id, creates an alias to merge sessions.
        
        Args:
            distinct_id: The user's distinct id (used as user ID)
            additionalProperties: Optional additional properties dictionary
        """
        if not self._client:
            self._logger.warning("PostHog not initialized. Cannot identify user.")
            return

        system_info = {}
        try:
            from jesse.services.general_info import get_general_info
            general_info = get_general_info(has_live=jh.has_live_trade_plugin())
            system_info = general_info.get('system_info', {})
        except Exception as e:
            self._logger.warning(f"Failed to get system info: {e}")

        try:
            # Determine the effective user ID
            effective_user_id = distinct_id or self._anonymous_id
            
            # If we have a distinct_id AND we previously had an anonymous session, create an alias
            if distinct_id and self._current_distinct_id is None:
                # User is transitioning from anonymous to identified
                self._logger.debug(f"Aliasing anonymous user {self._anonymous_id} to identified user {distinct_id}")
                self._client.alias(
                    previous_id=self._anonymous_id,
                    distinct_id=distinct_id
                )

            # Set user properties
            properties = {
                'jesse_mode': jh.app_mode(),
                'auth_type': 'password_based' if distinct_id else 'anonymous',
                'timestamp': datetime.now().isoformat(),
            }

            # Add system data if provided
            if system_info:
                properties.update(system_info)
                
            # Add additional properties if provided
            if additionalProperties:
                properties.update(additionalProperties)

            # Identify the user context via distinct_id or anonymous_id if distinct_id is not provided
            identify_context(effective_user_id)

            # Set user properties using client's capture method
            self._client.capture(
                event="$identify",
                distinct_id=effective_user_id,
                properties={
                    "$set": properties
                }
            )
            
            # Store the current user token for background thread exceptions
            self._current_distinct_id = distinct_id

            self._logger.debug(f"User identified in PostHog with ID: {effective_user_id}")
            return

        except Exception as e:
            self._logger.error(f"Failed to identify user: {e}")
            return

    def reset_user(self) -> None:
        """
        Reset user back to anonymous state (useful for logout).
        """
        if not self._client:
            self._logger.warning("PostHog not initialized. Cannot reset user.")
            return

        try:
            # Reset PostHog context back to anonymous
            identify_context(self._anonymous_id)
            
            # Clear the current distinct_id
            self._current_distinct_id = None
            
            self._logger.debug(f"User reset to anonymous state with ID: {self._anonymous_id}")
            return

        except Exception as e:
            self._logger.error(f"Failed to reset user: {e}")
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
            # We use _current_distinct_id or _anonymous_id as the fallback id if the distinct id for the user is not provided
            self._client.capture_exception(error, distinct_id=self._current_distinct_id or self._anonymous_id, properties=properties)

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
