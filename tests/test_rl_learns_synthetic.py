"""
RL learning test: the agent must NAIL a trivially-learnable synthetic market.

Trains SB3 on an alternating up/down-trend market where the recent return sign almost
perfectly predicts the next move. Buy-and-hold there is ~0, so any large profit can only
come from the agent learning to ride the regimes. End-to-end proof that the RL machinery
(env -> action -> trade -> reward -> learning) works — it should pass every time, on every
OS/Python the RL extras install on. The install step in CI doubles as the "does SB3
install here?" check.

Skips unless the RL extras (gymnasium + stable-baselines3 + torch) are installed. The
actual train/eval runs in a fresh SUBPROCESS so it is immune to global-state pollution
from other tests (jesse's research.backtest does not fully isolate every global).
"""
import os
import subprocess
import sys


def test_rl_agent_learns_easy_market():
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    proc = subprocess.run([sys.executable, os.path.abspath(__file__), '--run'],
                          cwd=repo_root, capture_output=True, text=True)
    assert 'RL_LEARNED' in proc.stdout, (
        "RL agent failed to learn the easy market.\n"
        f"--- stdout ---\n{proc.stdout[-3000:]}\n--- stderr ---\n{proc.stderr[-3000:]}"
    )


# --------------------------------------------------------------------------- #
# Runs in the subprocess (fresh interpreter).
# --------------------------------------------------------------------------- #
def _run():
    import importlib
    import numpy as np
    import torch

    from jesse.research.reinforcement_learning import train_rl_agent_sb3, evaluate_rl_agent_sb3
    from jesse.services import report

    torch.manual_seed(0)
    np.random.seed(0)

    EXCH, SYM = 'Binance Perpetual Futures', 'BTC-USDT'

    def easy_candles(n=4000, regime=20, step=0.005, noise=0.0001, seed=1):
        # Synthetic 1-minute BTC candles with a perfectly alternating trend:
        # every `regime` candles the drift flips between +step and -step per bar.
        # Starting price ~$20k. The pattern is trivially learnable — an RL agent
        # that picks up on recent return sign should dominate buy-and-hold.
        rng = np.random.default_rng(seed)
        # Align timestamp to a clean minute boundary (ms epoch)
        ts0 = 1_600_000_000_000; ts0 -= ts0 % 60_000
        rets = np.empty(n)
        for i in range(n):
            # Direction flips every `regime` bars: even blocks go up, odd go down
            d = 1.0 if (i // regime) % 2 == 0 else -1.0
            rets[i] = d * step + noise * rng.standard_normal()
        # Log-normal price so it never goes negative
        close = 20_000 * np.exp(np.cumsum(rets))
        # Each bar opens at the previous bar's close (gapless)
        open_ = np.empty(n); open_[0] = close[0]; open_[1:] = close[:-1]
        # Tiny random wick on each side (proportional to price, ~0.01% amplitude)
        hl = np.abs(rng.normal(0, 0.0001, n)) * close
        high = np.maximum(open_, close) + hl
        low = np.clip(np.minimum(open_, close) - hl, 1e-6, None)
        vol = rng.uniform(10, 100, n)
        # One timestamp per bar, spaced 60 000 ms (1 minute) apart
        ts = ts0 + np.arange(n, dtype=np.int64) * 60_000
        # Jesse candle format: [timestamp, open, close, high, low, volume]
        arr = np.column_stack([ts, open_, close, high, low, vol]).astype(np.float64)
        return {f'{EXCH}-{SYM}': {'exchange': EXCH, 'symbol': SYM, 'candles': arr}}

    cls = getattr(importlib.import_module('jesse.strategies.RLEasyMomentum'), 'RLEasyMomentum')
    config = {'starting_balance': 10_000, 'fee': 0.0, 'type': 'futures', 'futures_leverage': 1,
              'futures_leverage_mode': 'cross', 'exchange': EXCH, 'warm_up_candles': 0}
    routes = [{'exchange': EXCH, 'strategy': cls, 'symbol': SYM, 'timeframe': '1m'}]
    candles = easy_candles()

    res = train_rl_agent_sb3(config, routes, [], candles, algorithm='DQN',
                             total_timesteps=60_000, n_envs=1, max_steps=1000,
                             random_episode_start=True, train_freq=4)
    n = candles[f'{EXCH}-{SYM}']['candles'].shape[0]
    evaluate_rl_agent_sb3(res['model'], config, routes, [], candles, max_steps=n + 1)
    m = report.portfolio_metrics()
    net = m['net_profit_percentage'] if m else 0.0
    trades = m['total'] if m else 0
    print(f"net={net:.1f}% trades={trades} win={(m['win_rate']*100 if m else 0):.0f}%")
    # buy & hold here is ~0; the threshold is lenient (optimal is +100s of %) so it never
    # flakes, yet a non-learning/random policy (~0 or negative) cannot pass.
    if trades > 0 and net > 50.0:
        print("RL_LEARNED")


if __name__ == '__main__':
    if '--run' in sys.argv:
        _run()
