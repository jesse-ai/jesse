<div align="center">
<br>
<p align="center">
<img src="assets/jesse-logo.png" alt="Jesse" height="72" />
</p>

<p align="center">
Algo-trading was 😵‍💫, we made it 🤩
</p>
</div>

# Jesse
[![PyPI](https://img.shields.io/pypi/v/jesse)](https://pypi.org/project/jesse)
[![Downloads](https://pepy.tech/badge/jesse)](https://pepy.tech/project/jesse)
[![Docker Pulls](https://img.shields.io/docker/pulls/salehmir/jesse)](https://hub.docker.com/r/salehmir/jesse)
[![GitHub](https://img.shields.io/github/license/jesse-ai/jesse)](https://github.com/jesse-ai/jesse)
[![coverage](https://codecov.io/gh/jesse-ai/jesse/graph/badge.svg)](https://codecov.io/gh/jesse-ai/jesse)

---

Jesse is an advanced crypto trading framework that aims to **simplify** **researching** and defining **YOUR OWN trading strategies** for backtesting, optimizing, and live trading.

## What is Jesse?
Watch this video to get a quick overview of Jesse:

[![Jesse Overview](https://img.youtube.com/vi/0EqN3OOqeJM/0.jpg)](https://www.youtube.com/watch?v=0EqN3OOqeJM)

## Why Jesse?
In short, Jesse is more **accurate** than other solutions, and way more **simple**. 
In fact, it is so simple that in case you already know Python, you can get started today, in **matter of minutes**, instead of **weeks and months**. 

## Key Features

- 📝 **Simple Syntax**: Define both simple and advanced trading strategies with the simplest syntax in the fastest time.
- 📊 **Comprehensive Indicator Library**: Access a complete library of technical indicators with easy-to-use syntax.
- 📈 **Smart Ordering**: Supports market, limit, and stop orders, automatically choosing the best one for you.
- ⏰ **Multiple Timeframes and Symbols**: Backtest and livetrade multiple timeframes and symbols simultaneously without look-ahead bias.
- 🔒 **Self-Hosted and Privacy-First**: Designed with your privacy in mind, fully self-hosted to ensure your trading strategies and data remain secure.
- 🛡️ **Risk Management**: Built-in helper functions for robust risk management.
- 📋 **Metrics System**: A comprehensive metrics system to evaluate your trading strategy's performance.
- 🔍 **Debug Mode**: Observe your strategy in action with a detailed debug mode.
- 🔧 **Optimize Mode**: Search strategy parameters efficiently with Optuna and parallel processing powered by Ray.
- 📈 **Leveraged and Short-Selling**: First-class support for leveraged trading and short-selling.
- 🔀 **Partial Fills**: Supports entering and exiting positions in multiple orders, allowing for greater flexibility.
- 🔔 **Advanced Alerts**: Create real-time alerts within your strategies for effective monitoring.
- 🔌 **Jesse MCP**: Connect Claude, Codex, Cursor, VS Code, Zed, and other MCP-compatible AI assistants directly to your local Jesse project.
- 🔧 **Built-in Code Editor**: Write, edit, and debug your strategies with a built-in code editor.
- 📊 **Interactive Trading Charts**: Inspect candles, strategy indicators, horizontal levels, orders, and completed trades across backtest, paper, and live sessions.
- 🔬 **Rule Significance Testing**: Test whether an entry rule shows genuine historical edge or could have appeared by chance.
- 🎲 **Monte Carlo Analysis**: Stress-test your strategies with trade-order shuffling and candles-based simulations to distinguish skill from luck and guard against overfitting.
- 🧠 **Machine Learning**: A built-in ML pipeline — gather labelled training data from backtests, train scikit-learn models (binary, multiclass, or regression), and deploy predictions directly inside your strategies.
- 🧪 **Research API and Jupyter**: Run backtests, optimization, significance tests, Monte Carlo analysis, candle workflows, and machine learning from Python scripts or notebooks.
- 🦀 **Rust-Powered Indicators**: Native Rust implementations make indicator-heavy strategies and large research runs substantially faster.
- 🤖 **Reinforcement Learning — Coming Soon**: First-class reinforcement-learning workflows built on Jesse's simulation and research stack are on the way.
- 📺 **Youtube Channel**: Jesse has a Youtube channel with screencast tutorials that go through example strategies step by step.

## Dive Deeper into Jesse's Capabilities

### Stupid Simple
Craft complex trading strategies with remarkably simple Python. Access 300+ indicators, multi-symbol/timeframe support, spot/futures trading, partial fills, and risk management tools. Focus on logic, not boilerplate.

```python
class GoldenCross(Strategy):
    def should_long(self):
        # go long when the EMA 8 is above the EMA 21
        short_ema = ta.ema(self.candles, 8)
        long_ema = ta.ema(self.candles, 21)
        return short_ema > long_ema

    def go_long(self):
        entry_price = self.price - 10        # limit buy order at $10 below the current price
        qty = utils.size_to_qty(self.balance*0.05, entry_price) # spend only 5% of my total capital
        self.buy = qty, entry_price                 # submit entry order
        self.take_profit = qty, entry_price*1.2  # take profit at 20% above the entry price
        self.stop_loss = qty, entry_price*0.9   # stop loss at 10% below the entry price
```

### Backtest
Execute highly accurate and fast backtests without look-ahead bias. Utilize debugging logs, interactive charts with indicator support, and detailed performance metrics to validate your strategies thoroughly.

![Backtest](https://raw.githubusercontent.com/jesse-ai/storage/refs/heads/master/backtest.gif)

### Interactive Trading Charts
Inspect your strategy where its decisions happened. Jesse combines candlesticks, strategy-added indicators and levels, executed orders, and completed trades in synchronized interactive charts. The same charting workflow is available for backtests and for running or completed paper/live sessions.

![Jesse Trade Chart with completed trades and indicator panes](https://cdn.jesse.trade/images/148b8772-9356-45f6-941e-bdda119c8e7b.png)

Expand a trade to inspect every execution, collapse or isolate indicator panes, follow OHLC and indicator values under the cursor, reset the view, use fullscreen mode, or export the chart as an image.

![Jesse Trade Chart showing individual executions](https://cdn.jesse.trade/images/43a766d9-a9e7-47cb-b8ed-7112bdda3a13.png)

[Explore Jesse's interactive charts →](https://docs.jesse.trade/docs/charts/interactive-charts)

### Live/Paper Trading
Deploy strategies live with robust monitoring tools. Supports paper trading, multiple accounts, real-time logs & notifications (Telegram, Slack, Discord), interactive charts, spot/futures, DEX, and a built-in code editor.

![Live/Paper Trading](https://raw.githubusercontent.com/jesse-ai/storage/refs/heads/master/live.gif)

### Benchmark
Accelerate research using the benchmark feature. Run batch backtests, compare across timeframes, symbols, and strategies. Filter and sort results by key performance metrics for efficient analysis.

![Benchmark](https://raw.githubusercontent.com/jesse-ai/storage/refs/heads/master/benchmark.gif)

### Jesse MCP: Your AI Assistant, Connected to Jesse
Jesse includes a local [Model Context Protocol (MCP)](https://docs.jesse.trade/docs/mcp/) server. Connect your preferred AI assistant and let it work with Jesse's real tools and project context instead of merely guessing how your trading framework behaves.

Through Jesse MCP, an assistant can help you write and improve strategies, manage candle data, run and inspect backtests, perform rule significance tests, optimize parameters, run Monte Carlo simulations, and link you directly to the saved results in the Jesse dashboard. Your strategies and data remain under your control in your self-hosted Jesse setup.

For example, you can ask:

> Check whether my new entry rule is statistically significant, backtest it, optimize the promising parameters, and run a candles-based Monte Carlo analysis before we consider paper trading.

[Connect Claude, Codex, Cursor, VS Code, or Zed to Jesse →](https://docs.jesse.trade/docs/mcp/setup)

### Rule Significance Testing
Before spending hours building and tuning a complete strategy, test whether its entry rule has a measurable historical edge. Jesse compares the rule against a bootstrap distribution of random entries on the same market history, helping you reject noisy ideas early and focus your research on signals worth developing.

[Learn about Rule Significance Testing →](https://docs.jesse.trade/docs/rule-significance-testing/)

### Monte Carlo Analysis
Stress-test your strategies beyond a single historical path. Jesse's Monte Carlo mode runs hundreds of simulations using **trade-order shuffling** (tests whether trade timing drove your results) and **candles-based** (tests robustness under slightly different market conditions) methods. Use it to distinguish skill from luck, understand the range of outcomes you can realistically expect, and catch overfitting early.

### Machine Learning
Jesse includes a complete, end-to-end ML pipeline built for trading strategies:

1. **Gather data** — run a backtest in gather mode; call `record_features({...})` at each signal bar and `record_label(name, value)` when the outcome is known. Data is auto-saved to CSV.
2. **Train a model** — call `train_model()` with any scikit-learn–compatible estimator and choose a task type: `"binary"` classification, `"multiclass"` classification, or `"regression"`. Get a full report with feature importance, calibration, and metrics.
3. **Deploy** — switch to deploy mode and call `ml_predict()` or `ml_predict_proba()` inside your strategy. Model loading, scaling, and feature ordering are handled automatically.

```python
# Gather phase — inside your strategy
def before(self):
    self.record_features({
        'rsi': ta.rsi(self.candles),
        'adx': ta.adx(self.candles),
    })

# Deploy phase — gate entries with model confidence
def should_long(self):
    proba = self.ml_predict_proba()
    return proba['long'] > 0.65
```

[Explore Jesse's machine-learning pipeline →](https://docs.jesse.trade/docs/research/ml/)

### Research API and Jupyter Notebooks
Everything does not have to happen through the dashboard. Jesse's Research API exposes candle management, backtesting, optimization, Rule Significance Testing, Monte Carlo analysis, indicators, and machine learning to ordinary Python scripts and Jupyter notebooks. Use it for reproducible experiments, custom reports, batch research, or integration with your existing data-science workflow.

```python
from jesse import research
```

[Explore the Research API →](https://docs.jesse.trade/docs/research/)

### Rust-Powered Performance
Jesse's indicator engine is powered by native Rust implementations. In Jesse's benchmark suite, porting the remaining accelerated indicators to Rust reduced their combined runtime from 423.5 µs to 124.4 µs — a 3.4× speedup. Together with major backtesting improvements, this makes repeated strategy iteration, optimization, and Monte Carlo analysis dramatically faster.

### Reinforcement Learning — Coming Soon
We are working on first-class reinforcement-learning support built on Jesse's simulation and research stack. The goal is to make training, evaluating, and deploying reinforcement-learning agents feel as integrated as Jesse's existing backtesting, optimization, Monte Carlo, and machine-learning workflows.

### Optimize Your Strategies
Unsure about optimal parameters? Let the optimization mode decide using simple syntax. Fine-tune any strategy parameter with the Optuna library and easy cross-validation.

```python
@property
def slow_sma(self):
    return ta.sma(self.candles, self.hp['slow_sma_period'])

@property
def fast_sma(self):
    return ta.sma(self.candles, self.hp['fast_sma_period'])

def hyperparameters(self):
    return [
        {'name': 'slow_sma_period', 'type': int, 'min': 150, 'max': 210, 'default': 200},
        {'name': 'fast_sma_period', 'type': int, 'min': 20, 'max': 100, 'default': 50},
    ]
```

## Getting Started
Head over to the "getting started" section of the [documentation](https://docs.jesse.trade/docs/getting-started). The 
documentation is **short yet very informative**. 

## Resources

- [⚡️ Website](https://jesse.trade)
- [🎓 Documentation](https://docs.jesse.trade)
- [🎥 Youtube channel (screencast tutorials)](https://jesse.trade/youtube)
- [🛟 Help center](https://jesse.trade/help)
- [💬 Discord community](https://jesse.trade/discord)
- [🔌 Jesse MCP](https://docs.jesse.trade/docs/mcp/)

## What's next?

You can see the project's **[roadmap here](https://docs.jesse.trade/docs/roadmap.html)**. **Subscribe** to our mailing list at [jesse.trade](https://jesse.trade) to get the good stuff as soon they're released. Don't worry, We won't send you spam—Pinky promise.

## Disclaimer
This software is for educational purposes only. USE THE SOFTWARE AT **YOUR OWN RISK**. THE AUTHORS AND ALL AFFILIATES ASSUME **NO RESPONSIBILITY FOR YOUR TRADING RESULTS**. **Do not risk money that you are afraid to lose**. There might be **bugs** in the code - this software DOES NOT come with **ANY warranty**.
