from .KuCoinMain import KuCoinMain
from jesse.enums import exchanges
import jesse.helpers as jh
import ccxt
from typing import Union


class KuCoinFutures(KuCoinMain):
    def __init__(self) -> None:
        super().__init__(
            name=exchanges.KUCOIN_FUTURES,
            rest_endpoint='https://api-futures.kucoin.com',
            backup_exchange_class=None
        )
        # Override rate limit for futures (75 requests per second)
        self.rate_limit_per_second = 75
        self.sleep_time = 1 / self.rate_limit_per_second
        
        # Override for futures
        self.exchange = ccxt.kucoinfutures({
            'apiKey': '',  # No API key needed for public data
            'secret': '',
            'password': '',
            'sandbox': False,
            'enableRateLimit': True,
            'timeout': 30000,
        })

    def _convert_symbol(self, symbol: str) -> str:
        """Convert Jesse symbol format to CCXT format for futures"""
        # Jesse uses BTC-USDT, CCXT futures uses BTC/USDT:USDT
        return symbol.replace('-', '/') + ':USDT'

    def fetch(self, symbol: str, start_timestamp: int, timeframe: str = '1m') -> Union[list, None]:
        """Override fetch method that returns data ready for storage without _fill_absent_candles processing"""
        try:
            ccxt_symbol = self._convert_symbol(symbol)
            ccxt_timeframe = self._convert_timeframe(timeframe)
            
            # Calculate end timestamp
            end_timestamp = start_timestamp + (self.count - 1) * 60000 * jh.timeframe_to_one_minutes(timeframe)
            
            print(f"[KuCoin Futures] Fetching {symbol} ({ccxt_symbol}) from {start_timestamp} to {end_timestamp}")
            
            # Check if symbol is available and active
            try:
                markets = self.exchange.load_markets()
                if ccxt_symbol not in markets:
                    print(f"[KuCoin Futures] Symbol {ccxt_symbol} not found in markets")
                    return []
                
                market_info = markets[ccxt_symbol]
                if not market_info.get('active', False):
                    print(f"[KuCoin Futures] Symbol {ccxt_symbol} is not active")
                    return []
                
                print(f"[KuCoin Futures] Market status: {market_info.get('status', 'unknown')}")
                
            except Exception as e:
                print(f"[KuCoin Futures] Warning: Could not check market status: {e}")
            
            # Fetch OHLCV data with retry logic
            max_retries = 3
            ohlcv = None
            
            for attempt in range(max_retries):
                try:
                    ohlcv = self.exchange.fetch_ohlcv(
                        ccxt_symbol,
                        ccxt_timeframe,
                        since=start_timestamp,
                        limit=self.count
                    )
                    break
                except Exception as e:
                    print(f"[KuCoin Futures] Attempt {attempt + 1} failed: {e}")
                    if attempt < max_retries - 1:
                        import time
                        time.sleep(1)  # Wait 1 second before retry
                    else:
                        raise e
            
            print(f"[KuCoin Futures] Raw API response: {len(ohlcv) if ohlcv else 0} candles")
            
            if not ohlcv:
                print(f"[KuCoin Futures] No data returned from API")
                return []
            
            # Log first few raw candles
            if len(ohlcv) > 0:
                print(f"[KuCoin Futures] First raw candle: {ohlcv[0]}")
                if len(ohlcv) > 1:
                    print(f"[KuCoin Futures] Last raw candle: {ohlcv[-1]}")
            
            # Convert to Jesse format with enhanced validation
            candles = []
            zero_volume_count = 0
            same_prices_count = 0
            invalid_candles = 0
            
            for i, candle in enumerate(ohlcv):
                try:
                    # Validate candle data
                    if len(candle) < 6:
                        print(f"[KuCoin Futures] Invalid candle format at index {i}: {candle}")
                        invalid_candles += 1
                        continue
                    
                    timestamp = int(candle[0])
                    open_price = float(candle[1])
                    high_price = float(candle[2])
                    low_price = float(candle[3])
                    close_price = float(candle[4])
                    volume = float(candle[5])
                    
                    # Validate price data
                    if any(price <= 0 for price in [open_price, high_price, low_price, close_price]):
                        print(f"[KuCoin Futures] Invalid price data at index {i}: {candle}")
                        invalid_candles += 1
                        continue
                    
                    # Validate OHLC logic
                    if not (low_price <= open_price <= high_price and low_price <= close_price <= high_price):
                        print(f"[KuCoin Futures] Invalid OHLC logic at index {i}: {candle}")
                        invalid_candles += 1
                        continue
                    
                    # Check for zero volume
                    if volume == 0:
                        zero_volume_count += 1
                        print(f"[KuCoin Futures] Zero volume candle at {timestamp}: {candle}")
                    
                    # Check for same prices (might indicate no trading activity)
                    if open_price == high_price == low_price == close_price:
                        same_prices_count += 1
                        print(f"[KuCoin Futures] Same prices candle at {timestamp}: {candle}")
                    
                    candles.append({
                        'id': jh.generate_unique_id(),
                        'exchange': self.name,
                        'symbol': symbol,
                        'timeframe': timeframe,
                        'timestamp': timestamp,
                        'open': open_price,
                        'high': high_price,
                        'low': low_price,
                        'close': close_price,
                        'volume': volume
                    })
                    
                except (ValueError, TypeError, IndexError) as e:
                    print(f"[KuCoin Futures] Error processing candle at index {i}: {e}, candle: {candle}")
                    invalid_candles += 1
                    continue
            
            print(f"[KuCoin Futures] Converted {len(candles)} candles")
            print(f"[KuCoin Futures] Zero volume candles: {zero_volume_count} ({zero_volume_count/len(candles)*100:.1f}%)")
            print(f"[KuCoin Futures] Same prices candles: {same_prices_count} ({same_prices_count/len(candles)*100:.1f}%)")
            print(f"[KuCoin Futures] Invalid candles skipped: {invalid_candles}")
            
            # Log first few converted candles
            if len(candles) > 0:
                print(f"[KuCoin Futures] First converted candle: {candles[0]}")
                if len(candles) > 1:
                    print(f"[KuCoin Futures] Last converted candle: {candles[-1]}")
            
            # Additional validation: check for data gaps
            if len(candles) > 1:
                time_diffs = []
                for i in range(1, min(10, len(candles))):
                    diff = (candles[i]['timestamp'] - candles[i-1]['timestamp']) / 1000 / 60  # in minutes
                    time_diffs.append(diff)
                
                expected_interval = jh.timeframe_to_one_minutes(timeframe)
                irregular_intervals = [d for d in time_diffs if abs(d - expected_interval) > 1]
                
                if irregular_intervals:
                    print(f"[KuCoin Futures] Warning: Irregular time intervals detected: {irregular_intervals[:5]}")
            
            # For KuCoin Futures, we return only real data
            # This prevents _fill_absent_candles from creating fake candles
            return candles
            
        except Exception as e:
            print(f"[KuCoin Futures] Error fetching candles for {symbol}: {str(e)}")
            import traceback
            traceback.print_exc()
            return []

    def _create_filled_time_series(self, candles: list, start_timestamp: int, end_timestamp: int, timeframe: str) -> list:
        """Create a time series that fills the expected range without fake candles"""
        if not candles:
            print(f"[KuCoin Futures] No candles to process")
            return []
        
        # Sort candles by timestamp
        sorted_candles = sorted(candles, key=lambda x: x['timestamp'])
        
        print(f"[KuCoin Futures] Creating filled time series from {start_timestamp} to {end_timestamp}")
        print(f"[KuCoin Futures] Available candles: {len(sorted_candles)}")
        
        # Calculate expected interval in milliseconds
        interval_ms = 60000 * jh.timeframe_to_one_minutes(timeframe)
        
        # Create a time series that matches what _fill_absent_candles expects
        result_candles = []
        current_timestamp = start_timestamp
        
        # Create a map of existing candles by timestamp for quick lookup
        existing_candles = {c['timestamp']: c for c in sorted_candles}
        
        # Get the first real candle for reference
        first_candle = sorted_candles[0]
        
        while current_timestamp <= end_timestamp:
            if current_timestamp in existing_candles:
                # Use real candle data
                result_candles.append(existing_candles[current_timestamp])
            else:
                # Create a placeholder candle that _fill_absent_candles will recognize as already filled
                # We use the last known price to maintain continuity
                last_price = first_candle['close']  # Use first candle's close as reference
                
                placeholder_candle = {
                    'id': jh.generate_unique_id(),
                    'exchange': self.name,
                    'symbol': first_candle['symbol'],
                    'timeframe': timeframe,
                    'timestamp': current_timestamp,
                    'open': last_price,
                    'high': last_price,
                    'low': last_price,
                    'close': last_price,
                    'volume': 0  # Zero volume to indicate no trading activity
                }
                result_candles.append(placeholder_candle)
            
            current_timestamp += interval_ms
        
        print(f"[KuCoin Futures] Created filled time series with {len(result_candles)} candles")
        
        # Count real vs placeholder candles
        real_candles = [c for c in result_candles if c['volume'] > 0]
        placeholder_candles = [c for c in result_candles if c['volume'] == 0]
        
        print(f"[KuCoin Futures] Real candles: {len(real_candles)}, Placeholder candles: {len(placeholder_candles)}")
        
        return result_candles

    def _create_complete_time_series(self, candles: list, start_timestamp: int, end_timestamp: int, timeframe: str) -> list:
        """Create a complete time series that prevents _fill_absent_candles from creating fake candles"""
        if not candles:
            print(f"[KuCoin Futures] No candles to process")
            return []
        
        # Sort candles by timestamp
        sorted_candles = sorted(candles, key=lambda x: x['timestamp'])
        
        print(f"[KuCoin Futures] Creating complete time series from {start_timestamp} to {end_timestamp}")
        print(f"[KuCoin Futures] Available candles: {len(sorted_candles)}")
        
        # Calculate expected interval in milliseconds
        interval_ms = 60000 * jh.timeframe_to_one_minutes(timeframe)
        
        # Create a complete time series that matches what _fill_absent_candles expects
        result_candles = []
        current_timestamp = start_timestamp
        
        # Create a map of existing candles by timestamp for quick lookup
        existing_candles = {c['timestamp']: c for c in sorted_candles}
        
        # Get the first and last real candles for reference
        first_candle = sorted_candles[0]
        last_candle = sorted_candles[-1]
        
        while current_timestamp <= end_timestamp:
            if current_timestamp in existing_candles:
                # Use real candle data
                result_candles.append(existing_candles[current_timestamp])
            else:
                # Create a placeholder candle that won't be processed by _fill_absent_candles
                # We use a special marker to indicate this is a placeholder
                placeholder_candle = {
                    'id': jh.generate_unique_id(),
                    'exchange': self.name,
                    'symbol': first_candle['symbol'],
                    'timeframe': timeframe,
                    'timestamp': current_timestamp,
                    'open': 0,  # Special marker
                    'high': 0,  # Special marker
                    'low': 0,   # Special marker
                    'close': 0, # Special marker
                    'volume': -1  # Special marker to indicate placeholder
                }
                result_candles.append(placeholder_candle)
            
            current_timestamp += interval_ms
        
        print(f"[KuCoin Futures] Created complete time series with {len(result_candles)} candles")
        
        # Filter out placeholder candles before returning
        real_candles = [c for c in result_candles if c['volume'] != -1]
        
        print(f"[KuCoin Futures] Returning {len(real_candles)} real candles")
        
        return real_candles

    def _fill_absent_candles(self, temp_candles, start_timestamp, end_timestamp):
        """Override _fill_absent_candles to prevent creation of fake candles for KuCoin Futures"""
        print(f"[KuCoin Futures] _fill_absent_candles called with {len(temp_candles)} input candles")
        print(f"[KuCoin Futures] Time range: {start_timestamp} to {end_timestamp}")
        
        if not temp_candles:
            print(f"[KuCoin Futures] No input candles, returning empty list")
            return []
        
        # For KuCoin Futures, we don't fill absent candles - just return what we have
        # This prevents creation of fake candles with zero volume
        print(f"[KuCoin Futures] Returning {len(temp_candles)} real candles without filling gaps")
        
        # Sort candles by timestamp to ensure proper order
        sorted_candles = sorted(temp_candles, key=lambda x: x['timestamp'])
        
        # Additional analysis
        zero_volume_count = sum(1 for c in sorted_candles if c['volume'] == 0)
        same_prices_count = sum(1 for c in sorted_candles if c['open'] == c['high'] == c['low'] == c['close'])
        
        print(f"[KuCoin Futures] Real candles zero volume: {zero_volume_count} ({zero_volume_count/len(sorted_candles)*100:.1f}%)")
        print(f"[KuCoin Futures] Real candles same prices: {same_prices_count} ({same_prices_count/len(sorted_candles)*100:.1f}%)")
        
        return sorted_candles

