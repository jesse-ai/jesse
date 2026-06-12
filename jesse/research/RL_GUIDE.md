# Reinforcement Learning with Jesse

Train a reinforcement-learning (RL) agent that makes trading decisions inside a Jesse
backtest. The agent observes market state each candle, chooses an action (e.g. go long /
flat / short), and is rewarded by how its decisions affect the portfolio. Training uses
[Ray RLlib](https://docs.ray.io/en/latest/rllib/index.html) and runs many backtests in
parallel across your CPU cores.

> Module: `jesse.research.reinforcement_learning`
> Requires the RL extras: `pip install "ray[rllib]" gymnasium torch`

---

## 1. How it works (architecture)

A Jesse backtest is wrapped as a standard Gymnasium environment, `JesseRLEnvironment`:

- **`reset()`** starts a fresh backtest episode — it re-initialises Jesse's global state
  (config / router / store), injects warm-up candles, and creates a *generator* that drives
  the simulation one candle at a time.
- **`step(action)`** hands the action to your strategy, advances the simulation by one
  candle, and reads back the new observation, reward, and done-flag.

Because Jesse uses global singletons (`store`, `config`, `router`), two environments cannot
share one process. Parallelism therefore comes from **separate processes** ("env-runners"),
each running its own independent backtest — which is exactly how Ray RLlib samples. Each
env-runner gets its own core; the learner (neural-network updates) runs in the driver
process. See §6 for the scaling details.

The bridge between your strategy and the agent is `store.rl` (the RL state store): the env
writes the agent's action into it, your strategy reads the action and writes back the
observation / reward / done.

---

## 2. Writing an RL strategy

Subclass `Strategy` as usual and override the RL hooks. Drive your trading logic from
`self.current_action` (the action the agent picked this candle).

```python
import numpy as np
from jesse.strategies import Strategy


class MyRLStrategy(Strategy):
    # --- define the agent's interface ---
    def get_action_space(self):
        from gymnasium import spaces
        return spaces.Discrete(3)            # 0 = flat/hold, 1 = long, 2 = exit

    def get_observation_space(self):
        from gymnasium import spaces
        # must match the shape/dtype returned by get_observation()
        return spaces.Box(low=-np.inf, high=np.inf, shape=(6,), dtype=np.float32)

    # --- what the agent sees each step ---
    def get_observation(self) -> np.ndarray:
        closes = np.asarray(self.candles[-6:, 2], dtype=np.float64)   # column 2 = close
        rets = np.diff(np.log(closes)).astype(np.float32) if closes.size >= 6 else np.zeros(5, np.float32)
        return np.concatenate([rets, [np.float32(self.is_long)]]).astype(np.float32)

    # --- the reward signal the agent maximises ---
    def calculate_reward(self) -> float:
        pv = float(self.portfolio_value)
        prev = getattr(self, '_prev_pv', pv)
        self._prev_pv = pv
        return (pv - prev) / 100.0           # per-step mark-to-market change, scaled

    # --- (optional) end the episode early ---
    def is_rl_episode_done(self) -> bool:
        return False                         # default: episode ends when candles run out

    # --- translate the action into orders ---
    def should_long(self) -> bool:  return self.current_action == 1
    def should_short(self) -> bool: return False
    def should_cancel_entry(self) -> bool: return True

    def go_long(self):
        qty = (self.balance * 0.5) / self.price
        self.buy = qty, self.price

    def go_short(self):
        pass

    def update_position(self):
        if self.current_action == 2:         # exit on the "flat" action
            self.liquidate()
```

The five RL hooks (`get_action_space`, `get_observation_space`, `get_observation`,
`calculate_reward`, `is_rl_episode_done`) have safe no-op defaults on the base `Strategy`,
so you only override what you need. `gymnasium` is imported lazily inside the hooks, so
non-RL strategies never need the RL dependencies installed.

**Designing the reward** is where most of the work is. Common choices: per-step change in
`portfolio_value` (above), realised PnL on close, risk-adjusted returns (penalise drawdown),
or a sparse end-of-episode profit. Start simple.

---

## 3. Running training

```python
from jesse.research.reinforcement_learning import train_rl_agent

config = {'starting_balance': 10_000, 'fee': 0.0, 'type': 'spot',
          'exchange': 'Binance', 'warm_up_candles': 0}
routes = [{'exchange': 'Binance', 'strategy': 'MyRLStrategy', 'symbol': 'BTC-USDT', 'timeframe': '1m'}]
data_routes = []
# candles: {'Binance-BTC-USDT': {'exchange': 'Binance', 'symbol': 'BTC-USDT', 'candles': np.array([...])}}

result = train_rl_agent(
    config, routes, data_routes, candles,
    algorithm='PPO',        # 'DQN' or 'PPO' (see §5)
    num_iterations=100,
    num_workers=8,          # parallel env-runner processes (see §6)
    checkpoint_freq=10,
)
print(result['checkpoints'][-1])     # path to the latest saved model
```

`candles` is the same dict format used by `jesse.research.backtest` — 1-minute candle arrays
with columns `[timestamp, open, close, high, low, volume]`. The strategy must be importable
(a `strategies/<Name>/__init__.py` package on your `PYTHONPATH`, i.e. a normal Jesse project).

`train_rl_agent` returns a dict with `results`, `summaries`, `checkpoints`,
`episode_trading_metrics`, `performance_stats` (CPU efficiency), and `training_duration`.

### Key parameters
| param | meaning |
|---|---|
| `algorithm` | `'DQN'` (off-policy, sample-efficient) or `'PPO'` (on-policy, scales better) |
| `num_iterations` | number of train/update cycles |
| `num_workers` | parallel env-runner processes — set to ~`cpu_cores - 1` |
| `rollout_fragment_length` | env-steps each worker samples per round (kept constant; default 64) |
| `train_batch_size` | learner batch size (default 64; PPO scales it up with workers automatically) |
| `num_steps_sampled_before_learning_starts` | DQN warm-up steps before learning (default 256) |
| `checkpoint_freq` | save a checkpoint every N iterations |

---

## 4. Evaluating a trained agent

```python
from jesse.research.reinforcement_learning import evaluate_rl_agent

ev = evaluate_rl_agent(
    config, routes, data_routes, candles,
    checkpoint_path=result['checkpoints'][-1],
    algorithm='PPO',
    num_episodes=10,
)
print(ev['mean_reward'], ev['std_reward'])
```

---

## 5. Choosing an algorithm: DQN vs PPO

- **DQN** (off-policy, replay buffer, single learner). Sample-efficient — learns from fewer
  environment steps. The **strong default**; on a few cores it is both faster and scales
  better (measured ~2.45x at 3 workers on a 4-core box).
- **PPO** (on-policy). Collects a large rollout from *all* env-runners in parallel, then does
  several synchronous SGD passes (`num_epochs`). Rollout collection — the expensive part with a
  heavy backtest env — is embarrassingly parallel with no replay-buffer/single-learner wall, so
  it is designed to keep scaling on **many cores**. The trade-off is heavier per-iteration
  learning; on few cores that serial SGD makes it slower than DQN. On a many-core machine, tune
  `num_epochs` down (3–5) and raise `num_workers`.

**Benchmark both on your hardware** — the winner depends on your core count. Action/observation
spaces and the strategy hooks are identical for both; switching is just the `algorithm=`
argument.

---

## 6. Multiprocessing & scaling

Parallelism comes from `num_workers` separate env-runner processes, each running an
independent backtest on its own core; the learner runs in the driver process. Ray is sized to
`min(cpu_count, num_workers + 1)` — `num_workers` runners + 1 driver/learner — with **no CPU
over-subscription**.

Guidelines:
- Set `num_workers ≈ cpu_cores - 1` (leave one core for the driver/learner + OS).
- The dominant cost is the Jesse env-step itself (a Python backtest candle), which is exactly
  what parallelizes across runner *processes* — so more cores ⇒ more workers ⇒ more throughput.
- There is a small per-iteration coordination overhead that grows with worker count. With very
  many workers, prefer PPO and/or a larger `rollout_fragment_length` so each iteration does
  more work and amortizes that overhead.
- Benchmarks on a 4-core machine (DQN, working env): throughput scales 1.0 / 1.95 / 2.45x for
  0→2→3 workers, using ~2.9 of 4 cores. On a 12-core machine you have far more headroom —
  raise `num_workers` accordingly and benchmark DQN vs PPO there.

A reproducible benchmark harness lives in `dev-jesse/rl-bench/` (`bench.py`, `run_one.py`,
`diag.py`).

---

## 7. End-to-end example

See `dev-jesse/rl-bench/` for a complete, runnable example:
`strategies/RLExampleStrategy/` (an RL strategy), `common.py` (synthetic candles + config),
and `bench.py` (train + benchmark across worker counts).
