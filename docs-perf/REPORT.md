# Backtest performance overhaul — review guide

**Branches:** `perf-backtests` in `jesse` (15 performance commits on top of `e499b3ea`,
which is the already-merged dashboard rebuild, PR #587) and `perf-backtests` in
`jesse-rust` (5 commits on top of `main`).
**Benchmarked on:** Raspberry Pi 5 (aarch64, Cortex-A76), Python 3.12.13, numpy 1.26.4.
Bench harness, scenarios and all result JSONs live in `/home/saleh/dev-jesse/jesse-bench/`
(see its `ANALYSIS.md` for the full night-by-night writeup).

---

## 1. Executive summary

The full benchmark suite went from **79.0 s to 27.5 s — 2.88x faster overall**, with
**zero change in backtest output**: all 8 scenario fingerprints (metrics + sha256 over
every closed trade) are bit-identical to baseline.

4 deterministic synthetic scenarios x 2 modes. `fast` = skip simulator
(`fast_mode=True`, the default for dashboard + MCP users); `step` = full per-minute
simulator. Median of 3 timed runs (+1 warmup), seconds:

| scenario:mode | baseline | round 1 | round 2 | round 3 | **speedup** | trades_hash |
|---|---:|---:|---:|---:|---:|---|
| a_simple_1h:fast | 0.73 | 0.56 | 0.38 | 0.30 | **2.46x** | `cc8ab0d73d50ae16` |
| a_simple_1h:step | 5.33 | 2.27 | 1.22 | 1.18 | **4.51x** | `cc8ab0d73d50ae16` |
| b_heavy_15m:fast | 11.22 | 9.90 | 5.81 | 5.32 | **2.11x** | `760596ae71bcce7b` |
| b_heavy_15m:step | 16.17 | 11.85 | 6.94 | 6.71 | **2.41x** | `760596ae71bcce7b` |
| c_multi_route:fast | 5.76 | 4.68 | 2.78 | 2.40 | **2.40x** | `121845d0f4572d93` |
| c_multi_route:step | 12.05 | 6.78 | 3.80 | 3.76 | **3.21x** | `121845d0f4572d93` |
| d_long_2y:fast | 4.54 | 3.79 | 2.63 | 2.05 | **2.22x** | `7d11a1f5f85cbc4d` |
| d_long_2y:step | 23.23 | 10.76 | 6.01 | 5.75 | **4.04x** | `7d11a1f5f85cbc4d` |
| **suite total** | **79.03** | **50.58** | **29.57** | **27.46** | **2.88x** | — |

Scenarios: a = simple SMA cross, 1 route @ 1h, ~6 mo of 1m candles, spot;
b = indicator-heavy (EMA/RSI/ATR/BB + TP/SL), 1 route @ 15m, ~6 mo, futures;
c = multi-route, 3 symbols (2x SMA @ 1h + 1x heavy @ 15m), ~3 mo, futures;
d = long run, simple SMA, 1 route @ 1h, ~2 years (1,051,200 1m candles), futures.

Source JSONs (in `jesse-bench/results/`): `baseline.json` (jesse `e499b3ea`),
`fdbd0166-round1.json`, `20c6b834-round2.json`, `15cb00d3-round3.json` — plus one
JSON per intermediate commit (each change was benched individually).

**Honest headline:** ~2.1–2.5x in fast mode and ~2.4–4.5x in step mode *on this suite*.
See §5 for why real-world sessions will shift these numbers (mostly in our favor for
engine wins, against us for kernel wins).

---

## 2. How correctness was guaranteed

Nothing here is "looks the same"; everything is **bit-for-bit**:

1. **Fingerprint gate.** The harness records, per (scenario, mode): key metrics
   (net profit, trade counts, fees, drawdown, …) **and `trades_hash`** — a sha256 over
   every closed trade's prices/qty/fees/timestamps (6-decimal rounding) — plus an input
   checksum. `bench.py --compare` hard-fails on any drift. **One measured change at a
   time**; any change that could not be proven bit-exact was rejected (see §6).
   Final check: `--compare results/baseline.json results/15cb00d3-round3.json` →
   **ALL 8 FINGERPRINTS MATCH**.
2. **Randomized bitwise sweeps** for every new/changed Rust kernel, compared with `==`
   (no tolerance) against the reference: e.g. `rsi_last` vs `rsi()[-1]` over 300 cases,
   `sma_last` vs `sma()[-1]` over 400 cases (NaN prefixes, random NaNs, strided column
   views), `candle_from_one_minutes` vs the numpy expression for **every** block length
   1..=4320 plus NaN/-0.0/strided cases, `fix_jumped_candles` vs the Python loop over
   randomized series. Zero mismatches.
3. **Full test suites at the final SHAs:** `pytest tests/ -q -p no:anyio` → **498 passed**;
   `tests/test_indicators.py` → **178 passed**.
4. **Reasoning constraints for the storage prefills** (the two riskiest commits): the
   jumped-candle fix reads only the previous candle's *close*, which no fix ever writes,
   so applying all fixes upfront in ascending order is order-identical to applying them
   per minute / per step; and storage rows after any step equal the input rows whether
   or not orders executed, because the execution path's restore (`add_candle` /
   `add_multiple_1m_candles` override) was left untouched. Both prefills are gated by
   strict guards (dtype / writeable / no zero timestamps / strictly increasing
   timestamps / warmup continuity) and **fall back to the original code path** when any
   guard fails.
