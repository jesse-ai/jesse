"""
Example Configuration File for Fractal Genetic Optimization Strategy

This file shows how to configure Jesse to use the FractalGeneticStrategy.
Copy the relevant sections to your project's config.py file.
"""

# ======================
# STRATEGY IMPORT
# ======================
from jesse.strategies import FractalGeneticStrategy


# ======================
# TRADING ROUTES
# ======================

# Single pair configuration (recommended for beginners)
routes = [
    {
        'exchange': 'Binance Futures',
        'symbol': 'BTC-USDT',
        'timeframe': '5m',
        'strategy': 'FractalGeneticStrategy'
    },
]

# Multi-pair configuration (advanced)
# routes = [
#     {
#         'exchange': 'Binance Futures',
#         'symbol': 'BTC-USDT',
#         'timeframe': '5m',
#         'strategy': 'FractalGeneticStrategy'
#     },
#     {
#         'exchange': 'Binance Futures',
#         'symbol': 'ETH-USDT',
#         'timeframe': '5m',
#         'strategy': 'FractalGeneticStrategy'
#     },
# ]


# ======================
# EXTRA CANDLES (REQUIRED!)
# ======================

# Minimum recommended timeframes for single pair
extra_candles = [
    ('Binance Futures', 'BTC-USDT', '1D'),   # Daily (important for trend)
    ('Binance Futures', 'BTC-USDT', '4h'),   # 4-hour (medium-term)
    ('Binance Futures', 'BTC-USDT', '1h'),   # 1-hour (short-term)
    ('Binance Futures', 'BTC-USDT', '15m'),  # 15-minute (micro-trend)
]

# Extended timeframes for better analysis
# extra_candles = [
#     ('Binance Futures', 'BTC-USDT', '1W'),   # Weekly (very long-term)
#     ('Binance Futures', 'BTC-USDT', '1D'),   # Daily
#     ('Binance Futures', 'BTC-USDT', '12h'),  # 12-hour
#     ('Binance Futures', 'BTC-USDT', '8h'),   # 8-hour
#     ('Binance Futures', 'BTC-USDT', '4h'),   # 4-hour
#     ('Binance Futures', 'BTC-USDT', '2h'),   # 2-hour
#     ('Binance Futures', 'BTC-USDT', '1h'),   # 1-hour
#     ('Binance Futures', 'BTC-USDT', '30m'),  # 30-minute
#     ('Binance Futures', 'BTC-USDT', '15m'),  # 15-minute
#     ('Binance Futures', 'BTC-USDT', '10m'),  # 10-minute
# ]

# Multi-pair extra candles
# extra_candles = [
#     # BTC
#     ('Binance Futures', 'BTC-USDT', '1D'),
#     ('Binance Futures', 'BTC-USDT', '4h'),
#     ('Binance Futures', 'BTC-USDT', '1h'),
#     ('Binance Futures', 'BTC-USDT', '15m'),
#     # ETH
#     ('Binance Futures', 'ETH-USDT', '1D'),
#     ('Binance Futures', 'ETH-USDT', '4h'),
#     ('Binance Futures', 'ETH-USDT', '1h'),
#     ('Binance Futures', 'ETH-USDT', '15m'),
# ]


# ======================
# EXCHANGE SETTINGS
# ======================

# For backtesting
config = {
    'env': 'backtest',
    'exchanges': {
        'Binance Futures': {
            'fee': 0.04,  # 0.04% (maker/taker average)
            'type': 'futures',
            'futures_leverage': 2,  # 2x leverage (conservative)
            'futures_leverage_mode': 'cross',
            'settlement_currency': 'USDT',
        }
    }
}

# For live/paper trading
# config = {
#     'env': 'livetrade',  # or 'papertrade'
#     'exchanges': {
#         'Binance Futures': {
#             'fee': 0.04,
#             'type': 'futures',
#             'futures_leverage': 2,
#             'futures_leverage_mode': 'cross',
#             'settlement_currency': 'USDT',
#             'api_key': 'YOUR_API_KEY',
#             'api_secret': 'YOUR_API_SECRET',
#         }
#     },
#     'notifications': {
#         'events': {
#             'updated_position': True,
#             'started': True,
#             'terminated': True,
#         },
#         'drivers': {
#             'telegram': {
#                 'enabled': True,
#                 'token': 'YOUR_TELEGRAM_BOT_TOKEN',
#                 'chat_id': 'YOUR_CHAT_ID',
#             }
#         }
#     }
# }


