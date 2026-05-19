import os
import numpy as np
from scipy.stats import gaussian_kde
from datetime import datetime, timedelta
from jesse.routes import router
from jesse.store import store
from jesse.services.candle_service import get_candles_from_db
from jesse.utils import prices_to_returns

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as mticker
from matplotlib.colors import TwoSlopeNorm

_BACKTEST_CHART_NAMES = ['equity_curve', 'cumulative_returns', 'drawdown', 'underwater', 'monthly_heatmap', 'monthly_distribution', 'trade_pnl']
BACKTEST_CHART_NAMES = _BACKTEST_CHART_NAMES

_THEMES = {
    'light': {
        'fig_facecolor':    'white',
        'axes_facecolor':   '#f8f8f8',
        'text_color':       'black',
        'title_color':      'black',
        'grid_color':       '#cccccc',
        'tick_color':       'black',
        'spine_color':      '#cccccc',
        'legend_facecolor': 'white',
        'legend_edgecolor': '#cccccc',
        'portfolio_line':   '#818CF8',
        'benchmark_colors': ['#f59e0b', '#fb7185', '#60A5FA', '#f472b6', '#A78BFA'],
        'drawdown_fill':    'tomato',
        'shading':          'tomato',
        'positive_bar':     '#22c55e',
        'negative_bar':     'tomato',
        'kde_line':         'steelblue',
        'mean_line':        'darkred',
        'median_line':      '#f59e0b',
    },
    'dark': {
        'fig_facecolor':    '#333333',
        'axes_facecolor':   '#2a2a2a',
        'text_color':       '#e5e7eb',
        'title_color':      '#f6f7ee',
        'grid_color':       '#4a4a4a',
        'tick_color':       '#e5e7eb',
        'spine_color':      '#4a4a4a',
        'legend_facecolor': '#333333',
        'legend_edgecolor': '#4a4a4a',
        'portfolio_line':   '#818CF8',
        'benchmark_colors': ['#fbbf24', '#fb7185', '#60A5FA', '#f472b6', '#A78BFA'],
        'drawdown_fill':    '#ef4444',
        'shading':          '#ef4444',
        'positive_bar':     '#22c55e',
        'negative_bar':     '#ef4444',
        'kde_line':         '#3b82f6',
        'mean_line':        '#fca5a5',
        'median_line':      '#fbbf24',
    },
}


def _compute_drawdown_series(daily_balance: list, start_date: datetime) -> list:
    """Return list of (date, drawdown_pct) where drawdown_pct <= 0."""
    dates = [start_date + timedelta(days=x) for x in range(len(daily_balance))]
    result = []
    peak = daily_balance[0] if daily_balance else 0.0
    for date, balance in zip(dates, daily_balance):
        if balance > peak:
            peak = balance
        dd = ((balance - peak) / peak * 100) if peak != 0 else 0.0
        result.append((date, dd))
    return result


def _find_worst_drawdown_periods(daily_balance: list, start_date: datetime, n: int = 5) -> list:
    """Return up to n worst drawdown periods sorted by max_drawdown ascending (most negative first)."""
    dd_series = _compute_drawdown_series(daily_balance, start_date)

    periods = []
    in_drawdown = False
    period_start = None
    period_bottom_date = None
    period_min_dd = 0.0

    for i, (date, dd) in enumerate(dd_series):
        if dd < 0 and not in_drawdown:
            in_drawdown = True
            period_start = date
            period_bottom_date = date
            period_min_dd = dd
        elif dd < 0 and in_drawdown:
            if dd < period_min_dd:
                period_min_dd = dd
                period_bottom_date = date
        elif dd >= 0 and in_drawdown:
            in_drawdown = False
            periods.append({
                'start': period_start,
                'bottom': period_bottom_date,
                'recovery': date,
                'max_drawdown': period_min_dd,
            })
            period_start = None
            period_bottom_date = None
            period_min_dd = 0.0

    # Handle open drawdown at end of series
    if in_drawdown and period_start is not None:
        periods.append({
            'start': period_start,
            'bottom': period_bottom_date,
            'recovery': None,
            'max_drawdown': period_min_dd,
        })

    periods.sort(key=lambda p: p['max_drawdown'])
    return periods[:n]


