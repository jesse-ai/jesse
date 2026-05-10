# Hedge Mode for Jesse — RFC

> **TL;DR.** Hedge mode without touching `self.position` semantics, without touching the `Position` class, and without touching the `Strategy` lifecycle. We model hedge mode as **two routes that share a symbol**, each with its own normal `Position`. The store keying picks up an optional `side` discriminator. A thin `HedgeStrategy` sugar class lets users write both legs in one file when they want to. That is the entire design.
>
> **Baseline.** All file paths, line counts, and the diff sizing in §3.2 are against upstream `jesse-ai/jesse:master`. This RFC was designed from scratch against the upstream codebase; it does not port code from any existing fork.

---

## 1. Why this needs an RFC

The blocker you flagged is real and load-bearing:

> "everything I've designed so far has been considering one position. So when you say `self.position`, you get one position, because we assume that at all points, that's the one that you have."

Any design that makes `self.position` polymorphic — sometimes `Position`, sometimes a wrapper that aggregates two positions — relocates the cost rather than removing it. Every internal call site that reads `self.position.qty`, `self.position.is_open`, `self.position.entry_price` either has to learn about hedge mode or has to be served by a wrapper that lies about itself. That pressure leaks into user strategies as `isinstance` checks and surprising aggregate semantics (`position.qty == 0` when long and short legs cancel — true but unhelpful).

**This RFC proposes a design where the invariant you stated stays literally true.** `self.position` is always exactly one `Position`. There is no wrapper, no aggregate, no proxy. Hedge mode strategies just have two `self.position` objects in two strategy instances, and a small amount of glue lets one author both.

---

## 2. The model

### 2.1 One concept: `side` on a route

A route today is `(exchange, symbol, timeframe, strategy)`. We extend it with one optional field:

```python
{
    'exchange':  'Bybit USDT Perpetual',
    'symbol':    'ETH-USDT',
    'timeframe': '1h',
    'strategy':  'MyLongLeg',
    'side': 'long',     # NEW — optional. Omitted ⇒ one-way (today's behavior)
}
```

A symbol can appear in **at most two routes**: at most one with `side='long'`, at most one with `side='short'`. Validation enforces this at startup. (We considered `position_side` for self-documentation; `side` is shorter and the route context makes the meaning unambiguous.)

### 2.2 One change: the store keys by `side` when set

```python
# jesse/store/state_positions.py — the only structural change in the framework
def position_key(exchange: str, symbol: str, side: str | None) -> str:
    if side is None:
        return f'{exchange}-{symbol}'                        # today's key
    return f'{exchange}-{symbol}-{side}'                     # hedge key
```

The selector that resolves a strategy's position uses the strategy's own `side` (read off its route at construction time). When unset, it gets today's key, today's `Position`. When set, it gets its own dedicated `Position`.

That is the entire framework change.

### 2.3 What is **not** changed

- `Position` class: no new fields, no new methods, no `side` parameter, no sign convention shifts.
- `Strategy` class: no new lifecycle, no new accessors, no branching.
- Order class: no new fields. Orders are placed by a Strategy on its own Position; the Position already knows which leg it is via the route.
- Broker: no `position_side` kwarg threading. A broker call from a long-leg Strategy targets that Strategy's own Position.
- Trade recording: no split buckets. Each leg's trades are recorded by its Strategy, exactly as today.

### 2.4 What hedge users see

Most users want to write both legs in one place rather than maintaining two strategy files. We provide a thin convenience wrapper — purely sugar over the two-routes mechanism above:

```python
from jesse.strategies import HedgeStrategy, LongLeg, ShortLeg

class MyHedge(HedgeStrategy):
    """Coordinates a long leg and a short leg on the same symbol."""

    class Long(LongLeg):
        def should_long(self):  return self.shared.macd_bullish()
        def go_long(self):      self.buy = 1, self.price
        def update_position(self):
            # Cross-leg read — explicit, public, returns a real Position object.
            short_pos = self.get_position(side='short')
            if short_pos.is_open and short_pos.pnl < -100:
                self.liquidate()  # close own (long) leg only

    class Short(ShortLeg):
        def should_short(self): return self.shared.macd_bearish()
        def go_short(self):     self.sell = 1, self.price
        def update_position(self): ...

    # Shared indicators / state — computed once, accessible from both legs
    def macd_bullish(self):  return ta.macd(self.candles).hist > 0
    def macd_bearish(self):  return ta.macd(self.candles).hist < 0
```

