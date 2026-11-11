import os
import numpy as np
from scipy.stats import gaussian_kde
from datetime import datetime, timedelta, timezone
from jesse.store import store
from jesse.services import benchmark as benchmark_service
from jesse.services.metrics import monthly_returns as compute_monthly_returns

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as mticker
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm

# With more symbols than this, the legend alone would cover the chart. They stay in the chart as
# quiet lines behind the portfolio and the combined holding, and only those two are named.
MAX_LABELED_SYMBOLS = 8
# How close two drawdown labels can be, as a share of the chart's width, before they'd touch.
LABEL_CLEARANCE = 0.07
_BACKTEST_CHART_NAMES = ['equity_curve', 'cumulative_returns', 'drawdown', 'underwater', 'monthly_heatmap', 'monthly_distribution', 'trade_pnl', 'entry_timing']
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
        'heatmap_peak':     '#3730a3',
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
        'heatmap_peak':     '#a5b4fc',
    },
}


def _compute_drawdown_series(daily_balance: list, dates: list[datetime]) -> list:
    """Return list of (date, drawdown_pct) where drawdown_pct <= 0."""
    result = []
    peak = daily_balance[0] if daily_balance else 0.0
    for date, balance in zip(dates, daily_balance):
        if balance > peak:
            peak = balance
        dd = ((balance - peak) / peak * 100) if peak != 0 else 0.0
        result.append((date, dd))
    return result


def _find_worst_drawdown_periods(daily_balance: list, dates: list[datetime], n: int = 5) -> list:
    """Return up to n worst drawdown periods sorted by max_drawdown ascending (most negative first)."""
    dd_series = _compute_drawdown_series(daily_balance, dates)

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


def _compute_entry_timing(opened_at: list) -> np.ndarray:
    """Return a 7x24 grid of entry counts: rows Monday to Sunday, columns UTC hours."""
    grid = np.zeros((7, 24), dtype=int)
    for timestamp in opened_at:
        date = datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc)
        grid[date.weekday(), date.hour] += 1
    return grid


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


def _percent_tick(multiplier: float, decimals: int) -> str:
    """Format a growth multiplier as a return: 1.0 is "0%", 2.0 is "+100%" and 0.5 is "-50%"."""
    change = round((multiplier - 1) * 100, decimals)
    return f'{change:+,.{decimals}f}%' if change != 0 else '0%'


def _style_legend(ax, c: dict) -> None:
    """Apply theme colours to a legend already attached to ax."""
    legend = ax.get_legend()
    if legend is None:
        return
    legend.get_frame().set_facecolor(c['legend_facecolor'])
    legend.get_frame().set_edgecolor(c['legend_edgecolor'])
    for text in legend.get_texts():
        text.set_color(c['text_color'])


MAX_HISTOGRAM_BINS = 200


def _histogram_bin_count(arr: np.ndarray, max_bins: int = MAX_HISTOGRAM_BINS) -> int:
    """Freedman-Diaconis bin count, capped so a tiny IQR plus one outlier cannot
    ask numpy for billions of bins (see jesse-ai/jesse#641)."""
    if len(arr) < 10:
        return 10
    q75, q25 = np.percentile(arr, [75, 25])
    iqr = q75 - q25
    if not iqr > 0:
        return 15
    bw = 2 * iqr * len(arr) ** (-1 / 3)
    n_bins = np.ceil((arr.max() - arr.min()) / bw)
    if not np.isfinite(n_bins):
        return max_bins
    return int(min(max(5, n_bins), max_bins))


