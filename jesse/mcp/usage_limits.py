"""
MCP Usage Limits
================

Meters the *expensive* research-run MCP tools so that free-plan users get a
generous DAILY credit budget, while premium users are unlimited.

Why this exists
---------------
A handful of MCP tools kick off heavy compute on the user's machine (backtests,
Monte Carlo, optimizations, significance tests). To keep the free plan
sustainable we cap how many of these a free user can fire per UTC day. Cheap
tools (config/candle/strategy reads, draft creation/updates, status polls,
logs, cancel/terminate, …) are NOT metered.

Design overview
---------------
- A small ``UsageMeter`` interface with two implementations:
    * ``LocalUsageMeter``  — Redis-backed daily counter (the default for now).
    * ``RemoteUsageMeter`` — delegates check+consume to the license backend.
- A ``@gated(weight=...)`` decorator wraps the four gated tool functions. Before
  the tool runs it: (1) determines the user's plan, (2) for premium → allow,
  (3) for free → ask the meter to consume ``weight`` credits. If the limit is
  reached it returns a FRIENDLY STRUCTURED dict instead of raising, so the MCP
  client doesn't break.

Plan determination REUSES Jesse's existing license system — it calls the same
``{JESSE_API_URL}/v2/user-info`` endpoint (with the ``LICENSE_API_TOKEN``) that
``jesse.services.general_info.get_general_info`` uses. We do not invent a new
license system.

Fail-open policy
----------------
If the plan cannot be determined (license backend unreachable / errored), we
ALLOW the run and log a warning. We never block a legit user because our own
metering plumbing is down.

NOTE on security: ``LocalUsageMeter`` is trivially bypassable because the MCP
server runs on the user's own machine (they control Redis). It is fine as a
soft/honest limit. For a real enforced limit, switch to ``RemoteUsageMeter``
(see USAGE_LIMITS.md). The meter is selected via config/env so production can
flip to remote without code changes.
"""

import functools
import logging
import os
from datetime import datetime, timezone, timedelta

logger = logging.getLogger("jesse.mcp.usage_limits")


# ---------------------------------------------------------------------------
# Config constants (all overridable via environment variables)
# ---------------------------------------------------------------------------

def _env_int(name: str, default: int) -> int:
    """Read an int from env, falling back to ``default`` on missing/garbage."""
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        logger.warning("Invalid int for %s=%r, using default %s", name, raw, default)
        return default


# Daily credit budget for free-plan users (logged in, not premium). Paid plans are
# unlimited. Override with MCP_FREE_DAILY_CREDITS (e.g. export MCP_FREE_DAILY_CREDITS=200).
FREE_DAILY_CREDITS = _env_int("MCP_FREE_DAILY_CREDITS", 100)

# Daily budget for GUEST users (no license token at all). Default 0 — guests can't run
# the research tools at all; they're nudged to sign up for a (free) account. Override
# with MCP_GUEST_DAILY_CREDITS if you ever want to grant guests a small daily allowance.
GUEST_DAILY_CREDITS = _env_int("MCP_GUEST_DAILY_CREDITS", 0)

# Per-tool credit cost. Every expensive run — backtest, significance test, Monte Carlo,
# optimization — costs exactly 1 credit; there is no weighting. (Kept per-tool and
# env-overridable only in case that ever needs to change.)
CREDIT_WEIGHTS = {
    "run_backtest": _env_int("MCP_CREDIT_WEIGHT_BACKTEST", 1),
    "run_significance_test": _env_int("MCP_CREDIT_WEIGHT_SIGNIFICANCE_TEST", 1),
    "run_monte_carlo": _env_int("MCP_CREDIT_WEIGHT_MONTE_CARLO", 1),
    "run_optimization": _env_int("MCP_CREDIT_WEIGHT_OPTIMIZATION", 1),
}

# Which meter backend to use: "local" (Redis on this machine) or "remote"
# (license backend). Default is local for now. Override with MCP_USAGE_METER.
USAGE_METER_BACKEND = os.environ.get("MCP_USAGE_METER", "local").strip().lower()

# Redis key prefix for the local meter's daily counters.
_REDIS_KEY_PREFIX = "jesse:mcp:usage"


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------

