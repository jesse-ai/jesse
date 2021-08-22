import os
import jesse.helpers as jh
from jesse.services import logger as jesse_logger
import threading
import traceback
import logging
from jesse.services.redis import sync_publish


def register_custom_exception_handler() -> None:
    log_format = "%(message)s"
    os.makedirs('storage/logs/live-mode', exist_ok=True)
    os.makedirs('storage/logs/backtest-mode', exist_ok=True)
    os.makedirs('storage/logs/optimize-mode', exist_ok=True)
    os.makedirs('storage/logs/collect-mode', exist_ok=True)

    session_id = jh.get_session_id()

    if jh.is_live():
        logging.basicConfig(filename=f'storage/logs/live-mode/{session_id}.txt', level=logging.INFO,
                            filemode='w', format=log_format)
    elif jh.is_collecting_data():
        logging.basicConfig(filename=f'storage/logs/collect-mode/{session_id}.txt', level=logging.INFO, filemode='w',
                            format=log_format)
    elif jh.is_optimizing():
        logging.basicConfig(filename=f'storage/logs/optimize-mode/{session_id}.txt', level=logging.INFO, filemode='w',
                            format=log_format)
    elif jh.is_backtesting():
        logging.basicConfig(filename=f'storage/logs/backtest-mode/{session_id}.txt', level=logging.INFO, filemode='w',
                            format=log_format)
    else:
        logging.basicConfig(filename=f'storage/logs/etc.txt', level=logging.INFO, filemode='w',
                            format=log_format)

    # other threads
    def handle_thread_exception(args) -> None:
        if args.exc_type == SystemExit:
            return

        # send notifications if it's a live session
        if jh.is_live():
            jesse_logger.error(
                f'{args.exc_type.__name__}: {args.exc_value}'
            )

        sync_publish('exception', {
            'error': f"{args.exc_type.__name__}: {str(args.exc_value)}",
            'traceback': str(traceback.format_exc())
        })

        terminate_session()

    threading.excepthook = handle_thread_exception


def terminate_session():
    sync_publish('termination', {
        'message': "Session terminated as the result of an uncaught exception",
    })

    jesse_logger.error(
        f"Session terminated as the result of an uncaught exception"
    )

    jh.terminate_app()
