from .KuCoinMain import KuCoinMain
from jesse.enums import exchanges
import jesse.helpers as jh
import ccxt


class KuCoinFuturesTestnet(KuCoinMain):
    def __init__(self) -> None:
        super().__init__(
            name=exchanges.KUCOIN_FUTURES_TESTNET,
            rest_endpoint='https://api-sandbox-futures.kucoin.com',
            backup_exchange_class=None
        )
        # Override rate limit for futures testnet (75 requests per second)
        self.rate_limit_per_second = 75
        self.sleep_time = 1 / self.rate_limit_per_second
        
        # Override for futures testnet
        self.exchange = ccxt.kucoinfutures({
            'apiKey': '',  # No API key needed for public data
            'secret': '',
            'password': '',
            'sandbox': True,  # Enable sandbox mode
            'enableRateLimit': True,
            'timeout': 30000,
        })

    def _convert_symbol(self, symbol: str) -> str:
        """Convert Jesse symbol format to CCXT format for futures testnet"""
        # Jesse uses BTC-USDT, CCXT futures uses BTC/USDT:USDT
        return symbol.replace('-', '/') + ':USDT'

    def get_available_symbols(self) -> list:
        try:
            markets = self.exchange.load_markets()
            
            # Filter only trading symbols for futures
            trading_symbols = []
            for symbol, market in markets.items():
                if market.get('active', False) and market.get('type') == 'future':
                    # Convert from CCXT format (BTC/USDT:USDT) to Jesse format (BTC-USDT)
                    # Remove the :USDT suffix and replace / with -
                    jesse_symbol = symbol.replace(':USDT', '').replace('/', '-')
                    trading_symbols.append(jesse_symbol)
            
            return trading_symbols
            
        except Exception as e:
            print(f"Error getting available symbols: {str(e)}")
            return []