# Override the global _fill_absent_candles function for KuCoin Futures
def _fill_absent_candles(temp_candles, start_timestamp, end_timestamp):
    """Override global _fill_absent_candles to prevent creation of fake candles for KuCoin Futures"""
    print(f"[KuCoin Futures] GLOBAL _fill_absent_candles called with {len(temp_candles)} input candles")
    print(f"[KuCoin Futures] Time range: {start_timestamp} to {end_timestamp}")
    
    if not temp_candles:
        print(f"[KuCoin Futures] No input candles, returning empty list")
        return []
    
    # For KuCoin Futures, we don't fill absent candles - just return what we have
    # This prevents creation of fake candles with zero volume
    print(f"[KuCoin Futures] Returning {len(temp_candles)} real candles without filling gaps")
    
    # Sort candles by timestamp to ensure proper order
    sorted_candles = sorted(temp_candles, key=lambda x: x['timestamp'])
    
    # Additional analysis
    zero_volume_count = sum(1 for c in sorted_candles if c['volume'] == 0)
    same_prices_count = sum(1 for c in sorted_candles if c['open'] == c['high'] == c['low'] == c['close'])
    
    print(f"[KuCoin Futures] Real candles zero volume: {zero_volume_count} ({zero_volume_count/len(sorted_candles)*100:.1f}%)")
    print(f"[KuCoin Futures] Real candles same prices: {same_prices_count} ({same_prices_count/len(sorted_candles)*100:.1f}%)")
    
    return sorted_candles

    def get_market_status(self, symbol: str) -> dict:
        """Get detailed market status for a symbol"""
        try:
            ccxt_symbol = self._convert_symbol(symbol)
            markets = self.exchange.load_markets()
            
            if ccxt_symbol not in markets:
                return {'error': f'Symbol {ccxt_symbol} not found'}
            
            market_info = markets[ccxt_symbol]
            return {
                'symbol': ccxt_symbol,
                'active': market_info.get('active', False),
                'status': market_info.get('status', 'unknown'),
                'type': market_info.get('type', 'unknown'),
                'base': market_info.get('base', ''),
                'quote': market_info.get('quote', ''),
                'precision': market_info.get('precision', {}),
                'limits': market_info.get('limits', {}),
                'info': market_info.get('info', {})
            }
        except Exception as e:
            return {'error': str(e)}
    
    def check_trading_hours(self, symbol: str) -> dict:
        """Check if the market is currently trading"""
        try:
            # Get current server time
            server_time = self.exchange.fetch_time()
            
            # Get market status
            market_status = self.get_market_status(symbol)
            
            return {
                'server_time': server_time,
                'market_active': market_status.get('active', False),
                'market_status': market_status.get('status', 'unknown'),
                'is_trading': market_status.get('active', False) and market_status.get('status') == 'ok'
            }
        except Exception as e:
            return {'error': str(e)}
    
    def filter_valid_candles(self, candles: list, min_volume: float = 0.0) -> list:
        """Filter out candles with zero volume or other issues"""
        if not candles:
            return []
        
        valid_candles = []
        filtered_count = 0
        
        for candle in candles:
            # Skip candles with zero volume if min_volume is set
            if min_volume > 0 and candle.get('volume', 0) < min_volume:
                filtered_count += 1
                continue
            
            # Skip candles with invalid OHLC data
            if not self._validate_candle_data(candle):
                filtered_count += 1
                continue
            
            valid_candles.append(candle)
        
        if filtered_count > 0:
            print(f"[KuCoin Futures] Filtered out {filtered_count} invalid candles")
        
        return valid_candles
    
    def _validate_candle_data(self, candle: dict) -> bool:
        """Validate individual candle data"""
        try:
            required_fields = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
            
            # Check required fields
            if not all(field in candle for field in required_fields):
                return False
            
            # Check data types and values
            prices = [candle['open'], candle['high'], candle['low'], candle['close']]
            
            # All prices must be positive
            if not all(price > 0 for price in prices):
                return False
            
            # OHLC logic validation
            if not (candle['low'] <= candle['open'] <= candle['high'] and 
                    candle['low'] <= candle['close'] <= candle['high']):
                return False
            
            # Volume should be non-negative
            if candle['volume'] < 0:
                return False
            
            return True
            
        except (KeyError, TypeError, ValueError):
            return False
    
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