def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_day_str(now: datetime = None) -> str:
    """Return the current UTC day as 'YYYY-MM-DD' (the counter bucket key)."""
    now = now or _utc_now()
    return now.astimezone(timezone.utc).strftime("%Y-%m-%d")


def _next_utc_midnight(now: datetime = None) -> datetime:
    """The next 00:00:00 UTC strictly after ``now`` — when the counter resets."""
    now = now or _utc_now()
    now = now.astimezone(timezone.utc)
    tomorrow = (now + timedelta(days=1)).date()
    return datetime(tomorrow.year, tomorrow.month, tomorrow.day, tzinfo=timezone.utc)


def _reset_at_iso(now: datetime = None) -> str:
    return _next_utc_midnight(now).isoformat()


# ---------------------------------------------------------------------------
# Plan determination (reuses Jesse's existing license system)
# ---------------------------------------------------------------------------

# Result of a consume attempt, returned by every UsageMeter implementation.
class ConsumeResult:
    """
    Outcome of asking a meter to consume credits.

    Attributes:
        allowed:  whether the run may proceed.
        used:     credits used so far today (AFTER this consume if allowed,
                  or the current total if blocked). Best-effort; may be None
                  if the backend doesn't report it.
        limit:    the daily limit in effect.
        reset_at: ISO8601 timestamp of the next reset (next 00:00 UTC).
    """

    def __init__(self, allowed: bool, used=None, limit=None, reset_at=None):
        self.allowed = allowed
        self.used = used
        self.limit = limit
        self.reset_at = reset_at


def get_user_plan() -> str:
    """
    Determine the current user's plan as reported by the license backend
    (e.g. 'free', 'guest', 'basic', 'pro', 'enterprise', 'lifetime', 'premium').

    REUSES the same license endpoint as jesse.services.general_info — calls
    ``POST {JESSE_API_URL}/v2/user-info`` with the LICENSE_API_TOKEN bearer. This
    is a READ of an existing endpoint; we add nothing on the backend.

    Returns:
      - the plan string on success;
      - ``'guest'`` when there is NO license token at all (a guest — metered, smaller
        allowance; deliberately NOT fail-open);
      - ``None`` on a real backend error (unreachable / non-200 / bad response) so the
        caller FAILS OPEN.
    """
    import requests
    from jesse.services.auth import get_access_token
    from jesse.info import JESSE_API_URL

    access_token = get_access_token()
    if not access_token:
        # No license token at all → the user is a GUEST (metered at the smaller guest
        # allowance). This is deliberately NOT fail-open — only a real backend error is.
        return 'guest'

    try:
        response = requests.post(
            JESSE_API_URL + '/v2/user-info',
            headers={'Authorization': f'Bearer {access_token}'},
            timeout=10,
        )
        if response.status_code != 200:
            logger.warning("user-info returned HTTP %s; failing open.", response.status_code)
            return None
        if 'application/json' not in response.headers.get('Content-Type', ''):
            logger.warning("user-info returned non-JSON; failing open.")
            return None
        plan = response.json().get('plan')
        if not plan:
            logger.warning("user-info JSON missing 'plan'; failing open.")
            return None
        return plan
    except Exception as e:
        logger.warning("Failed to fetch plan from license backend (%s); failing open.", e)
        return None


def _plan_is_premium(plan: str) -> bool:
    """
    Any PAID plan is unlimited; only the free tier is metered.

    The license backend's free tier reports 'free' (and signed-out/guest reports
    'guest'); every paid plan (basic / pro / enterprise / lifetime / premium / …)
    is treated as unlimited. Anything we don't recognize as free is treated as
    paid — failing toward NOT blocking, since this is a soft nudge, not a wall.
    """
    if not plan:
        return False
    return plan.strip().lower() not in ('free', 'guest')


# ---------------------------------------------------------------------------
# UsageMeter interface + implementations
# ---------------------------------------------------------------------------

class UsageMeter:
    """Interface: consume credits for the current user/day, atomically."""

    def consume(self, credits: int) -> ConsumeResult:  # pragma: no cover - interface
        raise NotImplementedError


