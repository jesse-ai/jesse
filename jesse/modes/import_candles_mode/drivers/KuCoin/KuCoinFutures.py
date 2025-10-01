from .KuCoinMain import KuCoinMain


class KuCoinFutures(KuCoinMain):
    def __init__(self) -> None:
        # KuCoin Futures is not supported
        raise ValueError(
            'KuCoin Futures is not supported. Please use KuCoin Spot instead.'
        )

    def _convert_symbol(self, symbol: str) -> str:
        """Convert Jesse symbol format to CCXT format for futures"""
        raise ValueError('KuCoin Futures is not supported')

    def get_available_symbols(self) -> list:
        raise ValueError('KuCoin Futures is not supported')