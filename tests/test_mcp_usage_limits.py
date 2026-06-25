"""
Tests for the MCP usage-limits feature (jesse/mcp/usage_limits.py).

Covers:
- credit weighting math / config constants
- premium bypass (unlimited)
- free plan under and over the limit
- the limit-reached response shape
- fail-open when the plan can't be determined
- daily reset (TTL set + rollover to a new UTC-day key)

Tests use LocalUsageMeter against a tiny in-memory fake Redis so no real Redis
or license backend is needed, and they're deterministic + isolated.
"""

import importlib

import jesse.mcp.usage_limits as ul


# ---------------------------------------------------------------------------
# Fake Redis — implements only what LocalUsageMeter touches.
# ---------------------------------------------------------------------------

class _FakePipeline:
    def __init__(self, redis):
        self._redis = redis
        self._ops = []

    def incrby(self, key, amount):
        self._ops.append(('incrby', key, amount))
        return self

    def ttl(self, key):
        self._ops.append(('ttl', key))
        return self

    def execute(self):
        results = []
        for op in self._ops:
            if op[0] == 'incrby':
                results.append(self._redis.incrby(op[1], op[2]))
            elif op[0] == 'ttl':
                results.append(self._redis.ttl(op[1]))
        self._ops = []
        return results


class FakeRedis:
    """Minimal in-memory Redis supporting incrby/ttl/expire/pipeline + get for asserts."""

    def __init__(self):
        self.store = {}
        self.ttls = {}

    def incrby(self, key, amount):
        self.store[key] = self.store.get(key, 0) + amount
        return self.store[key]

    def ttl(self, key):
        if key not in self.store:
            return -2
        return self.ttls.get(key, -1)

    def expire(self, key, seconds):
        self.ttls[key] = seconds
        return True

    def pipeline(self):
        return _FakePipeline(self)

    def get(self, key):
        return self.store.get(key)


def _meter(redis, user_id="user-A", limit=50):
    return ul.LocalUsageMeter(redis_client=redis, user_id=user_id, limit=limit)


# ---------------------------------------------------------------------------
# Weighting math / config constants
# ---------------------------------------------------------------------------

def test_default_weights_and_limit():
    # Every expensive run costs 1 credit (no weighting); free budget = 100/day.
    assert ul.CREDIT_WEIGHTS["run_backtest"] == 1
    assert ul.CREDIT_WEIGHTS["run_significance_test"] == 1
    assert ul.CREDIT_WEIGHTS["run_monte_carlo"] == 1
    assert ul.CREDIT_WEIGHTS["run_optimization"] == 1
    assert ul.FREE_DAILY_CREDITS == 100
    assert ul.GUEST_DAILY_CREDITS == 0      # guests can't run research tools at all


def test_weights_overridable_via_env(monkeypatch):
    monkeypatch.setenv("MCP_FREE_DAILY_CREDITS", "200")
    monkeypatch.setenv("MCP_CREDIT_WEIGHT_BACKTEST", "2")
    reloaded = importlib.reload(ul)
    try:
        assert reloaded.FREE_DAILY_CREDITS == 200
        assert reloaded.CREDIT_WEIGHTS["run_backtest"] == 2
    finally:
        # Restore the module to env-free defaults so other tests see clean state.
        monkeypatch.delenv("MCP_FREE_DAILY_CREDITS", raising=False)
        monkeypatch.delenv("MCP_CREDIT_WEIGHT_BACKTEST", raising=False)
        importlib.reload(ul)


def test_consume_accumulates_credits():
    # The meter sums whatever credit amounts it's given (each real run is 1 credit).
    redis = FakeRedis()
    m = _meter(redis, limit=50)
    assert m.consume(1).used == 1
    assert m.consume(5).used == 6
    assert m.consume(5).used == 11


# ---------------------------------------------------------------------------
# LocalUsageMeter: under / over limit + response shape
# ---------------------------------------------------------------------------

def test_under_limit_allows():
    redis = FakeRedis()
    m = _meter(redis, limit=50)
    r = m.consume(40)
    assert r.allowed is True
    assert r.used == 40
    assert r.limit == 50


def test_over_limit_blocks_and_reports_prior_usage():
    redis = FakeRedis()
    m = _meter(redis, limit=50)
    assert m.consume(48).allowed is True            # 48/50
    r = m.consume(5)                                 # would be 53 > 50
    assert r.allowed is False
    assert r.used == 48                              # prior usage, not the rejected add
    assert r.limit == 50


def test_exact_limit_allowed_then_next_blocked():
    redis = FakeRedis()
    m = _meter(redis, limit=50)
    assert m.consume(50).allowed is True            # exactly at limit is OK
    assert m.consume(1).allowed is False            # one more is over


# ---------------------------------------------------------------------------
# Daily reset: TTL set on first write, key rolls over per UTC day
# ---------------------------------------------------------------------------

def test_ttl_set_to_expire_at_utc_midnight():
    redis = FakeRedis()
    m = _meter(redis, limit=50)
    m.consume(1)
    key = m._key()
    ttl = redis.ttls.get(key)
    assert ttl is not None
    assert 0 < ttl <= 24 * 3600        # expires within the next 24h (at next UTC midnight)


