import os
import jesse.helpers as jh
from jesse.services import logger as jesse_logger
import threading
import traceback
import logging
from jesse.services.redis import sync_publish


def register_custom_exception_handler() -> None:
    log_format = "%(message)s"
    os.makedirs('storage/logs', exist_ok=True)

    if jh.is_livetrading():
        logging.basicConfig(filename='storage/logs/live-trade.txt', level=logging.INFO,
                            filemode='w', format=log_format)
    elif jh.is_paper_trading():
        logging.basicConfig(filename='storage/logs/paper-trade.txt', level=logging.INFO,
                            filemode='w',
                            format=log_format)
    elif jh.is_collecting_data():
        logging.basicConfig(filename='storage/logs/collect.txt', level=logging.INFO, filemode='w',
                            format=log_format)
    elif jh.is_optimizing():
        logging.basicConfig(filename='storage/logs/optimize.txt', level=logging.INFO, filemode='w',
                            format=log_format)
    else:
        logging.basicConfig(level=logging.INFO)

    # TODO: for the actual main thread it doesn't work. Should we worry?
    # # main thread
    # def handle_exception(exc_type, exc_value, exc_traceback) -> None:
    #     print('====')
    #     print('oops error in the MAIN thread')
    #     print('====')
    #
    #     if issubclass(exc_type, KeyboardInterrupt):
    #         sys.excepthook(exc_type, exc_value, exc_traceback)
    #         return
    #
    #     # send notifications if it's a live session
    #     if jh.is_live():
    #         jesse_logger.error(
    #             f'{exc_type.__name__}: {exc_value}'
    #         )
    #
    #     sync_publish('exception', {
    #         'error': f"{type(exc_type.__name__)}: {str(exc_value)}",
    #         'traceback': str(traceback.format_exc())
    #     })
    #
    # sys.excepthook = handle_exception

    # other threads
    def handle_thread_exception(args) -> None:
        print('\n')
        print('other threads')
        print('\n')

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

        print('Unhandled exception in the thread:')
        print(traceback.format_exc())

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
