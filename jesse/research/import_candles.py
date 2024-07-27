def import_candles(
    exchange: str,
    symbol: str,
    start_date: str,
    show_progressbar: bool = True,
) -> str:
    from jesse.modes.import_candles_mode import run

    return run(
        client_id='',
        exchange=exchange,
        symbol=symbol,
        start_date_str=start_date,
        running_via_dashboard=False,
        show_progressbar=show_progressbar
    )
