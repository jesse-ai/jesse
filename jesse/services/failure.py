import os
import jesse.helpers as jh


def register_custom_exception_handler() -> None:
    import sys
    import threading
    import traceback
    import logging
    from jesse.services import logger as jesse_logger
    import click
    from jesse import exceptions

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

    # main thread
    def handle_exception(exc_type, exc_value, exc_traceback) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.excepthook(exc_type, exc_value, exc_traceback)
            return

        # handle Breaking exceptions
        if exc_type in [
            exceptions.InvalidConfig, exceptions.RouteNotFound, exceptions.InvalidRoutes,
            exceptions.CandleNotFoundInDatabase
        ]:
            click.clear()
            print(f"{'=' * 30} EXCEPTION TRACEBACK:")
            traceback.print_tb(exc_traceback, file=sys.stdout)
            print("=" * 73)
            print(
                '\n',
                jh.color('Uncaught Exception:', 'red'),
                jh.color(f'{exc_type.__name__}: {exc_value}', 'yellow')
            )
            return

        # send notifications if it's a live session
        if jh.is_live():
            jesse_logger.error(
                f'{exc_type.__name__}: {exc_value}'
            )

        if jh.is_live() or jh.is_collecting_data():
            logging.error("Uncaught Exception:", exc_info=(exc_type, exc_value, exc_traceback))
        else:
            print(f"{'=' * 30} EXCEPTION TRACEBACK:")
            traceback.print_tb(exc_traceback, file=sys.stdout)
            print("=" * 73)
            print(
                '\n',
                jh.color('Uncaught Exception:', 'red'),
                jh.color(f'{exc_type.__name__}: {exc_value}', 'yellow')
            )

        if jh.is_paper_trading():
            print(
                jh.color(
                    'An uncaught exception was raised. Check the log file at:\nstorage/logs/paper-trade.txt',
                    'red'
                )
            )
        elif jh.is_livetrading():
            print(
                jh.color(
                    'An uncaught exception was raised. Check the log file at:\nstorage/logs/live-trade.txt',
                    'red'
                )
            )
        elif jh.is_collecting_data():
            print(
                jh.color(
                    'An uncaught exception was raised. Check the log file at:\nstorage/logs/collect.txt',
                    'red'
                )
            )

    sys.excepthook = handle_exception

    # other threads
    if jh.python_version() >= 3.8:
        def handle_thread_exception(args) -> None:
            if args.exc_type == SystemExit:
                return

            # handle Breaking exceptions
            if args.exc_type in [
                exceptions.InvalidConfig, exceptions.RouteNotFound, exceptions.InvalidRoutes,
                exceptions.CandleNotFoundInDatabase
            ]:
                click.clear()
                print(f"{'=' * 30} EXCEPTION TRACEBACK:")
                traceback.print_tb(args.exc_traceback, file=sys.stdout)
                print("=" * 73)
                print(
                    '\n',
                    jh.color('Uncaught Exception:', 'red'),
                    jh.color(f'{args.exc_type.__name__}: {args.exc_value}', 'yellow')
                )
                return

            # send notifications if it's a live session
            if jh.is_live():
                jesse_logger.error(
                    f'{args.exc_type.__name__}: {args.exc_value}'
                )

            if jh.is_live() or jh.is_collecting_data():
                logging.error("Uncaught Exception:",
                              exc_info=(args.exc_type, args.exc_value, args.exc_traceback))
            else:
                print(f"{'=' * 30} EXCEPTION TRACEBACK:")
                traceback.print_tb(args.exc_traceback, file=sys.stdout)
                print("=" * 73)
                print(
                    '\n',
                    jh.color('Uncaught Exception:', 'red'),
                    jh.color(f'{args.exc_type.__name__}: {args.exc_value}', 'yellow')
                )

            if jh.is_paper_trading():
                print(
                    jh.color(
                        'An uncaught exception was raised. Check the log file at:\nstorage/logs/paper-trade.txt',
                        'red'
                    )
                )
            elif jh.is_livetrading():
                print(
                    jh.color(
                        'An uncaught exception was raised. Check the log file at:\nstorage/logs/live-trade.txt',
                        'red'
                    )
                )
            elif jh.is_collecting_data():
                print(
                    jh.color(
                        'An uncaught exception was raised. Check the log file at:\nstorage/logs/collect.txt',
                        'red'
                    )
                )

        threading.excepthook = handle_thread_exception
