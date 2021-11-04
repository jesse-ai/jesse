import jesse.helpers as jh
from jesse.services import logger as jesse_logger
import threading
import traceback
from jesse.services.redis import sync_publish


def register_custom_exception_handler() -> None:
    # log_format = "%(message)s"
    # session_id = jh.get_session_id()

    # jh.make_directory('storage/logs/live-mode')
    # jh.make_directory('storage/logs/backtest-mode')
    # jh.make_directory('storage/logs/optimize-mode')
    # jh.make_directory('storage/logs/collect-mode')
    #
    # if jh.is_live():
    #     filename = f'storage/logs/live-mode/{jh.now(True)}--{session_id}.txt'
    # elif jh.is_collecting_data():
    #     filename = f'storage/logs/collect-mode/{jh.now(True)}--{session_id}.txt'
    # elif jh.is_optimizing():
    #     filename = f'storage/logs/optimize-mode/{jh.now(True)}--{session_id}.txt'
    # elif jh.is_backtesting():
    #     filename = f'storage/logs/backtest-mode/{jh.now(True)}--{session_id}.txt'
    # else:
    #     filename = f'storage/logs/etc.txt'
    #
    # logging.basicConfig(filename=filename, level=logging.INFO, filemode='w', format=log_format)

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

    jesse_logger.error(
        f"Session terminated as the result of an uncaught exception"
    )

    jh.terminate_app()
