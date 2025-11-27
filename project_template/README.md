# Jesse Backtesting Project

This is a Jesse project template for crypto trading backtesting. Use this with Google Antigravity (or any IDE) to write and test trading strategies.

## What is Jesse?

Jesse is an advanced crypto trading framework for:
- **Backtesting** trading strategies on historical data
- **Optimizing** strategy parameters with AI (Optuna)
- **Live/paper trading** on exchanges (Binance, Bybit, etc.)

## Requirements

Jesse needs PostgreSQL and Redis. **Don't worry - you can use FREE cloud services!** No Docker or local installation needed.

---

## Quick Setup (Cloud - Recommended for Low-Spec Machines)

### Step 1: Set up PostgreSQL (Free - Neon)

1. Go to **https://neon.tech** and sign up (GitHub login works)
2. Click **"New Project"**
3. Name it `jesse` and click **Create Project**
4. Copy these values from the dashboard:
   - Host (looks like `ep-cool-name-123456.us-east-2.aws.neon.tech`)
   - Database name (usually `neondb`)
   - Username
   - Password

### Step 2: Set up Redis (Free - Upstash)

1. Go to **https://upstash.com** and sign up
2. Click **"Create Database"**
3. Select **Redis**, name it `jesse`, pick nearest region
4. Copy these values from the dashboard:
   - Endpoint (looks like `helpful-emu-12345.upstash.io`)
   - Port (`6379`)
   - Password

### Step 3: Configure Your Project

```bash
# Copy the template
cp .env.example .env
```

Edit `.env` with your cloud credentials:

```bash
# Application
PASSWORD=pick_any_password_here
APP_PORT=9000
APP_HOST=0.0.0.0
LSP_PORT=9001
IS_DEV_ENV=FALSE

# PostgreSQL (from Neon)
POSTGRES_HOST=ep-cool-name-123456.us-east-2.aws.neon.tech
POSTGRES_PORT=5432
POSTGRES_NAME=neondb
POSTGRES_USERNAME=your-neon-username
POSTGRES_PASSWORD=your-neon-password
POSTGRES_SSLMODE=require

# Redis (from Upstash)
REDIS_HOST=helpful-emu-12345.upstash.io
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=your-upstash-password
```

### Step 4: Install & Run Jesse

```bash
# Install Jesse
pip install jesse

# Run from this project folder
cd project_template
jesse run
```

### Step 5: Open Dashboard

Go to **http://localhost:9000** in your browser

---

## Alternative: Local Setup (If you have a powerful machine)

<details>
<summary>Click to expand local setup instructions</summary>

### PostgreSQL (Local)
```bash
# Ubuntu/Debian
sudo apt install postgresql
sudo -u postgres createdb jesse_db
sudo -u postgres createuser jesse_user

# Or Docker
docker run -d --name jesse-postgres \
  -e POSTGRES_DB=jesse_db \
  -e POSTGRES_USER=jesse_user \
  -e POSTGRES_PASSWORD=password \
  -p 5432:5432 postgres:15
```

### Redis (Local)
```bash
# Ubuntu/Debian
sudo apt install redis-server
sudo systemctl start redis

# Or Docker
docker run -d --name jesse-redis -p 6379:6379 redis:7
```

</details>

---

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

---

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

---

## Using with Google Antigravity

1. Open this project folder in Antigravity
2. Use the AI agent to help write strategies
3. Example prompts:
   - "Create a RSI oversold/overbought strategy"
   - "Add MACD indicator to the GoldenCross strategy"
   - "Optimize the stop loss percentage"
   - "Create a strategy that uses Bollinger Bands breakout"

---

## Available Indicators (300+)

Jesse includes technical indicators via `jesse.indicators`:

| Indicator | Function |
|-----------|----------|
| EMA | `ta.ema(candles, period)` |
| SMA | `ta.sma(candles, period)` |
| RSI | `ta.rsi(candles, period)` |
| MACD | `ta.macd(candles)` |
| Bollinger Bands | `ta.bollinger_bands(candles)` |
| ATR | `ta.atr(candles, period)` |
| Stochastic | `ta.stoch(candles)` |
| ADX | `ta.adx(candles)` |

And 290+ more...

---

## Supported Exchanges

- Binance (Futures/Spot)
- Bybit (USDT Perpetual)
- Coinbase
- Gate.io
- Bitget
- Hyperliquid
- dYdX

---

## Free Cloud Services Summary

| Service | Free Tier | Sign Up |
|---------|-----------|---------|
| **Neon** (PostgreSQL) | 512MB storage | https://neon.tech |
| **Supabase** (PostgreSQL) | 500MB storage | https://supabase.com |
| **Upstash** (Redis) | 10K commands/day | https://upstash.com |
| **Redis Cloud** | 30MB storage | https://redis.com/try-free |

---

## Resources

- [Jesse Documentation](https://docs.jesse.trade)
- [YouTube Tutorials](https://jesse.trade/youtube)
- [Discord Community](https://jesse.trade/discord)

---

## Troubleshooting

**"Connection refused" error?**
- Check your cloud service credentials in `.env`
- Make sure `POSTGRES_SSLMODE=require` for cloud databases

**"Redis connection error"?**
- Verify your Upstash password is correct
- Check the host doesn't include `redis://` prefix

**Dashboard not loading?**
- Make sure port 9000 isn't blocked
- Try `APP_HOST=127.0.0.1` instead of `0.0.0.0`