def _compute_monthly_returns(daily_balance: list, start_date: datetime) -> dict:
    """Return dict keyed by (year, month) -> return_pct, sorted chronologically."""
    if not daily_balance:
        return {}

    dates = [start_date + timedelta(days=x) for x in range(len(daily_balance))]
    monthly: dict = {}

    for date, balance in zip(dates, daily_balance):
        key = (date.year, date.month)
        if key not in monthly:
            monthly[key] = {'first': balance, 'last': balance}
        else:
            monthly[key]['last'] = balance

    result = {}
    for key in sorted(monthly.keys()):
        first = monthly[key]['first']
        last = monthly[key]['last']
        result[key] = (last / first - 1) * 100 if first != 0 else 0.0

    return result


def _apply_chart_theme(fig, ax, c: dict) -> None:
    """Apply significance-test-matching color theme to a matplotlib figure and axis."""
    fig.patch.set_facecolor(c['fig_facecolor'])
    ax.set_facecolor(c['axes_facecolor'])
    ax.tick_params(colors=c['tick_color'], labelsize=9)
    ax.xaxis.label.set_color(c['text_color'])
    ax.yaxis.label.set_color(c['text_color'])
    ax.title.set_color(c['title_color'])
    for spine in ax.spines.values():
        spine.set_edgecolor(c['spine_color'])
    ax.grid(True, color=c['grid_color'], linewidth=0.5, alpha=0.5)


def _style_legend(ax, c: dict) -> None:
    """Apply theme colours to a legend already attached to ax."""
    legend = ax.get_legend()
    if legend is None:
        return
    legend.get_frame().set_facecolor(c['legend_facecolor'])
    legend.get_frame().set_edgecolor(c['legend_edgecolor'])
    for text in legend.get_texts():
        text.set_color(c['text_color'])


