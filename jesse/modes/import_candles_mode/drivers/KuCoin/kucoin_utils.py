def timeframe_to_interval(timeframe: str) -> str:
    """
    Convert Jesse timeframe to KuCoin interval format
    """
    timeframe_map = {
        '1m': '1min',
        '3m': '3min', 
        '5m': '5min',
        '15m': '15min',
        '30m': '30min',
        '1h': '1hour',
        '2h': '2hour',
        '4h': '4hour',
        '6h': '6hour',
        '8h': '8hour',
        '12h': '12hour',
        '1D': '1day',
        '1W': '1week',
        '1M': '1month'
    }
    
    if timeframe not in timeframe_map:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    
    return timeframe_map[timeframe]