Behind the scenes, `HedgeStrategy` registers `Long` and `Short` as two routes (`side='long'` and `side='short'`) and exposes a shared `self.shared` reference on each so they can call up to the parent for shared computation. The shared-state mechanism is plain attribute lookup on the parent — `self.shared.macd_bullish()` resolves to a method on the `MyHedge` instance, and the parent caches per-bar computations so each leg gets the same result without recomputing. **Each leg is a normal `Strategy` from the framework's perspective, with one `Position`, one lifecycle, one set of orders.** The framework has no special case for `HedgeStrategy`; it sees two strategies on two routes.

For users who explicitly want two separate files (institutional desks running long and short books separately), that path is also valid: write `MyLongLeg(LongLeg)` and `MyShortLeg(ShortLeg)` as standalone strategies, register them on two routes with the same symbol. No `HedgeStrategy` required.

`LongLeg` and `ShortLeg` are tiny base classes (each ~10 lines) that subclass `Strategy` and constrain the signal direction:

```python
class LongLeg(Strategy):
    def should_short(self): return False     # locked
    def go_short(self):     pass             # locked

class ShortLeg(Strategy):
    def should_long(self):  return False     # locked
    def go_long(self):      pass             # locked
```

These exist purely to make intent explicit and to give the runtime something to type-check against. They add no new lifecycle.

---

## 3. Why this is the path of least resistance

### 3.1 The maintainer's invariant survives

`self.position` is always one `Position`, in every code path, in every strategy. The statement that motivated this RFC ("when you say `self.position`, you get one position") is preserved verbatim. Every internal call site that reads `self.position.X` keeps working, untouched, unbranched.

### 3.2 The diff is tiny

| File | Change |
|---|---|
| `jesse/store/state_positions.py` | ~10 lines — keying function, plus pass `side` when constructing a `Position` on a hedge route |
| `jesse/services/selectors.py` | ~5 lines — `get_position` reads the calling strategy's `side` |
| `jesse/strategies/Strategy.py` | ~5 lines — `Strategy.get_position(side=None)` public helper, defaults to own side (no behavior change for existing strategies) |
| `jesse/routes.py` (or equivalent route validation) | ~20 lines — accept `side`, validate symbol pairing, validate strategy class matches declared side |
| `jesse/strategies/__init__.py` | Re-export `HedgeStrategy`, `LongLeg`, `ShortLeg` |
| `jesse/strategies/hedge.py` (new) | ~80 lines — `HedgeStrategy`, `LongLeg`, `ShortLeg`, shared-state plumbing |
| `jesse/config.py` | One sentence in docs; no new config flag needed (presence of `side` on a route is the signal) |
| **Total** | **< 150 lines, almost entirely additive** |

`Position`, `Strategy` lifecycle, `Order`, `Broker`, the trade store — **zero changes**.

### 3.3 Live trading falls out for free

Each leg is already a normal route. Exchanges that support hedge mode at the API level (Bybit's `positionIdx`, Binance's `dualSidePosition`) need exactly one tiny change in their drivers: read the route's `side` and attach the corresponding exchange-specific field to the order payload. That's a per-driver, per-exchange follow-up — but each one is on the order of 5–10 lines because the *plumbing already exists*.

Compare to a wrapper-based design: every exchange driver would need to learn the wrapper's structure and route fills back to the right sub-position.

### 3.4 No new mental model for users

Users who write hedge strategies still write `Strategy` subclasses. They still call `self.buy`, `self.sell`, `self.broker.buy_at_market(...)`. They still read `self.position.qty`. The only new thing is *where they declare it*: `side='long'` on a route, or `class Long(LongLeg)` inside a `HedgeStrategy`. The semantic model — "a position is one direction, with a single qty and entry" — is unchanged.

### 3.5 Backwards compatibility is mathematical, not best-effort

Because the keying function is `f'{exchange}-{symbol}'` exactly when `side` is `None`, and because no existing route or test sets `side`, every existing key is bit-identical. The new `Strategy.get_position(side=None)` defaults to today's behavior. There is no possible behavioral change to one-way strategies. The full Jesse test suite must pass unchanged — and we can prove it before you read line one of the diff.

---

## 4. Trade-offs we accept