def _plot_backtest_charts(session_id: str, charts_folder: str, theme: str = 'light', benchmark: bool = False) -> None:  # noqa: C901
    """
    Internal. Generate six separate PNG chart images for a completed backtest.
    Must be called while store.app and store.closed_trades are still populated
    (i.e. before store.reset()).

    Saves files to charts_folder using the predictable naming convention:
      {session_id}_{chart_name}.png
    """
    t = _THEMES.get(theme, _THEMES['light'])
    os.makedirs(charts_folder, exist_ok=True)

    if store.closed_trades.count == 0:
        return

    daily_balance = store.app.daily_balance
    if not daily_balance or len(daily_balance) < 2:
        return

    start_date = datetime.fromtimestamp(store.app.starting_time / 1000)
    dates = [start_date + timedelta(days=x) for x in range(len(daily_balance))]

    # ── Chart 1: Equity Curve ────────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(10, 4))
    fig.patch.set_facecolor(t['fig_facecolor'])
    ax.set_facecolor(t['axes_facecolor'])
    ax.plot(dates, daily_balance, color=t['portfolio_line'], linewidth=1.5, label='Strategy')

    # Fetch and cache benchmark candles once — reused by both chart 1 and chart 2
    bench_series = []  # list of (symbol, color, bench_dates, bench_balance, bench_multiplier)
    if benchmark:
        initial_balance = daily_balance[0]
        bench_colors = t['benchmark_colors']
        # Use store.app.ending_time directly (no +24h). ending_time is just ~1 minute
        # past the last simulated candle, so floor(ending_time) - 1 min lands exactly
        # on the last candle timestamp that exists in the DB. Adding 24h previously
        # caused the fetch to request a finish date one full day beyond the last DB
        # candle, which always raised CandleNotFoundInDatabase.
        benchmark_finish = store.app.ending_time
        for i, r in enumerate(router.routes):
            try:
                _, daily_candles = get_candles_from_db(
                    r.exchange, r.symbol, '1D', store.app.starting_time,
                    benchmark_finish,
                    is_for_jesse=False, warmup_candles_num=0, caching=True
                )
                daily_returns = prices_to_returns(daily_candles[:, 2])
                daily_returns[0] = 0
                bench_multiplier = (1 + daily_returns / 100).cumprod()
                bench_balance = initial_balance * bench_multiplier
                bench_dates = [start_date + timedelta(days=x) for x in range(len(bench_balance))]
                color = bench_colors[i % len(bench_colors)]
                bench_series.append((r.symbol, color, bench_dates, bench_balance, bench_multiplier))
                ax.plot(bench_dates, bench_balance, color=color, linewidth=1.2, linestyle='--', label=r.symbol)
            except Exception as e:
                import jesse.helpers as jh
                jh.error(f'Could not generate benchmark chart for {r.symbol}: {e}')

    ax.set_ylabel('Balance', color=t['text_color'])
    ax.set_xlabel('Date', color=t['text_color'])
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    fig.autofmt_xdate(rotation=30)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f'{x:,.0f}'))
    _apply_chart_theme(fig, ax, t)
    ax.legend(fontsize=9, facecolor=t['legend_facecolor'], edgecolor=t['legend_edgecolor'])
    _style_legend(ax, t)
    plt.tight_layout()
    plt.savefig(os.path.join(charts_folder, f'{session_id}_equity_curve.png'), dpi=130, bbox_inches='tight', facecolor=t['fig_facecolor'])
    plt.close(fig)

    # ── Chart 2: Cumulative Returns vs Benchmark (Log Scaled) ────────────────
    initial_balance = daily_balance[0]
    # Compute portfolio cumulative return as a growth multiplier (1.0 = 0% return)
    portfolio_multiplier = [b / initial_balance for b in daily_balance]

    fig, ax = plt.subplots(figsize=(10, 4))
    fig.patch.set_facecolor(t['fig_facecolor'])
    ax.set_facecolor(t['axes_facecolor'])

    ax.plot(dates, portfolio_multiplier, color=t['portfolio_line'], linewidth=1.5, label='Strategy')

    # Reuse cached benchmark series — no second fetch needed
    for symbol, color, bench_dates, _bench_balance, bench_multiplier in bench_series:
        ax.plot(bench_dates, bench_multiplier, color=color, linewidth=1.2, linestyle='--', label=symbol)

    # 0% return line — multiplier of 1.0
    ax.axhline(1.0, color=t['spine_color'], linewidth=1.0, linestyle='--', zorder=2)

    # Log scale: equal multiplicative distances appear equal visually
    ax.set_yscale('log')

    # Format y-axis ticks as percentage returns: multiplier 1.0 → "0%", 2.0 → "100%", 0.5 → "-50%"
    def _pct_formatter(x, _):
        pct = (x - 1) * 100
        return f'{pct:+.0f}%' if pct != 0 else '0%'

    ax.yaxis.set_major_formatter(mticker.FuncFormatter(_pct_formatter))
    ax.yaxis.set_minor_formatter(mticker.NullFormatter())

    ax.set_ylabel('Cumulative Return', color=t['text_color'])
    ax.set_xlabel('Date', color=t['text_color'])
    # Match chart 1: same AutoDateLocator, same %Y-%m format, same 30° rotation
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    fig.autofmt_xdate(rotation=30)
    _apply_chart_theme(fig, ax, t)
    # Re-apply grid for both major and minor log-scale lines after theme call
    ax.grid(True, which='major', color=t['grid_color'], linewidth=0.5, alpha=0.5)
    ax.grid(True, which='minor', color=t['grid_color'], linewidth=0.3, alpha=0.3)
    ax.legend(fontsize=9, facecolor=t['legend_facecolor'], edgecolor=t['legend_edgecolor'])
    _style_legend(ax, t)
    plt.tight_layout()
    plt.savefig(os.path.join(charts_folder, f'{session_id}_cumulative_returns.png'), dpi=130, bbox_inches='tight', facecolor=t['fig_facecolor'])
    plt.close(fig)

    # ── Chart 3: Drawdown Chart (equity curve + shaded worst-5 periods) ──────
    dd_series = _compute_drawdown_series(daily_balance, start_date)
    worst_periods = _find_worst_drawdown_periods(daily_balance, start_date, n=5)

    fig, ax = plt.subplots(figsize=(10, 4))
    fig.patch.set_facecolor(t['fig_facecolor'])
    ax.set_facecolor(t['axes_facecolor'])
    ax.plot(dates, daily_balance, color=t['portfolio_line'], linewidth=1.5)

    ax.set_ylabel('Balance', color=t['text_color'])
    ax.set_xlabel('Date', color=t['text_color'])
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    fig.autofmt_xdate(rotation=30)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f'{x:,.0f}'))

    for rank, period in enumerate(worst_periods, start=1):
        end = period['recovery'] if period['recovery'] else dates[-1]
        ax.axvspan(period['start'], end, alpha=0.15, color=t['shading'])
        mid = period['start'] + (end - period['start']) / 2
        y_pos = min(daily_balance) + (max(daily_balance) - min(daily_balance)) * 0.05
        ax.text(
            mid, y_pos,
            f"#{rank}\n{period['max_drawdown']:.1f}%",
            ha='center', va='bottom', fontsize=7.5,
            color=t['shading'], fontweight='bold'
        )

    _apply_chart_theme(fig, ax, t)
    plt.tight_layout()
    plt.savefig(os.path.join(charts_folder, f'{session_id}_drawdown.png'), dpi=130, bbox_inches='tight', facecolor=t['fig_facecolor'])
    plt.close(fig)

    # ── Chart 3: Underwater Plot ─────────────────────────────────────────────
    dd_dates = [d for d, _ in dd_series]
    dd_values = [v for _, v in dd_series]

    fig, ax = plt.subplots(figsize=(10, 3))
    fig.patch.set_facecolor(t['fig_facecolor'])
    ax.set_facecolor(t['axes_facecolor'])
    ax.fill_between(dd_dates, dd_values, 0, alpha=0.4, color=t['drawdown_fill'])
    ax.plot(dd_dates, dd_values, color=t['drawdown_fill'], linewidth=0.8)
    ax.axhline(0, color=t['spine_color'], linewidth=0.8, linestyle='--')

    ax.set_ylabel('Drawdown %', color=t['text_color'])
    ax.set_xlabel('Date', color=t['text_color'])
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    fig.autofmt_xdate(rotation=30)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f'{x:.1f}%'))
    _apply_chart_theme(fig, ax, t)
    plt.tight_layout()
    plt.savefig(os.path.join(charts_folder, f'{session_id}_underwater.png'), dpi=130, bbox_inches='tight', facecolor=t['fig_facecolor'])
    plt.close(fig)

    # ── Chart 4: Monthly Returns Heatmap ─────────────────────────────────────
    monthly_returns = _compute_monthly_returns(daily_balance, start_date)

    if monthly_returns:
        years = sorted(set(y for y, m in monthly_returns))
        month_labels = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec', 'Total']

        grid = np.full((len(years), 13), np.nan)
        for (year, month), ret in monthly_returns.items():
            if year in years:
                yi = years.index(year)
                mi = month - 1
                grid[yi, mi] = ret

        # Annual total column (compounded)
        for yi, year in enumerate(years):
            year_rets = [grid[yi, mi] for mi in range(12) if not np.isnan(grid[yi, mi])]
            if year_rets:
                compound = 1.0
                for r in year_rets:
                    compound *= (1 + r / 100)
                grid[yi, 12] = (compound - 1) * 100

        fig_height = max(3, len(years) * 0.55 + 2)
        fig, ax = plt.subplots(figsize=(10, fig_height))
        fig.patch.set_facecolor(t['fig_facecolor'])
        ax.set_facecolor(t['axes_facecolor'])

        masked = np.ma.masked_invalid(grid)
        # Compute the colour scale from monthly columns only (0-11).
        # Including the Total column (12) skews abs_max far too high (e.g. 143% annual
        # return) which compresses every monthly value toward yellow and makes negative
        # months look green instead of red.
        monthly_grid = grid[:, :12]
        abs_max = max(10, float(np.nanmax(np.abs(monthly_grid[~np.isnan(monthly_grid)]))) if not np.all(np.isnan(monthly_grid)) else 10)
        norm = TwoSlopeNorm(vmin=-abs_max, vcenter=0, vmax=abs_max)
        nan_color = t['axes_facecolor']
        cmap_copy = plt.cm.get_cmap('RdYlGn').copy()
        cmap_copy.set_bad(color=nan_color)

        ax.imshow(masked, cmap=cmap_copy, norm=norm, aspect='auto')

        ax.set_xticks(range(13))
        ax.set_xticklabels(month_labels, fontsize=9, color=t['tick_color'])
        ax.set_yticks(range(len(years)))
        ax.set_yticklabels([str(y) for y in years], fontsize=9, color=t['tick_color'])

        ax.tick_params(colors=t['tick_color'])
        for spine in ax.spines.values():
            spine.set_edgecolor(t['spine_color'])

        for yi in range(len(years)):
            for mi in range(13):
                val = grid[yi, mi]
                if not np.isnan(val):
                    text_color = '#000000' if abs(val) < abs_max * 0.6 else '#ffffff'
                    ax.text(mi, yi, f'{val:.1f}%', ha='center', va='center', fontsize=7.5, color=text_color, fontweight='bold')

        plt.tight_layout()
        plt.savefig(os.path.join(charts_folder, f'{session_id}_monthly_heatmap.png'), dpi=130, bbox_inches='tight', facecolor=t['fig_facecolor'])
        plt.close(fig)
    else:
        fig, ax = plt.subplots(figsize=(10, 3))
        fig.patch.set_facecolor(t['fig_facecolor'])
        ax.set_facecolor(t['axes_facecolor'])
        ax.text(0.5, 0.5, 'Not enough data for monthly heatmap', ha='center', va='center', transform=ax.transAxes, color=t['text_color'])
        for spine in ax.spines.values():
            spine.set_edgecolor(t['spine_color'])
        plt.savefig(os.path.join(charts_folder, f'{session_id}_monthly_heatmap.png'), dpi=130, bbox_inches='tight', facecolor=t['fig_facecolor'])
        plt.close(fig)

    # ── Chart 5: Monthly Returns Distribution ────────────────────────────────
    monthly_values = list(monthly_returns.values()) if monthly_returns else []

    fig, ax = plt.subplots(figsize=(8, 4))
    fig.patch.set_facecolor(t['fig_facecolor'])
    ax.set_facecolor(t['axes_facecolor'])
    if len(monthly_values) >= 2:
        arr = np.array(monthly_values)
        if len(arr) >= 10:
            q75, q25 = np.percentile(arr, [75, 25])
            iqr = q75 - q25
            if iqr > 0:
                bw = 2 * iqr * len(arr) ** (-1 / 3)
                n_bins = max(5, int(np.ceil((arr.max() - arr.min()) / bw)))
            else:
                n_bins = 15
        else:
            n_bins = 10

        counts, bin_edges = np.histogram(arr, bins=n_bins)
        bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
        bar_width = bin_edges[1] - bin_edges[0]
        bar_colors = [t['positive_bar'] if c >= 0 else t['negative_bar'] for c in bin_centers]
        ax.bar(bin_centers, counts, width=bar_width * 0.9, color=bar_colors, edgecolor=t['axes_facecolor'], linewidth=0.4, alpha=0.85)

        # KDE curve scaled to match histogram counts
        if len(arr) >= 4:
            try:
                kde = gaussian_kde(arr, bw_method='scott')
                x_range = np.linspace(arr.min() - bar_width, arr.max() + bar_width, 300)
                kde_values = kde(x_range) * len(arr) * bar_width
                ax.plot(x_range, kde_values, color=t['kde_line'], linewidth=2, zorder=5)
            except Exception:
                pass

        mean_val = np.mean(arr)
        median_val = np.median(arr)
        ax.axvline(float(mean_val), color=t['mean_line'], linewidth=1.8, linestyle='--', label=f'Mean: {mean_val:.2f}%')
        ax.axvline(float(median_val), color=t['median_line'], linewidth=1.8, linestyle=':', label=f'Median: {median_val:.2f}%')
        ax.legend(fontsize=9, facecolor=t['legend_facecolor'], edgecolor=t['legend_edgecolor'])
        _style_legend(ax, t)
    else:
        ax.text(0.5, 0.5, 'Not enough data', ha='center', va='center', transform=ax.transAxes, color=t['text_color'])


    ax.set_xlabel('Return %', color=t['text_color'])
    ax.set_ylabel('Frequency', color=t['text_color'])
    _apply_chart_theme(fig, ax, t)
    plt.tight_layout()
    plt.savefig(os.path.join(charts_folder, f'{session_id}_monthly_distribution.png'), dpi=130, bbox_inches='tight', facecolor=t['fig_facecolor'])
    plt.close(fig)

    # ── Chart 6: Trade PnL Distribution ─────────────────────────────────────
    trade_pnls = [trade.pnl_percentage for trade in store.closed_trades.trades]

    fig, ax = plt.subplots(figsize=(8, 4))
    fig.patch.set_facecolor(t['fig_facecolor'])
    ax.set_facecolor(t['axes_facecolor'])
    if len(trade_pnls) >= 2:
        arr = np.array(trade_pnls)
        if len(arr) >= 10:
            q75, q25 = np.percentile(arr, [75, 25])
            iqr = q75 - q25
            if iqr > 0:
                bw = 2 * iqr * len(arr) ** (-1 / 3)
                n_bins = max(5, int(np.ceil((arr.max() - arr.min()) / bw)))
            else:
                n_bins = 15
        else:
            n_bins = 10

        counts, bin_edges = np.histogram(arr, bins=n_bins)
        bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
        bar_width = bin_edges[1] - bin_edges[0]
        bar_colors = [t['positive_bar'] if c >= 0 else t['negative_bar'] for c in bin_centers]
        ax.bar(bin_centers, counts, width=bar_width * 0.9, color=bar_colors, edgecolor=t['axes_facecolor'], linewidth=0.4, alpha=0.85)

        # KDE curve scaled to match histogram counts
        if len(arr) >= 4:
            try:
                kde = gaussian_kde(arr, bw_method='scott')
                x_range = np.linspace(arr.min() - bar_width, arr.max() + bar_width, 300)
                kde_values = kde(x_range) * len(arr) * bar_width
                ax.plot(x_range, kde_values, color=t['kde_line'], linewidth=2, zorder=5)
            except Exception:
                pass

        mean_val = np.mean(arr)
        median_val = np.median(arr)
        ax.axvline(float(mean_val), color=t['mean_line'], linewidth=1.8, linestyle='--', label=f'Mean: {mean_val:.2f}%')
        ax.axvline(float(median_val), color=t['median_line'], linewidth=1.8, linestyle=':', label=f'Median: {median_val:.2f}%')
        ax.legend(fontsize=9, facecolor=t['legend_facecolor'], edgecolor=t['legend_edgecolor'])
        _style_legend(ax, t)
    else:
        ax.text(0.5, 0.5, 'Not enough data', ha='center', va='center', transform=ax.transAxes, color=t['text_color'])


    ax.set_xlabel('PnL %', color=t['text_color'])
    ax.set_ylabel('Frequency', color=t['text_color'])
    _apply_chart_theme(fig, ax, t)
    plt.tight_layout()
    plt.savefig(os.path.join(charts_folder, f'{session_id}_trade_pnl.png'), dpi=130, bbox_inches='tight', facecolor=t['fig_facecolor'])
    plt.close(fig)