def _plot_backtest_charts(session_id: str, charts_folder: str, theme: str = 'light', benchmark: bool = False) -> None:  # noqa: C901
    """
    Internal. Generate separate PNG chart images for a completed backtest.
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

    dates = [
        datetime.fromtimestamp(timestamp / 1000)
        for timestamp in store.app.daily_balance_timestamps
    ]

    # ── Chart 1: Equity Curve ────────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(10, 4))
    fig.patch.set_facecolor(t['fig_facecolor'])
    ax.set_facecolor(t['axes_facecolor'])
    ax.plot(dates, daily_balance, color=t['portfolio_line'], linewidth=1.5, label='Portfolio')

    # Fetch benchmark candles once — reused by both chart 1 and chart 2
    bench_series = []  # list of (series, color, bench_dates, line style)
    if benchmark:
        bench_colors = t['benchmark_colors']
        all_series = benchmark_service.get_series(daily_balance[0])
        symbols_count = len([s for s in all_series if s['name'] != benchmark_service.BUY_AND_HOLD_NAME])
        for i, series in enumerate(all_series):
            bench_dates = [datetime.fromtimestamp(timestamp / 1000) for timestamp in series['timestamps']]
            # The combined holding of a multi-route run stands apart from the dashed symbols.
            if series['name'] == benchmark_service.BUY_AND_HOLD_NAME:
                color, line_style = t['text_color'], {'linewidth': 1.6, 'linestyle': '-', 'label': series['name']}
            elif symbols_count > MAX_LABELED_SYMBOLS:
                color, line_style = bench_colors[i % len(bench_colors)], {'linewidth': 0.8, 'linestyle': '--', 'alpha': 0.35}
            else:
                color, line_style = bench_colors[i % len(bench_colors)], {'linewidth': 1.2, 'linestyle': '--', 'label': series['name']}
            bench_series.append((series, color, bench_dates, line_style))
            ax.plot(bench_dates, series['balance'], color=color, **line_style)

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

    ax.plot(dates, portfolio_multiplier, color=t['portfolio_line'], linewidth=1.5, label='Portfolio')

    # Reuse cached benchmark series — no second fetch needed
    for series, color, bench_dates, line_style in bench_series:
        ax.plot(bench_dates, series['multiplier'], color=color, **line_style)

    # 0% return line — multiplier of 1.0
    ax.axhline(1.0, color=t['spine_color'], linewidth=1.0, linestyle='--', zorder=2)

    # Log scale: equal multiplicative distances appear equal visually
    ax.set_yscale('log')

    plotted = np.concatenate([portfolio_multiplier, *[series['multiplier'] for series, *_ in bench_series]])
    highest, lowest = float(np.max(plotted)), float(np.min(plotted))
    # The default of one tick per decade leaves most runs with a single label. A run spanning
    # many decades takes fewer of them, or their labels would run into each other.
    subs = (1, 2, 5) if lowest <= 0 or highest / lowest > 100 else (1, 1.5, 2, 3, 5, 7)
    ax.yaxis.set_major_locator(mticker.LogLocator(base=10, subs=subs, numticks=12))

    # A run that moved less than a percent needs decimals, or all of its labels would read 0%.
    spread = (highest - lowest) * 100
    decimals = 0 if spread >= 10 else 1 if spread >= 1 else 2
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: _percent_tick(x, decimals)))
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
    dd_series = _compute_drawdown_series(daily_balance, dates)
    worst_periods = _find_worst_drawdown_periods(daily_balance, dates, n=5)

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

    # Labels sit at the bottom of the chart. One too close to the label before it moves up a level,
    # which keeps the rest clear of the equity line.
    label_levels = {}
    previous_mid, previous_level = None, 0
    for period in sorted(worst_periods, key=lambda period: period['start']):
        mid = period['start'] + ((period['recovery'] or dates[-1]) - period['start']) / 2
        is_close = previous_mid is not None and (mid - previous_mid) < (dates[-1] - dates[0]) * LABEL_CLEARANCE
        previous_level = previous_level + 1 if is_close else 0
        previous_mid = mid
        label_levels[id(period)] = previous_level

    for rank, period in enumerate(worst_periods, start=1):
        end = period['recovery'] if period['recovery'] else dates[-1]
        ax.axvspan(period['start'], end, alpha=0.15, color=t['shading'])
        mid = period['start'] + (end - period['start']) / 2
        y_pos = min(daily_balance) + (max(daily_balance) - min(daily_balance)) * (0.05 + label_levels[id(period)] * 0.12)
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
    monthly_returns = compute_monthly_returns(daily_balance, store.app.daily_balance_timestamps)

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
        counts, bin_edges = np.histogram(arr, bins=_histogram_bin_count(arr))
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
        counts, bin_edges = np.histogram(arr, bins=_histogram_bin_count(arr))
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

    # ── Chart 7: Entry Timing (hour × weekday) ──────────────────────────────
    entry_grid = _compute_entry_timing([trade.opened_at for trade in store.closed_trades.trades])
    cmap = LinearSegmentedColormap.from_list('entry_timing', [t['axes_facecolor'], t['heatmap_peak']])

    fig, ax = plt.subplots(figsize=(10, 3.5))
    _apply_chart_theme(fig, ax, t)
    ax.grid(False)
    mesh = ax.pcolormesh(
        entry_grid, cmap=cmap, vmin=0, vmax=max(int(entry_grid.max()), 1),
        edgecolors=t['fig_facecolor'], linewidth=1.5
    )
    ax.invert_yaxis()
    ax.set_xticks(np.arange(24) + 0.5)
    ax.set_xticklabels(range(24), fontsize=9, color=t['tick_color'])
    ax.set_yticks(np.arange(7) + 0.5)
    ax.set_yticklabels(['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'], fontsize=9, color=t['tick_color'])
    ax.tick_params(length=0)
    ax.set_xlabel('Hour of day (UTC)', color=t['text_color'])
    ax.set_ylabel('Day of week', color=t['text_color'])

    colorbar = fig.colorbar(mesh, ax=ax, fraction=0.03, pad=0.02, ticks=mticker.MaxNLocator(integer=True))
    colorbar.set_label('Entries', color=t['text_color'], fontsize=9)
    colorbar.ax.tick_params(colors=t['tick_color'], labelsize=9, length=0)
    colorbar.outline.set_edgecolor(t['spine_color'])

    plt.tight_layout()
    plt.savefig(os.path.join(charts_folder, f'{session_id}_entry_timing.png'), dpi=130, bbox_inches='tight', facecolor=t['fig_facecolor'])
    plt.close(fig)


def _calculate_equity_curve(daily_balance, start_date, name: str, color: str, timestamps=None):
    if timestamps is not None and len(timestamps) == len(daily_balance):
        date_list = [datetime.fromtimestamp(timestamp / 1000) for timestamp in timestamps]
    else:
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

    result.append(_calculate_equity_curve(
        daily_balance,
        start_date,
        'Portfolio',
        colors[0],
        store.app.daily_balance_timestamps,
    ))

    if benchmark:
        for i, series in enumerate(benchmark_service.get_series(daily_balance[0])):
            # If there are more than 10 routes, generate new colors
            if i + 1 >= 10:
                colors.append(_generate_color(colors[-1]))

            result.append(_calculate_equity_curve(
                series['balance'],
                start_date,
                series['name'],
                colors[(i + 1) % len(colors)],
                series['timestamps'],
            ))

    return result
