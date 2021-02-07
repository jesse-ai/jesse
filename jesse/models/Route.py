class Route:
    def __init__(self, exchange: str, symbol: str, timeframe: str = None, strategy_name: str = None,
                 dna: str = None) -> None:
        self.exchange = exchange
        self.symbol = symbol
        self.timeframe = timeframe
        self.strategy_name = strategy_name
        self.strategy = None
        self.dna = dna
