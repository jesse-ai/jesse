# Jesse Backtesting Project

This is a Jesse project template for crypto trading backtesting. Use this with Google Antigravity (or any IDE) to write and test trading strategies.

## What is Jesse?

Jesse is an advanced crypto trading framework for:
- **Backtesting** trading strategies on historical data
- **Optimizing** strategy parameters with AI (Optuna)
- **Live/paper trading** on exchanges (Binance, Bybit, etc.)

## Requirements

Jesse requires these services running:

### 1. PostgreSQL (Database)
```bash
# Ubuntu/Debian
sudo apt install postgresql
sudo -u postgres createdb jesse_db
sudo -u postgres createuser jesse_user

# Or use Docker
docker run -d --name jesse-postgres \
  -e POSTGRES_DB=jesse_db \
  -e POSTGRES_USER=jesse_user \
  -e POSTGRES_PASSWORD=password \
  -p 5432:5432 postgres:15
```

### 2. Redis (Real-time messaging)
```bash
# Ubuntu/Debian
sudo apt install redis-server
sudo systemctl start redis

# Or use Docker
docker run -d --name jesse-redis -p 6379:6379 redis:7
```

## Quick Start

### 1. Install Jesse
```bash
pip install jesse
# Or from source:
pip install -e /path/to/jesse
```

### 2. Set up your project
```bash
cp .env.example .env
# Edit .env with your database credentials
```

### 3. Start Jesse
```bash
jesse run
```

### 4. Access the dashboard
Open http://localhost:9000 in your browser

## Project Structure

```
project_template/
├── .env.example           # Template configuration
├── .env                   # Your configuration (create from template)
├── strategies/            # Your trading strategies
│   └── GoldenCross/      # Example strategy
│       └── __init__.py
└── storage/              # Logs, cache, temp files
    ├── logs/
    └── temp/
```

## Writing Strategies

Strategies go in the `strategies/` folder. Each strategy is a Python class:

```python
from jesse.strategies import Strategy
import jesse.indicators as ta
from jesse import utils

class MyStrategy(Strategy):
    def should_long(self) -> bool:
        # Return True when you want to enter a long position
        return self.fast_ema > self.slow_ema

    def should_short(self) -> bool:
        # Return True when you want to enter a short position
        return self.fast_ema < self.slow_ema

    def go_long(self):
        qty = utils.size_to_qty(self.balance * 0.05, self.price)
        self.buy = qty, self.price
        self.stop_loss = qty, self.price * 0.95
        self.take_profit = qty, self.price * 1.10

    def go_short(self):
        qty = utils.size_to_qty(self.balance * 0.05, self.price)
        self.sell = qty, self.price
        self.stop_loss = qty, self.price * 1.05
        self.take_profit = qty, self.price * 0.90

    @property
    def fast_ema(self):
        return ta.ema(self.candles, 8)

    @property
    def slow_ema(self):
        return ta.ema(self.candles, 21)
```

## Using with Google Antigravity

1. Open this project folder in Antigravity
2. Use the AI agent to help write strategies
3. Example prompts:
   - "Create a RSI oversold/overbought strategy"
   - "Add MACD indicator to the GoldenCross strategy"
   - "Optimize the stop loss percentage"

## Available Indicators (300+)

Jesse includes technical indicators via `jesse.indicators`:
- `ta.ema()` - Exponential Moving Average
- `ta.sma()` - Simple Moving Average
- `ta.rsi()` - Relative Strength Index
- `ta.macd()` - MACD
- `ta.bollinger_bands()` - Bollinger Bands
- And many more...

## Supported Exchanges

- Binance (Futures/Spot)
- Bybit (USDT Perpetual)
- Coinbase
- Gate.io
- Bitget
- Hyperliquid
- dYdX

## Resources

- [Jesse Documentation](https://docs.jesse.trade)
- [YouTube Tutorials](https://jesse.trade/youtube)
- [Discord Community](https://jesse.trade/discord)
