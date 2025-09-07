import jesse.helpers as jh
from jesse.services import logger as jesse_logger
import threading
import traceback
from jesse.services.redis import sync_publish


def register_custom_exception_handler() -> None:
    # other threads
    def handle_thread_exception(args) -> None:
        if args.exc_type == SystemExit:
            return

        if args.exc_type.__name__ == 'Termination':
            sync_publish('termination', {})
            jh.terminate_app()
        else:
            # Capture exception in PostHog if available
            try:
                from jesse.services.posthog import get_posthog_service
                svc = get_posthog_service()
                if svc._client is not None:  # Only if PostHog is initialized
                    ctx = {
                        'source': 'thread_exception_handler',
                        'thread_name': threading.current_thread().name,
                        'traceback': str(traceback.format_exc())
                    }
                    svc.capture_exception(args.exc_value, ctx)
            except Exception:
                # Don't let PostHog errors affect the main exception handling
                pass

            # send notifications if it's a live session
            if jh.is_live():
                jesse_logger.error(
                    f'{args.exc_type.__name__}: {args.exc_value}'
                )
                jesse_logger.info(
                    str(traceback.format_exc())
                )

            sync_publish('exception', {
                'error': f"{args.exc_type.__name__}: {str(args.exc_value)}",
                'traceback': str(traceback.format_exc())
            })
            terminate_session()

    threading.excepthook = handle_thread_exception


def terminate_session():
    sync_publish('unexpectedTermination', {
        'message': "Session terminated as the result of an uncaught exception",
    })

    jesse_logger.error('Session terminated as the result of an uncaught exception')

    jh.terminate_app()