# ======================
# OPTIMIZATION SETTINGS
# ======================

# DNA configuration for optimization
# These are the hyperparameters that will be optimized
dna_config = {
    # Enabled by default in the strategy
}


# ======================
# EXAMPLE USAGE COMMANDS
# ======================

"""
# BACKTEST (basic)
jesse backtest 2023-01-01 2023-12-31

# BACKTEST (with chart)
jesse backtest 2023-01-01 2023-12-31 --chart

# BACKTEST (with specific DNA)
jesse backtest 2023-01-01 2023-12-31 --dna "YOUR_DNA_STRING"

# OPTIMIZE (basic)
jesse optimize 2023-01-01 2023-06-30 --cpu 8 --iterations 50

# OPTIMIZE (advanced)
jesse optimize 2023-01-01 2023-06-30 \\
  --cpu 8 \\
  --iterations 100 \\
  --population-size 50 \\
  --solution-len 30 \\
  --optimal-total sharpe-ratio

# IMPORT CANDLES (if needed)
jesse import-candles "Binance Futures" BTC-USDT 2020-01-01

# LIVE TRADING (paper mode first!)
jesse run --paper

# LIVE TRADING (real)
jesse run
"""


# ======================
# RECOMMENDED SETTINGS FOR DIFFERENT USE CASES
# ======================

"""
1. CONSERVATIVE (Low Risk)
   - futures_leverage: 1-2x
   - risk_per_trade: 0.01 (1%)
   - stop_loss_atr_multiplier: 2.5-3.0
   - take_profit_atr_multiplier: 2.0-3.0

2. MODERATE (Medium Risk)
   - futures_leverage: 2-3x
   - risk_per_trade: 0.02 (2%)
   - stop_loss_atr_multiplier: 2.0-2.5
   - take_profit_atr_multiplier: 3.0-4.0

3. AGGRESSIVE (High Risk)
   - futures_leverage: 3-5x
   - risk_per_trade: 0.03-0.05 (3-5%)
   - stop_loss_atr_multiplier: 1.5-2.0
   - take_profit_atr_multiplier: 4.0-6.0

NOTE: Always start with CONSERVATIVE settings!
"""


# ======================
# TIMEFRAME RECOMMENDATIONS
# ======================

"""
TRADING TIMEFRAME OPTIONS:

1. 5m (Default)
   - Fast-paced trading
   - More signals
   - Requires more attention
   - Best for: Active traders, automated systems

2. 15m
   - Balanced approach
   - Moderate signal frequency
   - Less noise than 5m
   - Best for: Semi-active traders

3. 1h
   - Slower trading
   - Higher quality signals
   - Less frequent trades
   - Best for: Swing traders, part-time traders

4. 4h
   - Very slow trading
   - Best signal quality
   - Infrequent trades
   - Best for: Position traders

EXTRA CANDLES:
Always include at least 3-4 higher timeframes than your trading timeframe.

Example for 5m trading:
- 15m, 1h, 4h, 1D (minimum)
- 15m, 30m, 1h, 4h, 12h, 1D (recommended)
- 10m, 15m, 30m, 1h, 2h, 4h, 8h, 12h, 1D, 1W (optimal)
"""


# ======================
# PERFORMANCE TIPS
# ======================

"""
1. DATA IMPORT:
   - Import more data than you need for backtesting
   - Minimum: 1 year of data
   - Recommended: 2-3 years

2. OPTIMIZATION:
   - Start with small date ranges (1-2 months)
   - Gradually increase after finding good parameters
   - Use walk-forward analysis for validation

3. BACKTESTING:
   - Always include realistic fees (0.04% for Binance Futures)
   - Add slippage for low-liquidity pairs
   - Test in different market conditions (bull, bear, sideways)

4. LIVE TRADING:
   - Always paper trade first (minimum 1 week)
   - Start with small position sizes
   - Monitor closely for the first few days
   - Keep logs and analyze performance regularly
"""
