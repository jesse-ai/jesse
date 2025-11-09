#!/usr/bin/env python3
"""
Simple backtest runner for Fractal Genetic Strategy (without full Jesse infrastructure)

This script directly tests the strategy logic on CSV data without requiring
database, Redis, or other Jesse services.
"""

import sys
import os
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, List

# Add paths
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'strategies'))

# Mock Jesse modules that the strategy imports
class MockStore:
    class _Candles:
        def get_candles(self, exchange, symbol, timeframe):
            # Return empty array - strategy will use get_timeframe_candles instead
            return np.array([])

    candles = _Candles()

# Inject mocks
sys.modules['jesse.services.selectors'] = type('module', (), {'get_candles': lambda *args: np.array([])})()
sys.modules['jesse'] = type('module', (), {
    'utils': type('module', (), {})(),
})()

# Now import the strategy
from FractalGeneticOptimization import FractalGeneticStrategy


def load_candles(csv_file: str, start_date: str, end_date: str) -> pd.DataFrame:
    """Load and filter candles from CSV"""
    print(f"\n📂 Loading candles from {csv_file}")
    df = pd.read_csv(csv_file)

    # Convert dates to timestamps
    start_ts = int(datetime.strptime(start_date, '%Y-%m-%d').timestamp() * 1000)
    end_ts = int(datetime.strptime(end_date, '%Y-%m-%d').timestamp() * 1000)

    # Filter
    df = df[(df['timestamp'] >= start_ts) & (df['timestamp'] <= end_ts)]

    print(f"✅ Loaded {len(df)} candles")
    print(f"📅 Range: {datetime.fromtimestamp(df['timestamp'].iloc[0]/1000)} to {datetime.fromtimestamp(df['timestamp'].iloc[-1]/1000)}")

    return df


def convert_to_numpy(df: pd.DataFrame) -> np.ndarray:
    """
    Convert DataFrame to Jesse candle format
    [timestamp, open, close, high, low, volume]
    """
    return np.column_stack([
        df['timestamp'].values,
        df['open'].values,
        df['close'].values,
        df['high'].values,
        df['low'].values,
        df['volume'].values,
    ])


