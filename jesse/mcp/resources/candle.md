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

Lists stored candles like the dashboard's Manage Candles table: one entry per exchange and
symbol with `start_date` and `end_date` (first and last stored UTC day), `backtesting_supported`,
and `updatable` (the exchange is an import source, so `import_candles` can extend it). The dates
are bounds, not a promise of gap-free coverage.

**Parameters (all optional):**
- `exchange`, `symbol`: case-insensitive substrings, like the dashboard's search boxes
- `availability`: `all` (default), `backtesting`, or `live` (live-only exchanges)
- `offset`, `limit` (1-1000, default 200): page with `next_offset`; `total_count` is the number of
  matches

### delete_candles() and purge_candles()

- `delete_candles(exchange, symbol)` permanently removes every stored row of that pair, all
  timeframes and dates, like the dashboard's Delete. `deleted_count` 0 means nothing was stored
  under that exact name.
- `purge_candles(exchanges)` permanently removes every symbol of the listed exchanges, like the
  dashboard's "Purge Candles by Exchange".

Neither can be undone. Only delete what the user asked to remove, using the names exactly as
`get_existing_candles()` shows them.

### export_candles()

Writes one stored series into the project as CSV, the same file the dashboard's Export button
downloads: the whole one-minute series of the pair, oldest first, columns
`timestamp,open,close,high,low,volume` (timestamp in Unix milliseconds). The file stays on the
Jesse host in `research_scripts/` (default
`research_scripts/candle_exports/<exchange>_<symbol>_1m.csv`); the tool returns only a summary
(`path`, `row_count`, `size_bytes`, first and last candle). An existing file is replaced only with
`overwrite=True`.

Use the file with the project file tools (`read_project_file(path, start_line, max_lines)` reads
it in pages), from a research script the user asked for, or re-import it as Custom Data. It is
not sent to the assistant's or user's computer; for a download, point the user to Export on the
dashboard's Manage Candles page (`dashboard_download_page`).

### get_candles()

Returns the candles the dashboard's live chart starts from: the live `warm_up_candles` setting's
number of candles of one timeframe ending now, at most `limit` (default 300, maximum 1000),
with `time` in Unix seconds. It is not a historical reader and is empty for data that ends in
the past; use `get_existing_candles()` for coverage and `export_candles()` for stored values.

### Custom CSV import (`preview_custom_candle_csv`, `clean_and_import_custom_candle_csv`)

Imports a one-minute CSV as `Custom Data / SYMBOL`. Pass exactly one source:
- `project_path`: a `.csv` inside the Jesse project (`research_scripts/` or `strategies/`). This is
  the way to import when you are not running on the Jesse host: write the CSV there with
  `write_project_file` (up to 2 MiB per file) or use one `export_candles` produced.
- `file_path`: an absolute path on the Jesse host. It only works when you run on that machine;
  a path on the user's computer does not exist there.

Preview first, then import with `invalid_row_policy="reject"` or `"drop"`. Identical duplicate
rows are dropped, conflicting rows for one timestamp fail the import, and gaps stay gaps. If the
symbol already has Custom Data, new timestamps are added and stored ones keep their values.
Larger files can be uploaded by the user through the dashboard's Custom Data importer.

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
- `delete_source` (optional, default false): remove the original once every chunk is copied
  (a separate statement: the copy and the deletion are not one transaction)

Rules: every stored row of the pair is copied, which is everything a backtest needs for any timeframe; the call is refused (HTTP 409) when the target already
holds candles, so series are never merged; deleting the source turns the copy into a rename, but
provider updates only work under the original exchange name, so confirm with the user first. A
large copy commits in chunks; if it is interrupted, delete the partial target before retrying.

**Returns:** `copied_count`, `deleted_count`, and the resolved target.

### import_candles()

Starts a background import from a historical source and returns once Jesse accepts it.

**Parameters:**
- `exchange`: a historical source exactly as Jesse lists it: crypto exchanges (e.g., "Binance
  Perpetual Futures", "Bybit USDT Perpetual") or the Massive sources (need a saved Massive key)
- `symbol`: Trading pair (e.g., "BTC-USDT")
- `start_date`: YYYY-MM-DD, before today (UTC)
- `import_id` (optional): defaults to a new UUID

An unsupported source, date, or symbol is refused at once with Jesse's message. Follow a started
import with `get_candle_import_status(import_id)` until `finished`, `failed`, or `cancelled`; an
ID Jesse has no record of also reports `finished`. The dashboard runs one import per exchange at a
time, so wait for one to finish before starting another on the same exchange.
`cancel_candle_import(import_id)` stops a running import; candles stored so far remain.

**Updating stored data:** call `import_candles` again with the pair's `start_date` from
`get_existing_candles()` (the dashboard's Update button). It downloads only what lies before the
first and after the last stored candle; Custom Data cannot be updated this way.

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
# then: get_candle_import_status(result["import_id"]) until it is finished
```

### Export and re-import as Custom Data
```python
exported = export_candles(exchange="Massive Stocks", symbol="SPY-USD")
preview_custom_candle_csv(symbol="SPY-USD", project_path=exported["path"])
clean_and_import_custom_candle_csv(symbol="SPY-USD", project_path=exported["path"],
                                   invalid_row_policy="reject")
```

## Retry Behavior

Re-running `import_candles` for a pair, with the same or a new `import_id`, never downloads what is
already stored: Jesse fetches only the range before the first stored candle and after the last
one, so retrying a failed or cancelled import continues from the stored data. Nothing resumes an
old import process, and gaps inside the stored range are kept as they are.

## Success Response Format

```
"Successfully imported candles since '2024-01-01' until today (2.1 days imported, 1.2 days already existed in the database)."
```

The message shows both newly imported data and pre-existing data that was skipped.
