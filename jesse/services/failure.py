import jesse.helpers as jh
from jesse.services import logger as jesse_logger
import threading
import traceback
from jesse.services.redis import sync_publish
from jesse.repositories import live_session_repository
from jesse.store import store
from jesse.enums import live_session_statuses


def register_custom_exception_handler() -> None:
    # other threads
    def handle_thread_exception(args) -> None:
        if args.exc_type == SystemExit:
            return

        if args.exc_type.__name__ == 'Termination':
            sync_publish('termination', {})
            jh.terminate_app()
        else:
            # send notifications if it's a live session
            if jh.is_live():
                jesse_logger.error(
                    f'{args.exc_type.__name__}: {args.exc_value}'
                )
                jesse_logger.info(
                    str(traceback.format_exc())
                )
                
                # Store exception in live session
                try:
                    live_session_repository.store_live_session_exception(
                        store.app.session_id,
                        f"{args.exc_type.__name__}: {str(args.exc_value)}",
                        str(traceback.format_exc())
                    )
                    live_session_repository.update_live_session_status(store.app.session_id, live_session_statuses.STOPPED)
                    live_session_repository.update_live_session_finished(store.app.session_id)
                except Exception as e:
                    jh.debug(f'Error storing live session exception: {e}')

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