5. **Real-strategy regression tests** (`tests/test_real_strategy_regression.py`): two
   pytest tests run full `jesse.research.backtest()` sessions with *real* strategies
   adapted from the maintainer's bot project and assert the complete result
   fingerprint (bench-style: key metrics @ 6 decimals + per-trade sha256) against
   values captured from **master @ `0987c304`** (pre-optimization):
   - `test_real_strategy_single_route`: ~1 year of 1m candles (525,600), BTC-USDT @ 1h,
     multi-timeframe Alligator + ADX/CMO/StochRSI system (`RealStrategyRegression1`,
     from AlligatorV2) with a 4h data route, **step** simulator. 69 trades
     (32L/37S), trades_hash `048ce3b5dc049429`.
   - `test_real_strategy_multi_route`: ~6 months × 3 routes (777,600 1m candles):
     Donchian-ATR trend @ 1h (`RealStrategyRegression2`), ADX/Williams%R @ 15m
     (`RealStrategyRegression3`), Alligator @ 1h — two extra 4h data routes, **fast**
     simulator. 104 trades (64L/40S), trades_hash `80e934a1e814f77a`.

   Both pass identically on master (18.0 s / 11.0 s) and on this branch
   (4.6 s / 5.1 s on the Pi — the speedup is visible in the runtimes), with candles
   from the same seeded generator as jesse-bench. Suite total is now **500 passed**.
   They are marked `@pytest.mark.slow` (deselect with `-m "not slow"`) but run by
   default. Note: the tests pre-register their exchange's sandbox driver to dodge a
   pre-existing (master-too) quirk where the API singleton freezes its driver map at
   first construction, silently dropping all orders for any *new* exchange name in
   later same-process backtests.

---

## 3. Reviewer's guide

Suggested review order: **(A) jesse-rust kernels** (self-contained, the contracts
everything else leans on) → **(B) jesse call-sites of those kernels** → **(C) pure-Python
jesse commits** (no Rust dependency, can be reviewed independently).

### A. jesse-rust (`perf-backtests`, 5 commits, review bottom-up)

