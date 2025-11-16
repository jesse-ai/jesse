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
        # Override for futures testnet
        self.exchange = ccxt.kucoinfutures({
            'apiKey': '',  # No API key needed for public data
            'secret': '',
            'password': '',
            'sandbox': True,  # Enable sandbox mode
            'enableRateLimit': True,
            'timeout': 30000,
        })

    def get_available_symbols(self) -> list:
        try:
            markets = self.exchange.load_markets()
            
            # Filter only trading symbols for futures
            trading_symbols = []
            for symbol, market in markets.items():
                if market.get('active', False) and market.get('type') == 'future':
                    # Convert from CCXT format (BTC/USDT) to Jesse format (BTC-USDT)
                    jesse_symbol = symbol.replace('/', '-')
                    trading_symbols.append(jesse_symbol)
            
            return trading_symbols
            
        except Exception as e:
            print(f"Error getting available symbols: {str(e)}")
            return []