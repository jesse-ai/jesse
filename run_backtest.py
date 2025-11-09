#!/usr/bin/env python3
"""
Run Backtest with Fractal Genetic Strategy using CSV data

This script:
1. Loads BTC 15m data from CSV
2. Runs backtest with FractalGeneticStrategy
3. Displays comprehensive results
"""

import sys
import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import Jesse modules
from jesse import research
from jesse.config import config, reset_config
from jesse.routes import router
from jesse.enums import timeframes
from jesse.modes import backtest_mode
from jesse.services import metrics as metrics_module


def setup_environment():
    """Setup Jesse environment for backtesting"""
    reset_config()

    # Configure database (using SQLite for simplicity)
    config['env']['databases']['postgres_host'] = '127.0.0.1'
    config['env']['databases']['postgres_name'] = 'jesse_db'
    config['env']['databases']['postgres_port'] = 5432
    config['env']['databases']['postgres_username'] = 'jesse_user'
    config['env']['databases']['postgres_password'] = 'password'

    # Use in-memory data instead of database
    config['app']['trading_mode'] = 'backtest'


def load_csv_candles(csv_file: str) -> pd.DataFrame:
    """Load candles from Jesse-format CSV"""
    print(f"\n📂 Loading candles from {csv_file}")
    df = pd.read_csv(csv_file)

    print(f"✅ Loaded {len(df)} candles")
    print(f"📅 Date range: {datetime.fromtimestamp(df['timestamp'].iloc[0]/1000)} to {datetime.fromtimestamp(df['timestamp'].iloc[-1]/1000)}")

    return df


def prepare_candles_array(df: pd.DataFrame) -> np.ndarray:
    """
    Convert DataFrame to Jesse candles format

    Jesse expects: [timestamp, open, close, high, low, volume]
    """
    candles = np.array([
        df['timestamp'].values,
        df['open'].values,
        df['close'].values,
        df['high'].values,
        df['low'].values,
        df['volume'].values,
    ]).T

    return candles