| # | commit | what | measured | risk notes |
|---|---|---|---|---|
| A1 | `4d488f8` | Add scalar `*_last` kernels for ema/sma/rsi/atr/bollinger_bands: same recurrences as the array versions, no full-series allocation; empty input raises IndexError to mirror `result[-1]` | enables B1 (measured there); sweeps: 4000 randomized trials bit-equal | Additive only — nothing calls them until jesse B1. Check each loop is literally the array version minus the output writes. |
| A2 | `ae8783e` | Add `candle_from_one_minutes`: bit-exact HTF candle builder, incl. a replica of numpy's pairwise summation for volume and `maximum/minimum.reduce` NaN/tie folds | enables B2 | **The pairwise-sum replica is the one numpy-version-coupled piece** (verified on numpy 1.26.4, every length <= 4320; callers gate on <= 4320 rows). See §5. |
| A3 | `bf17042` | Add `fix_jumped_candles`: in-place whole-series forward pass of `_get_fixed_jumped_candle` | enables B3/B4 | Mutates the caller's array — jesse callers guard on `writeable` and own those arrays. Reads only closes (never written), which is the whole-series-equals-per-minute argument. |
| A4 | `ba4fde7` | `rsi_last`: hoist the RSI evaluation out of the Wilder recurrence loop (per-iteration divisions + branch were dead work) | kernel 73→66 µs @ n=8640; b:fast 5.62→5.46, b:step 6.94→6.78 | Pure hoist: loop state is only avg_gain/avg_loss; RSI is a function of the final averages. 300-case sweep. |
| A5 | `99dd627` | `sma_last`: branch-free fast path for NaN-free sources, works on strided views | kernel 36.5→26.4 µs strided; d:fast 2.43→2.11, d:step 6.02→5.79 | Fast path valid because with no NaNs `count == period` for every window, so the same float ops run in the same order. NaN sources take the original loop. 400-case sweep incl. NaNs + strides. |

### B. jesse — call-sites of the new kernels (require the new jesse-rust wheel)

| # | commit | what | measured | risk notes |
|---|---|---|---|---|
| B1 | `23ec9fe1` | ema/sma/rsi/atr/bollinger_bands call `*_last` when `sequential=False` | b:fast 9.90→6.82 (**1.45x**) | Thin: same slicing/source-prep, only the final call changes. `bollinger_bands` also skips a redundant `astype` when already f64. 178 indicator tests pass. |
| B2 | `cdd8b8e6` | `generate_candle_from_one_minutes` + skip-sim `real_candle` built via the Rust kernel, gated on `len <= 4320 and dtype == float64`, numpy fallback above | b:fast 6.82→6.31, a:step 2.27→2.21 | The 4320 gate is the numpy-pairwise contract (§5). All timeframes through 3D are <= 4320 1m rows. |
| B3 | `e86ac0d2` | **Step-simulator 1m-storage prefill**: gap-fix whole series once (Rust), bulk-copy into the storage buffer, per-minute append becomes an index bump | a:step 2.21→1.25, b:step 11.85→7.56 | The big one. Review the guard list + fallback, and the invariant that order-execution minutes still restore rows through the untouched `add_candle` path (`short_candle` stays a row of the input array). `drop_at` is None in backtests, so bypassing `append` loses nothing. |
| B4 | `51be56bc` | Same prefill for the **skip simulator** (the dashboard/MCP default) + per-step loop-invariant hoisting | fast: a 0.38→0.34, b 5.81→5.62, c 2.78→2.58, d 2.63→2.43 | Boundary-only gap fixes replicated exactly (only each step's first candle, ascending order). Order-executing steps keep the original `add_multiple_1m_candles` override path bit-for-bit. |
| B5 | `15cb00d3` | Reuse the step's `real_candle` as the HTF candle when `count == candles_step` (always true single-timeframe) | fast: a 0.33→0.30, b 5.46→5.41, c 2.52→2.43, d 2.11→2.05 | Bit-identical for all non-pipeline runs (the rows are views of the same array, same kernel branch). **One flagged edge case for candle-pipeline sessions — see "Review attention points" below.** |

### C. jesse — pure-Python commits (independent of jesse-rust)

| # | commit | what | measured | risk notes |
|---|---|---|---|---|
| C1 | `f86521f8` | Skip the per-closed-trade DB write when `database.is_open()` is False | neutral here; scales with trade count | Only skips writes that previously *always* raised "Query must be bound to a database" + printed an error block. Persistence behavior with a DB is unchanged. |
| C2 | `e2860dc4` | Cheapen hot candle-storage access: `add_candle` scalar timestamp reads, `get_storage` inline key, `DynamicNumpyArray` index math | a:step 5.33→4.27 | Mechanical. The `arr.array[last_index, 0]` scalar read replaces up to 3 row-view builds; branch conditions (incl. the NaN else-branch) preserved. |
| C3 | `c9d33d09` | Early-exit order simulation: skip candle copy + execution loop when no order falls inside the candle; early-exit `_get_executing_orders`; `update_active_orders` skips rebuilding empty lists | a:step 4.27→3.81, b:step 16.17→14.65 | The tail `add_candle` + position-price update now run once — exactly what the old loop's single break path did. `candle_includes_price` inlined as `low <= price <= high` (same condition). |
| C4 | `8048b4cb` | Cheapen per-indicator-call helpers: `timeframe_to_one_minutes` via module constant, `is_unit_testing` membership test + lru_cache, inline `jh.key()` | b:fast 11.22→10.29 | Error path of `timeframe_to_one_minutes` unchanged (same `InvalidTimeframe`). |
| C5 | `5dfa6320` | Hoist loop invariants out of `_step_simulator`'s per-minute loop (route tuples, timeframe counts, debug flags, bound methods); skip the progress bar when `run_silently` | a:step 3.81→3.05 | Hoisted values are loop-invariant by construction (routes/config/debug flags don't change mid-backtest). `count == 1` is equivalent to `r.timeframe == '1m'` by `TIMEFRAME_TO_ONE_MINUTES`. |
| C6 | `30dcc470` | Skip the redundant candle re-store when no order executed (~260K of 527K `add_candle` calls were byte-for-byte no-op rewrites); pass the already-fetched position to `_check_for_liquidations`; cheapen `_get_fixed_jumped_candle` | a:step 3.05→2.31, b:step →12.17 | The re-store is only needed to overwrite partial candles written during execution; when nothing executed the caller stored this exact object one call earlier. |
| C7 | `fdbd0166` | `is_unit_testing()` near-free outside pytest: keep fully-dynamic checks when `'pytest' in sys.modules`, else compute once (env/argv are immutable for the process) | b:fast 10.29→9.85 | The one behavior-adjacent helper change: verified True inside pytest-run tests, False in plain python; `test_helpers.py` results identical to baseline. |
| C8 | `3453688e` | `_np_array_equal` helper (skips numpy dispatch for the small per-candle compares) + `get_candles` via plain dict lookups | b:fast 6.31→6.09 | Helper falls back to `np.array_equal` for non-ndarray inputs; NaN != NaN semantics match `equal_nan=False`. `get_candles` raises the same `RouteNotFound`. |
| C9 | `20c6b834` | Scalar-compare <= 8-element arrays in `_np_array_equal` | b:fast 6.09→5.78 | Same float/NaN semantics as `(a1 == a2).all()`. |
| C10 | `55f0ad77` | Flatten `Position.type`/`is_open` property chains (read `qty`/`_min_qty` once) | ~0–1.5% (noise) | **No caching** — pure restructuring of per-call reads; nothing can go stale; deliberately safe for live trading (Position is shared with live). |