def test_key_includes_user_and_utc_day():
    redis = FakeRedis()
    m = _meter(redis, user_id="user-X", limit=50)
    key = m._key()
    assert key.startswith("jesse:mcp:usage:user-X:")
    # day suffix looks like YYYY-MM-DD
    day = key.rsplit(":", 1)[1]
    assert len(day) == 10 and day.count("-") == 2


def test_different_days_use_different_keys(monkeypatch):
    from datetime import datetime, timezone
    redis = FakeRedis()
    m = _meter(redis, limit=50)

    day1 = datetime(2026, 6, 5, 12, 0, tzinfo=timezone.utc)
    day2 = datetime(2026, 6, 6, 12, 0, tzinfo=timezone.utc)
    assert m._key(day1) != m._key(day2)
    # And the reset time for day1 is day2's midnight.
    assert ul._next_utc_midnight(day1) == datetime(2026, 6, 6, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# The gate decorator: premium bypass, free under/over, fail-open, response shape
# ---------------------------------------------------------------------------

def _make_gated(weight, plan, redis, user_id="user-A", limit=50):
    """Build a gated dummy tool wired to a fake meter + fixed plan."""
    calls = {"n": 0}

    def tool(session_id="sid"):
        calls["n"] += 1
        return {"status": "started", "session_id": session_id}

    wrapped = ul.gated(
        weight=weight,
        # the gate passes the resolved (guest vs free) limit; here we pin the meter to the
        # test's explicit `limit` so these cases stay deterministic regardless of plan.
        meter_factory=lambda _lim: _meter(redis, user_id=user_id, limit=limit),
        plan_getter=lambda: plan,
    )(tool)
    return wrapped, calls


def test_premium_always_allowed_unlimited():
    redis = FakeRedis()
    tool, calls = _make_gated(5, "premium", redis, limit=50)
    # Way over what a free user could do — premium sails through every time.
    for _ in range(100):
        res = tool()
        assert res["status"] == "started"
    assert calls["n"] == 100
    # Premium path must not even touch the meter.
    assert redis.store == {}


def test_all_paid_plans_are_unlimited():
    # Any plan that isn't free/guest (basic/pro/enterprise/lifetime/premium, any case)
    # is unlimited and never metered.
    for plan in ("basic", "pro", "enterprise", "lifetime", "premium", "PRO"):
        redis = FakeRedis()
        tool, calls = _make_gated(1, plan, redis, limit=2)   # limit 2, but run 5×
        for _ in range(5):
            assert tool()["status"] == "started"
        assert calls["n"] == 5
        assert redis.store == {}      # never touched the meter


def test_free_under_limit_runs_the_tool():
    redis = FakeRedis()
    tool, calls = _make_gated(5, "free", redis, limit=50)
    res = tool()
    assert res["status"] == "started"
    assert calls["n"] == 1


def test_free_over_limit_returns_structured_response_without_running():
    redis = FakeRedis()
    tool, calls = _make_gated(5, "free", redis, limit=50)
    # 10 runs * 5 credits = 50 (all allowed), the 11th is over.
    for _ in range(10):
        assert tool()["status"] == "started"
    blocked = tool()
    assert calls["n"] == 10                      # tool body NOT executed on the blocked call
    assert blocked["status"] == "limit_reached"
    assert blocked["used"] == 50
    assert blocked["limit"] == 50
    assert blocked["is_guest"] is False
    assert "Upgrade to premium" in blocked["message"]
    assert "Sign up" not in blocked["message"]   # free users get the premium message, not the account one
    assert "00:00 UTC" in blocked["message"]
    assert blocked["reset_at"]                   # ISO timestamp present


def test_guest_is_blocked_and_told_an_account_is_required():
    # Guests get 0 — the very first run is blocked, with an account-required message (no reset).
    redis = FakeRedis()
    tool, calls = _make_gated(1, "guest", redis, limit=0)
    blocked = tool()
    assert calls["n"] == 0                            # tool body never ran
    assert blocked["status"] == "limit_reached"
    assert blocked["is_guest"] is True
    assert "account" in blocked["message"].lower()   # message states a free account is required
    assert "Upgrade to premium" not in blocked["message"]


def test_gate_selects_guest_vs_free_limit():
    # The gate must pass GUEST_DAILY_CREDITS for a guest and FREE_DAILY_CREDITS for free.
    seen = {}

    def factory(lim):
        seen["lim"] = lim
        return ul.LocalUsageMeter(redis_client=FakeRedis(), user_id="u", limit=lim)

    def tool():
        return {"status": "started"}

    ul.gated(1, meter_factory=factory, plan_getter=lambda: "guest")(tool)()
    assert seen["lim"] == ul.GUEST_DAILY_CREDITS
    ul.gated(1, meter_factory=factory, plan_getter=lambda: "free")(tool)()
    assert seen["lim"] == ul.FREE_DAILY_CREDITS


def test_no_license_token_is_treated_as_guest(monkeypatch):
    # No token at all → guest (metered), NOT fail-open. Only a real backend error fails open.
    monkeypatch.setattr("jesse.services.auth.get_access_token", lambda: None)
    assert ul.get_user_plan() == "guest"


def test_fail_open_when_plan_undetermined():
    redis = FakeRedis()
    # plan=None simulates a license-backend error → must allow, never meter.
    tool, calls = _make_gated(5, None, redis, limit=1)
    for _ in range(20):
        assert tool()["status"] == "started"
    assert calls["n"] == 20
    assert redis.store == {}                     # meter untouched on fail-open


def test_rejected_run_does_not_consume_credits():
    # A blocked heavy run must NOT inflate the counter — a later cheaper run that
    # still fits under the limit must be allowed.
    redis = FakeRedis()
    m = _meter(redis, limit=50)
    assert m.consume(48).allowed is True            # 48/50
    assert m.consume(5).allowed is False            # optimization (53) → blocked
    assert int(redis.get(m._key()) or 0) == 48      # counter unchanged by the rejected run
    r = m.consume(1)                                 # a backtest still fits (49 <= 50)
    assert r.allowed is True
    assert r.used == 49


def test_fail_open_when_meter_raises():
    class BoomRedis(FakeRedis):
        def get(self, key):
            raise RuntimeError("redis down")

    tool, calls = _make_gated(5, "free", BoomRedis(), limit=50)
    # Meter blows up → must fail open and still run the tool.
    assert tool()["status"] == "started"
    assert calls["n"] == 1


def test_meter_selection_default_is_local():
    assert isinstance(ul.get_usage_meter(), ul.LocalUsageMeter)


# ---------------------------------------------------------------------------
# Remote (api2-authoritative) meter path
# ---------------------------------------------------------------------------

def _gated_remote(monkeypatch, decision):
    """A gated tool running through the REMOTE backend, with _remote_usage_decision stubbed."""
    import jesse.mcp.usage_limits as ul
    monkeypatch.setattr(ul, "USAGE_METER_BACKEND", "remote")
    monkeypatch.setattr(ul, "_remote_usage_decision", lambda feature: decision)
    calls = []

    @ul.gated(1)
    def tool():
        calls.append(1)
        return "ran"

    return tool, calls


def test_remote_allowed_runs_the_tool(monkeypatch):
    import jesse.mcp.usage_limits as ul
    tool, calls = _gated_remote(monkeypatch, ul.ConsumeResult(allowed=True, used=1, limit=100))
    assert tool() == "ran"
    assert len(calls) == 1


def test_remote_blocked_free_returns_limit_reached(monkeypatch):
    import jesse.mcp.usage_limits as ul
    tool, calls = _gated_remote(monkeypatch, ul.ConsumeResult(allowed=False, used=100, limit=100, is_guest=False))
    out = tool()
    assert isinstance(out, dict) and out["status"] == "limit_reached"
    assert out["is_guest"] is False
    assert len(calls) == 0  # tool NOT run


def test_remote_blocked_guest_gets_account_message(monkeypatch):
    import jesse.mcp.usage_limits as ul
    tool, calls = _gated_remote(monkeypatch, ul.ConsumeResult(allowed=False, used=0, limit=0, is_guest=True))
    out = tool()
    assert out["status"] == "limit_reached" and out["is_guest"] is True
    assert "account" in out["message"].lower()
    assert len(calls) == 0


def test_remote_fails_open_when_backend_unreachable(monkeypatch):
    # _remote_usage_decision returns None on any error -> the tool must still run.
    tool, calls = _gated_remote(monkeypatch, None)
    assert tool() == "ran"
    assert len(calls) == 1


def test_remote_usage_decision_parses_response_and_sends_feature(monkeypatch):
    import jesse.mcp.usage_limits as ul

    class FakeResp:
        status_code = 200
        headers = {"Content-Type": "application/json"}

        def json(self):
            return {"allowed": True, "remaining": 87, "limit": 100, "tier": "free"}

    captured = {}

    def fake_post(url, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        return FakeResp()

    monkeypatch.setattr("jesse.services.auth.get_access_token", lambda: "tok-123")
    monkeypatch.setattr("requests.post", fake_post)
    res = ul._remote_usage_decision("mcp")
    assert res.allowed is True
    assert res.limit == 100
    assert res.used == 13  # 100 - 87
    assert res.is_guest is False
    assert captured["url"].endswith("/usage")
    assert captured["json"] == {"license_api_token": "tok-123", "feature": "mcp"}


def test_remote_usage_decision_fails_open_on_non_200(monkeypatch):
    import jesse.mcp.usage_limits as ul

    class FakeResp:
        status_code = 503
        headers = {"Content-Type": "application/json"}

        def json(self):
            return {}

    monkeypatch.setattr("jesse.services.auth.get_access_token", lambda: "tok")
    monkeypatch.setattr("requests.post", lambda *a, **k: FakeResp())
    assert ul._remote_usage_decision("mcp") is None
