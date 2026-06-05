# MCP Usage Limits

The Jesse MCP server meters the *expensive* research-run tools so free-plan
users get a generous DAILY credit budget while premium users are unlimited.

## What is metered

Each of these four "run" tools costs **1 credit** — no weighting:

| Tool                     | Credits |
|--------------------------|---------|
| `run_backtest`           | 1       |
| `run_significance_test`  | 1       |
| `run_monte_carlo`        | 1       |
| `run_optimization`       | 1       |

Everything else (config/candle/strategy/indicator reads, *draft*
creation/updates, status polls, `get_*_session`, logs, cancel/terminate,
purge, …) is FREE and unmetered.

Daily budgets (UTC day): **guests = 0** (no research runs at all — they must sign up),
**free (logged-in) = 100**; any paid plan is **unlimited**.

All of the above are config constants in `jesse/mcp/usage_limits.py` and are
overridable via environment variables:

| Env var                              | Default | Meaning                          |
|--------------------------------------|---------|----------------------------------|
| `MCP_GUEST_DAILY_CREDITS`            | 0       | Daily budget for guests (no token); 0 = must sign up|
| `MCP_FREE_DAILY_CREDITS`             | 100     | Daily budget for free (logged-in)|
| `MCP_CREDIT_WEIGHT_BACKTEST`         | 1       | Credit cost of `run_backtest`    |
| `MCP_CREDIT_WEIGHT_SIGNIFICANCE_TEST`| 1       | Credit cost of `run_significance_test`|
| `MCP_CREDIT_WEIGHT_MONTE_CARLO`      | 1       | Credit cost of `run_monte_carlo` |
| `MCP_CREDIT_WEIGHT_OPTIMIZATION`     | 1       | Credit cost of `run_optimization`|
| `MCP_USAGE_METER`                    | local   | Meter backend: `local` or `remote` |

## How a user's plan is determined

Reuses Jesse's existing license system — a **read of an existing endpoint; nothing
is added on the backend**. `get_user_plan()` calls
`POST {JESSE_API_URL}/v2/user-info` with `Authorization: Bearer <LICENSE_API_TOKEN>`
(the same endpoint `jesse.services.general_info.get_general_info` already uses) and
reads the `plan` field (`free` / `guest` / `basic` / `pro` / `enterprise` /
`lifetime` / `premium` / …).

- Any PAID plan (anything that isn't `free`/`guest`) → always allowed (unlimited).
- **`free`** (logged in, not paid) → metered at the free budget (100/day); the
  over-limit nudge is "upgrade to premium".
- **`guest`** — i.e. NO license token at all → guest budget is **0** by default, so
  guests get **no research runs** and are nudged to **sign up** for a free account.
  A missing token means *guest*, NOT *error*, so this is deliberately not fail-open.
- **Plan undetermined** — a real backend error (token present but `/v2/user-info`
  is unreachable / non-200 / malformed) → **FAIL OPEN** (allow the run, log a
  warning). We never block a legit user because our own metering plumbing is down —
  a soft nudge, not a hard wall.

> The whole feature is **client-side**: the counter lives in the user's own Redis
> (see below) and the plan comes from the existing license read above. No new
> backend endpoint is required. A determined user can bypass a client-side limit;
> that's an accepted trade-off for a nudge.

## Limit-reached response

When a user is over budget, the gated tool returns this structured dict (it does
NOT raise — that would break the MCP client). The `message` and `is_guest` differ
for guests (nudged to **sign up** for a free account) vs free users (nudged to
**upgrade** to premium):

```json
{
  "status": "limit_reached",
  "message": "Daily free-plan limit reached (X of 100 research runs used today). Upgrade to premium for unlimited runs. Resets at 00:00 UTC.",
  "used": 100,
  "limit": 100,
  "is_guest": false,
  "reset_at": "2026-06-06T00:00:00+00:00"
}
```

## Meter backends

The counter lives behind a small `UsageMeter` interface with two
implementations, selected via `MCP_USAGE_METER`:

### `local` (default) — `LocalUsageMeter`

Redis-backed daily counter (reuses `jesse.services.redis.sync_redis`).
One key per user/day: `jesse:mcp:usage:<user_id>:<YYYY-MM-DD>`, where
`<user_id>` is the `LICENSE_API_TOKEN` (or `anonymous`). The key is `INCRBY`'d
by the run's cost (1 credit) and given a TTL that expires at the next 00:00 UTC,
so the counter self-resets daily.

> **Security note:** the local meter is *bypassable* — the MCP server runs on
> the user's own machine and they control Redis. It is a soft/honest limit
> only. For a real, enforced limit use the remote meter below.

### `remote` — `RemoteUsageMeter`

Delegates check+consume to the license backend, which owns the counter and is
authoritative (tamper-proof). **This backend endpoint does not exist yet** —
the client is written against the contract below for the backend team to
implement. Switch on with `export MCP_USAGE_METER=remote`.

#### Backend contract (to be implemented)

**Request**

```
POST {JESSE_API_URL}/mcp-usage/consume
Authorization: Bearer <LICENSE_API_TOKEN>
Content-Type: application/json

{ "credits": 1 }
```

- The license token identifies the user. The backend looks up the user's plan.
- `credits` is the cost of the run the user is about to do (always 1 today).

**Behaviour**

- `premium` users: always `allowed: true` (the backend may skip counting).
- `free`/`guest` users: atomically check the user's daily budget and, if there
  is room, consume `credits`. If consuming would exceed the limit, do NOT
  consume and return `allowed: false`.
- The counter resets at 00:00 UTC each day.

**Response** (HTTP 200)

```json
{
  "allowed": true,
  "used": 15,
  "limit": 100,
  "reset_at": "2026-06-06T00:00:00+00:00"
}
```

| Field      | Type    | Meaning                                                    |
|------------|---------|------------------------------------------------------------|
| `allowed`  | bool    | Whether the run may proceed.                               |
| `used`     | int     | Credits used today (after this consume if allowed).        |
| `limit`    | int     | The user's daily limit (omit/null for unlimited/premium).  |
| `reset_at` | string  | ISO8601 timestamp of the next reset (next 00:00 UTC).      |

**Fail-open:** if the backend returns a non-200, non-JSON, or is unreachable,
the MCP client ALLOWS the run (and logs a warning) so transient backend issues
never block legit users.
```