### Review attention points (flagged during the docs pass — not fixed, by design)

1. **B5 `15cb00d3` x candle pipelines.** `BaseCandlesPipeline.get_candles` returns the
   pipeline's own `_output` buffer (not a view of the main array), and the write-back
   `candles_arr[i:i_step] = short_candles` happens *before* the step-boundary
   `_get_fixed_jumped_candle` mutates `short_candles[0]`. Old code built the HTF candle
   from `candles_arr` (pre-fix boundary row); the reuse now hands back `real_candle`,
   which was built from `short_candles` (post-fix). So **for research sessions that use a
   candles pipeline**, when a jumped-candle fix actually fires at a step boundary and a
   route's timeframe count equals `candles_step`, the HTF candle's open (and possibly
   high/low) can differ from pre-branch behavior. Non-pipeline runs are unaffected
   (there `short_candles` *is* a view, so the rows are identical), which is why every
   fingerprint and test still passes. Arguably the new value is *more* consistent (it
   matches the candle fills ran on, and matches the step simulator), but it is a
   behavior delta for pipeline users. **RESOLVED before review:** the reuse is now gated
   on `(storage_1m is not None or candles_pipeline is None)` (commit after the docs
   pass), so pipeline sessions take the original rebuild path and the branch is strictly
   behavior-preserving everywhere. Fingerprints re-verified after the gate
   (`results/*-gatecheck.json`). If you'd rather adopt the more-consistent post-fix
   value for pipelines too, that's a one-line follow-up — flagged here as your call.