class LocalUsageMeter(UsageMeter):
    """
    Redis-backed daily counter (DEFAULT).

    One key per user/day: ``jesse:mcp:usage:<user_id>:<YYYY-MM-DD>``. We INCRBY
    the weight, and on the first write of the day set an expiry at the next
    00:00 UTC so the bucket self-cleans / resets. Increment + read-back is done
    with a small atomic pipeline.

    Check-then-consume: read the current total and only INCRBY if this request
    fits under the limit — a rejected run must NOT consume a credit (don't push
    the counter past the limit on a blocked request). The tiny race under
    concurrency (two near-simultaneous consumes) is acceptable for a soft,
    per-user daily limit; a strict no-overshoot variant would need a Lua script
    and isn't worth it here.

    ``user_id`` defaults to the LICENSE_API_TOKEN (stable per user) so multiple
    machines sharing a token share a bucket; falls back to 'anonymous'.
    """

    def __init__(self, redis_client=None, user_id: str = None, limit: int = None):
        self._redis = redis_client  # injectable for tests
        self._user_id = user_id
        self._limit = limit if limit is not None else FREE_DAILY_CREDITS

    def _client(self):
        if self._redis is not None:
            return self._redis
        from jesse.services.redis import sync_redis
        return sync_redis

    def _resolve_user_id(self) -> str:
        if self._user_id:
            return self._user_id
        try:
            from jesse.services.auth import get_access_token
            token = get_access_token()
        except Exception:
            token = None
        return token or "anonymous"

    def _key(self, now: datetime = None) -> str:
        return f"{_REDIS_KEY_PREFIX}:{self._resolve_user_id()}:{_utc_day_str(now)}"

    def consume(self, credits: int) -> ConsumeResult:
        now = _utc_now()
        key = self._key(now)
        reset_at = _reset_at_iso(now)
        client = self._client()

        # Check first: a rejected run must not consume credits (see class docstring).
        current = int(client.get(key) or 0)
        if current + credits > self._limit:
            return ConsumeResult(
                allowed=False,
                used=current,
                limit=self._limit,
                reset_at=reset_at,
            )

        # It fits — consume, then ensure a TTL so the bucket resets at UTC midnight.
        new_total = int(client.incrby(key, credits))
        ttl = client.ttl(key)
        # ttl == -1 means "key exists but no expiry"; -2 means missing (shouldn't
        # happen right after INCRBY). Either way, set the reset TTL once.
        if ttl is None or int(ttl) < 0:
            seconds_until_reset = int((_next_utc_midnight(now) - now).total_seconds())
            client.expire(key, max(seconds_until_reset, 1))

        return ConsumeResult(
            allowed=True,
            used=new_total,
            limit=self._limit,
            reset_at=reset_at,
        )


class RemoteUsageMeter(UsageMeter):
    """
    Delegates check+consume to the license backend.

    Calls ``POST {JESSE_API_URL}/mcp-usage/consume`` (see USAGE_LIMITS.md for the
    full contract) with the license token + the credits to consume. The backend
    is authoritative — it owns the counter, the limit, and the reset time — which
    makes the limit tamper-proof (unlike the local meter).

    IMPORTANT: this endpoint does NOT exist on the backend yet. This client is
    written against the documented contract so the backend team can implement
    it. Until then, use the local meter (the default).

    Fail-open: if the backend errors or is unreachable, we ALLOW the run.
    """

    # Endpoint path relative to JESSE_API_URL.
    CONSUME_PATH = "/mcp-usage/consume"

    def __init__(self, access_token: str = None, api_url: str = None, timeout: int = 10):
        self._access_token = access_token
        self._api_url = api_url
        self._timeout = timeout

    def consume(self, credits: int) -> ConsumeResult:
        import requests

        access_token = self._access_token
        api_url = self._api_url
        if access_token is None:
            from jesse.services.auth import get_access_token
            access_token = get_access_token()
        if api_url is None:
            from jesse.info import JESSE_API_URL
            api_url = JESSE_API_URL

        if not access_token:
            logger.warning("RemoteUsageMeter: no license token; failing open.")
            return ConsumeResult(allowed=True)

        try:
            response = requests.post(
                api_url.rstrip('/') + self.CONSUME_PATH,
                headers={'Authorization': f'Bearer {access_token}'},
                json={'credits': credits},
                timeout=self._timeout,
            )
            if response.status_code != 200:
                logger.warning(
                    "RemoteUsageMeter: backend HTTP %s; failing open.", response.status_code
                )
                return ConsumeResult(allowed=True)
            data = response.json()
            return ConsumeResult(
                allowed=bool(data.get('allowed', True)),
                used=data.get('used'),
                limit=data.get('limit'),
                reset_at=data.get('reset_at'),
            )
        except Exception as e:
            logger.warning("RemoteUsageMeter: backend error (%s); failing open.", e)
            return ConsumeResult(allowed=True)


