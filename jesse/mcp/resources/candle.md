# Candle Management Reference

This reference covers candle import and management operations in Jesse.

## Data Requirements

Historical candle data is required for backtesting strategies. Import data for every route's exchange and symbol before running backtests.

Jesse imports and stores **one-minute candles only**, for every source (crypto exchanges, Massive, Custom Data). In backtests, optimization, Monte Carlo, significance tests and research, every other timeframe is generated from those minutes at run time, so a single import per exchange and symbol covers every timeframe a route or `get_candles()` asks for. Live and paper sessions are different: by default each timeframe's candles come from the exchange, and only when the live setting `generate_candles_from_1m` is enabled are bigger timeframes generated locally from one-minute candles. Timeframes are never imported, so when checking coverage only confirm that the symbol's data spans the backtest dates plus warm-up.

## Import Process

DO NOT pre-check candle availability before running a backtest. Run the
backtest first and only import on a missing-data error. Pre-checking with
`get_existing_candles()` wastes time and tokens, and the backtest engine
itself is the authoritative source of whether the required data is present
for a given route, timeframe, and date range.

Correct flow:

1. Run the backtest (see `jesse://backtest_management`).
2. If — and only if — it fails with a missing-candle error, call
   `import_candles()` starting ~2 months before the user's `start_date`.
3. Poll `get_candle_import_status(import_id)` until `"finished"`, `"failed"`, or `"cancelled"`. After `"finished"`,
   retry the backtest.
4. Use `get_existing_candles()` only for explicit user-driven inspection
   (e.g. "what data do I have?"), never as a pre-flight gate.

## Tool Reference

### get_existing_candles()

Checks what candle data is currently available in the database.

**Returns:** List of available candle datasets with exchange, symbol, timeframe, and date ranges.

### search_symbols()

Finds importable symbols on one candle source. Use it when the user names an instrument
("Microsoft", "crude oil", "the S&P 500 index") instead of an exact Jesse symbol, or when an
import fails with a symbol-not-found error.

**Parameters:**
- `exchange`: Candle source name exactly as Jesse lists it (e.g., "Massive Stocks")
- `query`: Ticker prefix or part of the instrument name (e.g., "MSFT", "microsoft")
- `limit` (optional): Maximum matches, default 20, maximum 200

**Ranking:** ticker prefixes first, then symbols whose provider name contains the query.

**Returns:** `matches`, each with `symbol` plus any provider details:

```python
search_symbols(exchange="Massive Stocks", query="microsoft")
# {"status": "success", "match_count": 3, "catalog_size": 13152, "matches": [
#   {"symbol": "MSFT-USD", "name": "Microsoft Corp", "kind": "Common Stock", "venue": "NASDAQ"},
#   {"symbol": "MSFX-USD", "name": "T-Rex 2X Long Microsoft Daily Target ETF", "kind": "ETF", "venue": "Cboe BZX"},
#   ...
# ]}
```

Source-specific behavior:
- Crypto exchanges (e.g., "Binance Perpetual Futures") match tickers only and return bare
  `{"symbol": ...}` entries. Searching "bitcoin" there returns nothing; search "BTC".
- "Massive Stocks" (stocks and ETFs), "Massive Currencies" (forex and crypto pairs),
  "Massive Indices", and "Massive Futures" also match names, and entries carry `name`,
  `kind`, `venue`, and for futures `expiry`.
- Every source has its own catalogue. Microsoft the company is `MSFT-USD` on Massive Stocks;
  Massive Futures instead lists CME stock futures on Microsoft such as `SMSFTU6-USD`
  ("Microsoft Corp Stock Futures", expires 2026-09-18). Choose the source that matches the
  user's intent and pass the returned `symbol` to `import_candles()` verbatim.
- Massive sources require a stored Massive API key; see `jesse://credentials`.

### copy_candles()

Duplicates stored candles under another exchange name (and optionally another symbol) so a
backtest can select the same data as a different market, for example to run Massive Stocks
`SPY-USD` under `Binance Perpetual Futures` as `SPY-USDT` and use that exchange's futures
simulation settings.

**Parameters:**
- `exchange`, `symbol`: the stored source series
- `target_exchange`: a backtesting-capable exchange name exactly as Jesse lists it
- `target_symbol` (optional): defaults to `symbol`; change it when the target quotes in another
  currency (`USD` vs `USDT`)
- `delete_source` (optional, default false): remove the original in the same transaction

Rules: the whole stored one-minute series is copied, which is everything a backtest needs for any timeframe; the call is refused (HTTP 409) when the target already
holds candles, so series are never merged; deleting the source turns the copy into a rename, but
provider updates only work under the original exchange name, so confirm with the user first.

**Returns:** `copied_count`, `deleted_count`, and the resolved target.

### import_candles()

Imports historical candle data from exchanges.

**Parameters:**
- `exchange`: Exchange name (e.g., "Binance Perpetual Futures")
- `symbol`: Trading pair (e.g., "BTC-USDT")
- `start_date`: Start date in YYYY-MM-DD format
- `import_id` (optional): Import ID for retrying failed imports

**Timeframes:** the import has no timeframe parameter. One-minute candles are stored, and in
backtests and the other research modes the timeframes usable in routes and `get_candles()` (1m,
3m, 5m, 15m, 30m, 45m, 1h, 2h, 3h, 4h, 6h, 8h, 12h, 1D, 3D, 1W, 1M) are all built from them at run
time. Live sessions fetch each timeframe from the exchange unless `generate_candles_from_1m` is on.

**Returns:** Import result with status and import ID

## Traditional Markets and Gapped Data

Massive sources and Custom Data describe markets that close, so their one-minute series has real
gaps (nights, weekends, holidays; pre-market and after-hours bars are kept where the provider has
them). Jesse never fabricates candles for a closure:

- Backtests detect gapped data automatically and replay only the candles that exist. Bigger
  timeframes are built from the observed minutes in clock-aligned buckets.
- Warm-up is counted in **completed observed candles** of the route's timeframe, not calendar
  time, so import noticeably more history than a crypto backtest would need.
- A resting order crossed by an opening gap fills at the **open price**, not at its own price.
- Metrics for these sources annualize on 252 observations by default instead of 365.
- To trade a stock-linked instrument on a 24/7 exchange with matching indicator history, use the
  trading-hours helpers described in `jesse://strategy`.

## Usage Examples

### Basic Import
```python
result = import_candles(
    exchange="Binance Spot",
    symbol="BTC-USDT",
    start_date="2024-01-01"
)
```

### Retry Failed Import
```python
# First attempt
result = import_candles(
    exchange="Binance Spot",
    symbol="ETH-USDT",
    start_date="2024-01-01"
)

# If failed, retry with same import_id
if result.get("status") != "success":
    import_id = result.get("import_id")
    retry_result = import_candles(
        exchange="Binance Spot",
        symbol="ETH-USDT",
        start_date="2024-01-01",
        import_id=import_id
    )
```

## Retry Behavior

When retrying imports with the same `import_id`:

- Previous events are automatically cleared
- Import resumes from the failure point
- Already-imported candles are skipped
- Progress monitoring starts fresh but continues efficiently
- WebSocket events are isolated per retry

## Success Response Format

```
"Successfully imported candles since '2024-01-01' until today (2.1 days imported, 1.2 days already existed in the database)."
```

The message shows both newly imported data and pre-existing data that was skipped.