def run_backtest_with_csv(
    csv_file: str,
    start_date: str,
    finish_date: str,
    exchange: str = 'Binance',
    symbol: str = 'BTC-USDT',
    timeframe: str = '15m',
    strategy_name: str = 'FractalGeneticOptimization',
    starting_balance: int = 10000
):
    """
    Run backtest using CSV data

    Args:
        csv_file: Path to Jesse-format CSV file
        start_date: Start date (YYYY-MM-DD)
        finish_date: End date (YYYY-MM-DD)
        exchange: Exchange name
        symbol: Trading pair
        timeframe: Timeframe (15m, 1h, etc.)
        strategy_name: Strategy module name
        starting_balance: Starting capital in USDT
    """

    print("=" * 80)
    print("🚀 Jesse Fractal Genetic Strategy Backtest")
    print("=" * 80)

    # Setup environment
    setup_environment()

    # Load candles
    df = load_csv_candles(csv_file)

    # Filter by date range
    start_ts = int(datetime.strptime(start_date, '%Y-%m-%d').timestamp() * 1000)
    finish_ts = int(datetime.strptime(finish_date, '%Y-%m-%d').timestamp() * 1000)

    df_filtered = df[(df['timestamp'] >= start_ts) & (df['timestamp'] <= finish_ts)]

    print(f"\n📊 Filtered to date range: {start_date} to {finish_date}")
    print(f"   Total candles: {len(df_filtered)}")

    if len(df_filtered) == 0:
        print("❌ No candles in date range!")
        return

    # Prepare candles
    candles = prepare_candles_array(df_filtered)

    # Setup route
    router.reset()
    router.set_routes([
        (exchange, symbol, timeframe, strategy_name),
    ])

    print(f"\n⚙️  Configuration:")
    print(f"   Exchange: {exchange}")
    print(f"   Symbol: {symbol}")
    print(f"   Timeframe: {timeframe}")
    print(f"   Strategy: {strategy_name}")
    print(f"   Starting Balance: ${starting_balance:,}")

    # Setup store with candles
    from jesse.store import store
    from jesse.models import Candle

    # Clear any existing data
    store.reset()

    # Initialize exchange
    exchange_obj = store.exchanges.storage[exchange]
    exchange_obj.starting_balance = starting_balance
    exchange_obj.balance = starting_balance

    print(f"\n🔄 Running backtest...")
    print(f"   This may take several minutes for {len(df_filtered)} candles...")

    try:
        # Import and run backtest using research module
        result = research.backtest(
            config={
                'starting_balance': starting_balance,
                'fee': 0.001,  # 0.1% trading fee
                'futures_leverage': 1,
                'futures_leverage_mode': 'cross',
                'exchange': exchange,
                'settlement_currency': 'USDT',
                'warm_up_candles': 500,  # Extra candles for indicators
            },
            routes=[
                {'exchange': exchange, 'strategy': strategy_name, 'symbol': symbol, 'timeframe': timeframe}
            ],
            extra_routes=[],
            candles={
                f"{exchange}-{symbol}": {
                    timeframe: candles
                }
            },
            chart=False,
            csv=False,
            json=False,
            tradingview=False,
            full_reports=True,
        )

        print("\n" + "=" * 80)
        print("📈 BACKTEST RESULTS")
        print("=" * 80)

        # Display results
        if result:
            metrics = result.get('metrics', {})

            print(f"\n💰 Performance Metrics:")
            print(f"   Total Net Profit: ${metrics.get('net_profit', 0):,.2f}")
            print(f"   Total Net Profit %: {metrics.get('net_profit_percentage', 0):.2f}%")
            print(f"   Starting Balance: ${metrics.get('starting_balance', starting_balance):,.2f}")
            print(f"   Finishing Balance: ${metrics.get('finishing_balance', 0):,.2f}")

            print(f"\n📊 Trading Statistics:")
            print(f"   Total Trades: {metrics.get('total_trades', 0)}")
            print(f"   Winning Trades: {metrics.get('winning_trades', 0)}")
            print(f"   Losing Trades: {metrics.get('losing_trades', 0)}")
            print(f"   Win Rate: {metrics.get('win_rate', 0):.2f}%")

            print(f"\n💵 Trade Analysis:")
            print(f"   Gross Profit: ${metrics.get('gross_profit', 0):,.2f}")
            print(f"   Gross Loss: ${metrics.get('gross_loss', 0):,.2f}")
            print(f"   Max Drawdown: ${metrics.get('max_drawdown', 0):,.2f}")
            print(f"   Max Drawdown %: {metrics.get('max_drawdown_percentage', 0):.2f}%")

            print(f"\n📈 Ratios:")
            print(f"   Sharpe Ratio: {metrics.get('sharpe_ratio', 0):.2f}")
            print(f"   Sortino Ratio: {metrics.get('sortino_ratio', 0):.2f}")
            print(f"   Calmar Ratio: {metrics.get('calmar_ratio', 0):.2f}")
            print(f"   Profit Factor: {metrics.get('profit_factor', 0):.2f}")

            # Save detailed report
            report_file = f"backtest_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            with open(report_file, 'w') as f:
                f.write(str(result))
            print(f"\n📝 Detailed report saved to: {report_file}")

        else:
            print("⚠️  No results returned from backtest")

    except Exception as e:
        print(f"\n❌ Error during backtest:")
        print(f"   {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        return None

    return result


if __name__ == "__main__":
    # Configuration
    CSV_FILE = "btc_15m_jesse_format.csv"

    # Test with a reasonable date range (last 2 years for faster testing)
    START_DATE = "2023-01-01"
    FINISH_DATE = "2025-01-01"

    # You can also test different periods:
    # START_DATE = "2020-01-01"  # Longer backtest
    # FINISH_DATE = "2021-01-01"

    print("\n💡 Tip: Edit this script to change date ranges and parameters")
    print(f"   Current range: {START_DATE} to {FINISH_DATE}\n")

    result = run_backtest_with_csv(
        csv_file=CSV_FILE,
        start_date=START_DATE,
        finish_date=FINISH_DATE,
        starting_balance=10000
    )

    if result:
        print("\n✅ Backtest completed successfully!")
    else:
        print("\n❌ Backtest failed!")
        sys.exit(1)