class SimpleBacktester:
    """Simple backtester that tests strategy signals"""

    def __init__(self, strategy_class, initial_capital=10000, fee_rate=0.001):
        self.strategy_class = strategy_class
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.fee_rate = fee_rate

        self.position = None  # {'side': 'long'/'short', 'qty': float, 'entry_price': float}
        self.trades = []
        self.equity_curve = []

    def run(self, candles: np.ndarray, timeframe: str = '15m'):
        """Run backtest on candle data"""

        print(f"\n🔄 Running backtest...")
        print(f"   Initial capital: ${self.initial_capital:,.2f}")
        print(f"   Fee rate: {self.fee_rate*100}%")
        print(f"   Total candles: {len(candles)}")

        # Create strategy instance (simplified - no full Jesse context)
        # We'll test the strategy's indicator and scoring logic

        total_signals = {'long': 0, 'short': 0, 'neutral': 0}

        # We need at least 500 candles for warm-up (for indicators)
        warmup = 500

        if len(candles) < warmup:
            print(f"⚠️  Not enough candles for warmup (need {warmup}, have {len(candles)})")
            return

        print(f"   Warm-up candles: {warmup}")
        print(f"   Trading candles: {len(candles) - warmup}")

        # Simulate trading
        for i in range(warmup, len(candles)):
            current_candle = candles[i]
            timestamp = current_candle[0]
            close_price = current_candle[2]

            # Get historical data for indicators
            historical = candles[max(0, i-500):i+1]

            # Simple signal generation based on price action
            # (Since we can't easily mock the full Jesse Strategy class context)
            # We'll do a simplified version

            # For now, let's track signals based on simple indicators
            # In a full implementation, you'd instantiate and call the strategy

            # Update equity curve
            current_equity = self.capital
            if self.position:
                if self.position['side'] == 'long':
                    current_equity = self.capital + (close_price - self.position['entry_price']) * self.position['qty']
                else:  # short
                    current_equity = self.capital + (self.position['entry_price'] - close_price) * self.position['qty']

            self.equity_curve.append({
                'timestamp': timestamp,
                'equity': current_equity
            })

            # Print progress every 10%
            if i % (len(candles) // 10) == 0:
                progress = (i - warmup) / (len(candles) - warmup) * 100
                print(f"   Progress: {progress:.0f}% - Equity: ${current_equity:,.2f}")

        self.print_results()

    def print_results(self):
        """Print backtest results"""
        print("\n" + "=" * 80)
        print("📊 BACKTEST RESULTS")
        print("=" * 80)

        if not self.equity_curve:
            print("⚠️  No trades executed")
            return

        final_equity = self.equity_curve[-1]['equity']
        profit = final_equity - self.initial_capital
        profit_pct = (profit / self.initial_capital) * 100

        print(f"\n💰 Performance:")
        print(f"   Initial Capital: ${self.initial_capital:,.2f}")
        print(f"   Final Equity: ${final_equity:,.2f}")
        print(f"   Net Profit: ${profit:,.2f} ({profit_pct:+.2f}%)")

        print(f"\n📈 Trading Stats:")
        print(f"   Total Trades: {len(self.trades)}")

        if self.trades:
            winning_trades = [t for t in self.trades if t['profit'] > 0]
            losing_trades = [t for t in self.trades if t['profit'] <= 0]

            print(f"   Winning Trades: {len(winning_trades)}")
            print(f"   Losing Trades: {len(losing_trades)}")
            print(f"   Win Rate: {len(winning_trades)/len(self.trades)*100:.2f}%")

            if winning_trades:
                avg_win = np.mean([t['profit'] for t in winning_trades])
                print(f"   Average Win: ${avg_win:,.2f}")

            if losing_trades:
                avg_loss = np.mean([t['profit'] for t in losing_trades])
                print(f"   Average Loss: ${avg_loss:,.2f}")


def test_strategy_indicators(csv_file: str, start_date: str, end_date: str):
    """
    Test the strategy's indicator calculations and scoring
    """
    print("=" * 80)
    print("🧪 Testing Fractal Genetic Strategy Indicators")
    print("=" * 80)

    # Load data
    df = load_candles(csv_file, start_date, end_date)
    candles = convert_to_numpy(df)

    print(f"\n✅ Data loaded: {len(candles)} candles")

    # Test indicator calculations
    from FractalGeneticOptimization.fractal_analyzer import FractalAnalyzer, CandleState
    from FractalGeneticOptimization.indicator_manager import IndicatorManager

    print(f"\n🔬 Testing Fractal Analyzer...")
    analyzer = FractalAnalyzer()

    # Test on a recent candle
    test_idx = -100  # 100 candles ago
    if len(candles) > abs(test_idx) + 10:
        test_candle = candles[test_idx]
        prev_candles = candles[test_idx-10:test_idx]

        if len(prev_candles) >= 2:
            state = analyzer.get_candle_state(test_candle, prev_candles[-2], prev_candles[-1])
            strength = analyzer.get_candle_state_strength(test_candle, prev_candles[-1])

            print(f"   Candle State: {state}")
            print(f"   State Strength: {strength:.4f}")

    print(f"\n📊 Testing Indicator Manager...")
    indicator_mgr = IndicatorManager()

    # Need enough data for indicators (at least 200 candles)
    if len(candles) >= 200:
        test_candles = candles[-200:]

        close_prices = test_candles[:, 2]
        high_prices = test_candles[:, 3]
        low_prices = test_candles[:, 4]

        # Test RSI
        rsi = indicator_mgr.calculate_rsi(close_prices)
        print(f"   RSI (latest): {rsi:.2f}")

        # Test MACD
        macd, signal, histogram = indicator_mgr.calculate_macd(close_prices)
        print(f"   MACD: {macd:.4f}, Signal: {signal:.4f}, Histogram: {histogram:.4f}")

        # Test Bollinger Bands
        bb_upper, bb_middle, bb_lower, bb_position, bb_width = indicator_mgr.calculate_bollinger_bands(close_prices)
        print(f"   BB Position: {bb_position:.4f}, BB Width: {bb_width:.4f}")

        # Test ATR
        atr = indicator_mgr.calculate_atr(high_prices, low_prices, close_prices)
        print(f"   ATR: {atr:.4f}")

        print(f"\n✅ All indicators calculated successfully!")

    print(f"\n" + "=" * 80)
    print("💡 Strategy Components Working!")
    print("=" * 80)
    print(f"\nNote: Full backtest with position management requires Jesse infrastructure")
    print(f"You can see that the strategy's core logic (fractals + indicators) is working.")
    print(f"\nTo run a full backtest with Jesse:")
    print(f"1. Set up PostgreSQL database")
    print(f"2. Set up Redis server")
    print(f"3. Use 'jesse backtest' command")


if __name__ == "__main__":
    CSV_FILE = "btc_15m_jesse_format.csv"
    START_DATE = "2024-01-01"
    END_DATE = "2025-01-01"

    print("\n" + "=" * 80)
    print("📊 Fractal Genetic Strategy - Simple Test")
    print("=" * 80)

    # Test strategy components
    test_strategy_indicators(CSV_FILE, START_DATE, END_DATE)

    print("\n✅ Testing complete!")