def get_usage_meter(limit: int = None) -> UsageMeter:
    """Build the configured meter. Default = local; 'remote' selects the backend.
    ``limit`` is the resolved daily budget (guest vs free); the local meter enforces
    it, the remote meter ignores it (the backend owns the limit)."""
    if USAGE_METER_BACKEND == "remote":
        return RemoteUsageMeter()
    return LocalUsageMeter(limit=limit)


# ---------------------------------------------------------------------------
# The gate decorator
# ---------------------------------------------------------------------------

def _limit_reached_response(result: ConsumeResult, is_guest: bool = False) -> dict:
    """
    Build the friendly, structured 'limit_reached' dict returned to the client.

    A guest (no license token) is nudged to SIGN UP for a free account — by default
    guests can't run the research tools at all. A free user is nudged to UPGRADE to
    premium (unlimited).
    """
    default_limit = GUEST_DAILY_CREDITS if is_guest else FREE_DAILY_CREDITS
    limit = result.limit if result.limit is not None else default_limit
    used = result.used if result.used is not None else limit
    reset_at = result.reset_at or _reset_at_iso()
    if is_guest:
        message = (
            "Running research through the AI assistant — backtests, Monte Carlo, "
            "optimizations, and significance tests — requires a Jesse account. "
            "Sign up for free at jesse.trade to get started; premium gives you "
            "unlimited runs."
        )
    else:
        message = (
            f"Daily free-plan limit reached ({used} of {limit} research runs used today). "
            f"Upgrade to premium for unlimited runs. Resets at 00:00 UTC."
        )
    return {
        "status": "limit_reached",
        "message": message,
        "used": used,
        "limit": limit,
        "reset_at": reset_at,
        "is_guest": is_guest,
    }


def gated(weight: int, meter_factory=get_usage_meter, plan_getter=get_user_plan):
    """
    Decorator that meters an expensive research-run tool.

    Before the wrapped tool runs:
      1. Determine the user's plan.
      2. paid plan → always allow (unlimited).
      3. plan undetermined / None (backend error) → FAIL OPEN (allow) + warn.
      4. guest (no token) → meter against the smaller guest allowance; free → meter
         against the free allowance. If the meter says no, return the friendly
         'limit_reached' dict WITHOUT calling the tool (so the MCP client gets a
         clean response, not an exception).

    ``meter_factory`` is called with the resolved daily limit. ``meter_factory`` /
    ``plan_getter`` are injectable for testing.
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # 1) Plan
            try:
                plan = plan_getter()
            except Exception as e:
                logger.warning("Plan lookup raised (%s); failing open.", e)
                plan = None

            # 2) Paid plan → unlimited
            if _plan_is_premium(plan):
                return func(*args, **kwargs)

            # 3) Undetermined plan (backend error) → fail open (already warned)
            if plan is None:
                return func(*args, **kwargs)

            # 4) Guest (no license token) or free → meter it. Guests get the smaller
            #    daily allowance + a "log in for more" nudge; free users get the full
            #    allowance + an "upgrade to premium" nudge.
            is_guest = str(plan).strip().lower() == 'guest'
            limit = GUEST_DAILY_CREDITS if is_guest else FREE_DAILY_CREDITS
            try:
                meter = meter_factory(limit)
                result = meter.consume(weight)
            except Exception as e:
                # Metering plumbing failure must never block a legit user.
                logger.warning("Usage meter error (%s); failing open.", e)
                return func(*args, **kwargs)

            if not result.allowed:
                return _limit_reached_response(result, is_guest=is_guest)

            return func(*args, **kwargs)

        return wrapper

    return decorator
