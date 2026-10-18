# Strategy Catalog Reference (jesse.trade)

The strategy catalog is the list of community strategies published on jesse.trade, the same
list the dashboard's Strategies page shows. Catalog strategies are online; they are not the
strategies installed in this Jesse project until one is imported. Local strategies are handled
with `create_strategy`, `read_strategy`, and `write_strategy`; catalog strategies with the three
tools below.

Only approved strategies with completed backtest metrics for the chosen period are listed.

## Workflow

1. `browse_strategy_catalog()` to rank candidates. Narrow with `sort_by`, `period`, submission
   dates, `query`, and `strategy_type`; follow `pagination.next_offset` for more.
2. Optionally check robustness with `get_catalog_strategy_metrics()` on other
   `backtest_symbols`, `backtest_timeframes`, or periods.
3. Present the shortlist (name, author, type, key metrics, `slug`) and let the user choose,
   unless they already asked you to import a specific one.
4. `import_catalog_strategy(slug)`, then continue with the returned `local_name`:
   `read_strategy(local_name)`, backtests, and reports all use that name, not the display name.

## Access

- Browsing works without a jesse.trade account. Importing needs the project's
  `LICENSE_API_TOKEN` (free and premium strategies alike), and premium strategies also need an
  active Premium plan. Jesse signs in with the token itself; no tool returns it.
- `code_available` on a browse result is jesse.trade's answer for the signed-in account: only
  import strategies where it is `true`.
- If `jesse_trade_signed_in` is `false`, tell the user what `jesse_trade_auth.message` says
  (missing or rejected `LICENSE_API_TOKEN`); do not guess another way to import.

## Tools

### browse_strategy_catalog(period=None, sort_by="Sharpe Ratio", submitted_after=None, submitted_before=None, query=None, strategy_type=None, offset=0, limit=10)

Sent to jesse.trade, exactly as the dashboard sends them:
- `period`: one of `available_filters.periods` (e.g. "Q1 of 2026", "2024 - 2025"). Omitted means
  `available_filters.default_period`, the dashboard's default.
- `sort_by`: "Sharpe Ratio", "PNL", "Sortino Ratio", "Calmar Ratio", or "Win Rate"; best first.
- `submitted_after` / `submitted_before`: `YYYY-MM-DD`. Compared with the submission time at
  00:00 UTC of that date, so `submitted_before` excludes submissions made on that day.

Applied by the tool to the ranked list (jesse.trade has no search, type filter, or paging):
- `query`: case-insensitive match on name, description, author, and slug.
- `strategy_type`: "free" or "premium".
- `offset` / `limit` (1-25): pagination over the matches, keeping the ranking.

Returns `strategies` (each with `slug`, `name`, `type`, `author`, `description`,
`code_available`, `submitted_at`, `views`, `default_symbol`, `default_timeframe`,
`backtest_symbols`, `backtest_timeframes`, and `metrics` for the default symbol/timeframe in
the period), plus `filters`, `available_filters`, `pagination`, `jesse_trade_signed_in`,
`jesse_trade_auth`, and a `message` that explains empty results. Strategy code and equity
curves are not included.

### get_catalog_strategy_metrics(slug, period, symbol, timeframe)

jesse.trade's full metric set (without equity curve) for one symbol (e.g. "ETH-USDT"),
timeframe, and period. `error_type: "not_found"` means the slug is unknown or that combination
was never backtested.

### import_catalog_strategy(slug)

Same as the dashboard's "Import Strategy" button. Jesse saves the code on the machine running
Jesse at `strategies/<local_name>/__init__.py`, where `local_name` is the class name in the
code. Returns `local_name`, `path`, and `dashboard_url`. It never overwrites a local strategy.

| error_type | Meaning and next step |
|------------|-----------------------|
| `strategy_exists` | A local strategy called `local_name` exists; nothing changed. Ask the user whether to use it or rename/delete it in the dashboard first. |
| `strategy_access_denied` | Premium strategy without an active Premium plan. |
| `license_token_missing` / `license_token_rejected` | No valid `LICENSE_API_TOKEN`; relay the setup steps in `message`. |
| `catalog_strategy_not_found` | Unknown slug; browse again. |
| `invalid_request` | Malformed slug, or the catalog code has no Python class. |
| `authentication_failed`, `connection_error`, `jesse_trade_unavailable`, `jesse_trade_error` | Jesse or jesse.trade problem; stop and tell the user. |

Never report an error as "no strategies found", and never retry an auth, access, or exists
error unchanged.