def _calculate_equity_curve(daily_balance, start_date, name: str, color: str):
    date_list = [start_date + timedelta(days=x) for x in range(len(daily_balance))]
    eq = [{
        'time': date.timestamp(),
        'value': balance,
        'color': color
    } for date, balance in zip(date_list, daily_balance)]
    return {
        'name': name,
        'data': eq,
        'color': color,
    }


def _generate_color(previous_color):
    # Convert the previous color from hex to RGB
    previous_color = previous_color.lstrip('#')
    r, g, b = tuple(int(previous_color[i:i+2], 16) for i in (0, 2, 4))

    # Modify the RGB values to generate a new color
    r = (r + 50) % 256
    g = (g + 50) % 256
    b = (b + 50) % 256

    # Convert the new color from RGB to hex
    new_color = '#{:02x}{:02x}{:02x}'.format(r, g, b)

    return new_color


def equity_curve(benchmark: bool = False) -> list:
    if store.closed_trades.count == 0:
        return None

    result = []
    start_date = datetime.fromtimestamp(store.app.starting_time / 1000)
    daily_balance = store.app.daily_balance

    # Define the first 10 colors
    colors = ['#818CF8', '#fbbf24', '#fb7185', '#60A5FA', '#f472b6', '#A78BFA', '#f87171', '#6EE7B7', '#93C5FD', '#FCA5A5']

    result.append(_calculate_equity_curve(daily_balance, start_date, 'Portfolio', colors[0]))

    if benchmark:
        initial_balance = daily_balance[0]
        # Use store.app.ending_time directly — same reasoning as _plot_backtest_charts above.
        benchmark_finish = store.app.ending_time
        for i, r in enumerate(router.routes):
            _, daily_candles = get_candles_from_db(
                r.exchange, r.symbol, '1D', store.app.starting_time,
                benchmark_finish, is_for_jesse=False, warmup_candles_num=0, caching=True
            )
            daily_returns = prices_to_returns(daily_candles[:, 2])
            daily_returns[0] = 0
            daily_balance_benchmark = initial_balance * (1 + daily_returns/100).cumprod()

            # If there are more than 10 routes, generate new colors
            if i + 1 >= 10:
                colors.append(_generate_color(colors[-1]))

            result.append(_calculate_equity_curve(daily_balance_benchmark, start_date, r.symbol, colors[(i + 1) % len(colors)]))

    return result
