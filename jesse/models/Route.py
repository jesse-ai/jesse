from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from jesse.strategies import Strategy


class Route:
    def __init__(
            self,
            exchange: str,
            symbol: str,
            timeframe: str = None,
            strategy_name: str = None,
            dna: str = None
    ) -> None:
        self.exchange = exchange
        self.symbol = symbol
        self.timeframe = timeframe
        self.strategy_name = strategy_name
        # set by the router when strategies are initiated, hence declared with
        # its post-initiation type for type checkers
        self.strategy: 'Strategy' = None  # type: ignore
        self.dna = dna