This design is intentionally minimalist. Two trade-offs are worth naming:

1. **Shared state across legs is opt-in, not automatic.** When both legs need the same indicator, you compute it once on the parent `HedgeStrategy` and reach up via `self.shared`. A wrapper-based design with a single strategy instance gets shared state for free. We think this is the right trade because the cost (one `self.shared.X` call) is paid by hedge users, while a wrapper-based design forces every user — hedge or not — to think about whether `self.position` might be a wrapper.

2. **Cross-leg actions ("close the short when the long stops out") need explicit cross-references.** A leg can read the other leg's position via `self.get_position(side='short')` — a public, additive method on `Strategy` that defaults to `side=None` (the strategy's own position) so existing strategies see no behavioral change. A leg can place orders against its own leg only. Routing an order to the *other* leg from inside a leg's code is intentionally not supported — it would re-introduce the polymorphism we're avoiding. Cross-leg orchestration belongs on the parent `HedgeStrategy`, which sees both. This is a discipline cost; we believe it's the correct one.

We considered and rejected:

- **Polymorphic `self.position` (the obvious wrapper design).** Rejected because it relocates the cost into every internal call site, leaks `isinstance` checks into user code, and forces a choice about what aggregate semantics `position.qty` should have. None of those choices are good.
- **A new `Position2D` class with `long_qty` and `short_qty` fields.** Rejected because it doubles the surface area of the most-touched class in the framework and forces every formula (PNL, value, liquidation) to learn a new shape.
- **Treating hedge mode as a runtime config flag rather than a per-route attribute.** Rejected because it forces global mode coupling — you can't run a hedge strategy on ETH and a one-way strategy on BTC in the same backtest.

---

## 5. Phasing

| Phase | Scope | What ships |
|---|---|---|
| **1. Backtest** | Everything in §2. `side` on routes, store keying, `LongLeg`/`ShortLeg`/`HedgeStrategy` sugar, validation, full test suite, docs. | A user can run a hedge strategy in `jesse.research.backtest()` and in the standard backtest runner. |
| **2. Paper trading** | Wire the existing paper-trading harness to the new keying. Should be a no-op since paper trading uses the same store. | Hedge strategies work in paper. |
| **3a. Live: Bybit hedge** | Map route `side` → Bybit `positionIdx` (1=long, 2=short). | Bybit hedge live. |
| **3b. Live: Binance dual-side** | Set `dualSidePosition=true` on account; map route `side` → Binance order's `positionSide` field. | Binance hedge live. |
| **3c. UI** | Expose `side` in the route editor on jesse.trade. Add a validation prompt when a symbol appears twice with conflicting/missing sides. | UI parity. |

Phase 1 is what this RFC asks for. Phases 2–3 are listed so the arc is visible.

---

## 6. Locked design decisions

These were the design forks we considered; choices are locked for the PR:

1. **Route field is `side`** (not `position_side`). Shorter; the route context disambiguates from order side.
2. **Shared state** is plain attribute lookup on the parent `HedgeStrategy` (`self.shared.macd_bullish()`). The parent caches per-bar computations. No injection registry, no DI machinery.
3. **Cross-leg reads are public and explicit.** `Strategy.get_position(side=None)` is a public method. It defaults to `side=None`, which returns the calling strategy's own position — bit-identical to today's behavior. Existing strategies that never call it see no change. Hedge strategies pass `side='long'` or `side='short'` to peek at the other leg.
4. **Validation is strict.** A route with `side='long'` must point to a `LongLeg` (or `HedgeStrategy.Long`) subclass. Mismatch → startup error with a clear message. No silent-warn path.
5. **`HedgeStrategy` ships in the same RFC.** Cutting it out would force every hedge user to write two strategy files for trivial cases. The sugar layer is small and additive.

---

## 7. What we're asking for

Approval-in-principle on §2 (the model) and §3 (the diff shape). Once we have that, we'll send a PR against `master` containing:

- The store keying change.
- Public `Strategy.get_position(side=None)` helper.
- Route validation for `side`.
- `LongLeg`, `ShortLeg`, `HedgeStrategy`.
- A new test module `tests/test_hedge_mode.py` covering: independent leg PNL, simultaneous open/close, validation errors, cross-leg reads, and — most importantly — a snapshot test proving the existing test suite is unchanged when no route sets `side`.
- A new doc page `docs/hedge_mode.md`.
