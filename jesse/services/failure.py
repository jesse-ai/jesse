import jesse.helpers as jh
from jesse.services import logger as jesse_logger
import threading
import traceback
import os
from jesse.services.redis import sync_publish
from jesse.repositories import live_session_repository
from jesse.store import store
from jesse.enums import live_session_statuses


def _terminal_debug(message: str) -> None:
    try:
        jh.terminal_debug(message)
    except Exception:
        pass


def register_custom_exception_handler() -> None:
    # other threads
    def handle_thread_exception(args) -> None:
        if args.exc_type == SystemExit:
            return

        formatted_traceback = ''.join(
            traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)
        )

        if args.exc_type.__name__ == 'Termination':
            sync_publish('termination', {})
            jh.terminate_app()
        else:
            # send notifications if it's a live session
            if jh.is_live():
                try:
                    jesse_logger.error(
                        f'{args.exc_type.__name__}: {args.exc_value}'
                    )
                    jesse_logger.info(formatted_traceback)
                except Exception as e:
                    _terminal_debug(
                        f'Error logging uncaught thread exception: {type(e).__name__}: {e}\n{formatted_traceback}'
                    )

                # Store exception in live session
                try:
                    live_session_repository.store_live_session_exception(
                        store.app.session_id,
                        f"{args.exc_type.__name__}: {str(args.exc_value)}",
                        formatted_traceback
                    )
                    live_session_repository.update_live_session_status(store.app.session_id, live_session_statuses.STOPPED)
                    live_session_repository.update_live_session_finished(store.app.session_id)
                except Exception as e:
                    _terminal_debug(f'Error storing live session exception: {type(e).__name__}: {e}')

            try:
                sync_publish('exception', {
                    'error': f"{args.exc_type.__name__}: {str(args.exc_value)}",
                    'traceback': formatted_traceback
                })
            finally:
                terminate_session()

    threading.excepthook = handle_thread_exception


def terminate_session():
    try:
        sync_publish('unexpectedTermination', {
            'message': "Session terminated as the result of an uncaught exception",
        })
    except Exception as e:
        _terminal_debug(f'Error publishing unexpected session termination: {type(e).__name__}: {e}')

    try:
        jesse_logger.error('Session terminated as the result of an uncaught exception')
    except Exception as e:
        _terminal_debug(f'Error logging unexpected session termination: {type(e).__name__}: {e}')

    try:
        jh.terminate_app()
    except BaseException as e:
        _terminal_debug(f'Error closing resources during session termination: {type(e).__name__}: {e}')
    finally:
        os._exit(1)