2. **Pre-existing, untouched:** the fast/step divergence on gapped/synthetic data (skip
   sim gap-fixes only step-boundary candles; step sim fixes every minute). Both prefills
   replicate their own simulator's existing behavior exactly. Also pre-existing:
   `add_candle`'s backfill loop iterates `range(max(20, len(arr) - 1))` — the comment
   says "last 20" but `max` makes it scan nearly the whole array; left alone.

---

## 4. Shipping order — jesse-rust MUST go first

The jesse branch imports **7 functions that do not exist in any released jesse-rust
wheel**: `ema_last`, `sma_last`, `rsi_last`, `atr_last`, `bollinger_bands_last`,
`candle_from_one_minutes`, `fix_jumped_candles`. Merging/releasing jesse first would
break every install at import time.

1. Merge jesse-rust `perf-backtests`, **bump its version** (currently 1.1.0 → suggest
   1.2.0), let CI build multi-platform wheels (manylinux x86_64/aarch64, macOS, Windows),
   release to PyPI.
2. Raise jesse's `jesse-rust` dependency pin to the new version.
3. Only then merge/release jesse `perf-backtests`.
4. Before release, re-run the suite on x86_64 (`bench.py --label release-check` then
   `--compare` vs `results/baseline.json`) — all timings here are Pi/aarch64; the
   fingerprint compare is the part that must pass everywhere.

---

## 5. Caveats

- **The bench exaggerates recursive-indicator cost.** It runs with
  `warmup_candles_num=0`, so `slice_candles` never truncates and every indicator call
  scans the entire growing history (O(N²) overall). Real usage (warmup 240+) caps
  slices, making kernels 1–2 µs instead of 30–140 µs. Consequently: real sessions get
  *more* benefit from the engine-side wins (prefills, hoisting, helper cheapening) and
  *less* from kernel scan-length effects than the table suggests. Quote the headline as
  "~2.1–2.5x fast / ~2.4–4.5x step on this suite", not as a universal constant.
- **numpy-version sensitivity (the one external coupling).** `candle_from_one_minutes`
  replicates numpy's *pairwise* summation order for the volume column, verified
  bit-identical against **numpy 1.26.4** for every block length <= 4320; numpy's
  buffered reduce changes the summation order above that, hence the <= 4320-row gate at
  every call site (covers all timeframes through 3D). **If jesse ever moves to a numpy
  that changes its pairwise blocking, re-run the equivalence sweep** (and the suite
  `--compare`).
- All timings are from one machine (Pi 5 / aarch64). Ratios should transfer; absolute
  numbers won't.

---

## 6. Deliberately rejected as unprovable (protects users)

Each of these would have been a bigger speedup than several shipped commits — and each
was rejected because bit-exactness could not be *proven*, only hoped for:

- **Cross-call indicator carry-state caching** (resuming Wilder/EMA recurrences from the
  previous candle's state): the source window's past can be rewritten (forming candles,
  partial-candle updates during order execution), and invalidation is not airtight.
  A stale cache here silently corrupts every downstream trade.
- **`get_candles` memoization**: same staleness class.
- **Value caches on Order/Position models**: these objects are shared with **live
  trading**; only call-site-local hoisting / pure restructuring was applied (C10),
  never caches.
- **Contiguous-copy of candle columns before kernels**: the copy costs about one strided
  pass, so single-pass kernels gain nothing without cross-call sharing — which was
  rejected above.

The rule the whole branch follows: *an optimization either provably changes nothing, or
it doesn't ship.*

---

## 7. Where the remaining time goes (if anyone wants more)

Fast mode is now kernel-bound (in b_heavy:fast the `*_last` kernels are ~3.1 s of 5.3 s),
and those loops are at their bit-exact floors (division-latency-bound RSI, FMA-chain
EMA, and a 48-byte stride penalty everywhere because candles are row-major). The
realistic next wins, in order: (1) document a sane `warmup_candles_num` for MCP/dashboard
users — worth more than any kernel micro-opt at long horizons; (2) column-major candle
storage or contiguous close-column mirrors — a bigger, riskier refactor; (3) the diffuse
order/position event machinery (~0.2–0.4 s per scenario, spread over dozens of tiny
sites) — diminishing returns.
