"""
Plotting utility for rule_significance_test() results.
"""

import os
from datetime import datetime

import matplotlib
matplotlib.use('Agg')   # non-interactive backend — safe in scripts and notebooks
from matplotlib import pyplot as plt


# ---------------------------------------------------------------------------
# Theme colour palettes
# ---------------------------------------------------------------------------

_THEMES = {
    'light': {
        'fig_facecolor':  'white',
        'axes_facecolor': '#f8f8f8',
        'text_color':     'black',
        'title_color':    'black',
        'grid_color':     '#cccccc',
        'hist_color':     'steelblue',
        'hist_edge':      'white',
        'reject_color':   'tomato',
        'vline_color':    'darkred',
        'box_facecolor':  'lightyellow',
        'box_alpha':      0.8,
        'box_text_color': 'black',
        'legend_facecolor': 'white',
        'legend_edgecolor': '#cccccc',
        'tick_color':     'black',
        'spine_color':    '#cccccc',
    },
    'dark': {
        'fig_facecolor':  '#333333',   # Dashboard backdrop-dark
        'axes_facecolor': '#2a2a2a',   # Slightly darker than backdrop
        'text_color':     '#e5e7eb',
        'title_color':    '#f6f7ee',   # Dashboard body-dark
        'grid_color':     '#4a4a4a',
        'hist_color':     '#3b82f6',   # blue-500
        'hist_edge':      '#333333',
        'reject_color':   '#ef4444',   # red-500
        'vline_color':    '#fca5a5',   # red-300
        'box_facecolor':  '#444444',
        'box_alpha':      0.9,
        'box_text_color': '#e5e7eb',
        'legend_facecolor': '#333333',
        'legend_edgecolor': '#4a4a4a',
        'tick_color':     '#e5e7eb',
        'spine_color':    '#4a4a4a',
    },
}


def plot_significance_test(
    result: dict,
    charts_folder: str = None,
    theme: str = 'light',
    dpi: int = 150,
    show_title: bool = True,
) -> str:
    """
    Visualise the sampling distribution produced by rule_significance_test().

    The histogram shows where the observed mean sits relative to the
    distribution of simulated means under H0.  The shaded region represents
    the fraction of simulations that equalled or exceeded the observed mean
    (i.e. the p-value).

    Parameters
    ----------
    result        : dict returned by rule_significance_test()
    charts_folder : directory to save the PNG; defaults to ./charts/
    theme         : 'light' (default) or 'dark' — controls matplotlib colours
    dpi           : image resolution (default 150)

    Returns
    -------
    str : absolute path to the saved PNG file
    """
    c = _THEMES.get(theme, _THEMES['light'])

    sim_means = result['simulated_means']
    observed_mean = result['observed_mean']
    p_value = result['p_value']
    annualized = result['annualized_return']
    n_obs = result['n_observations']
    n_sim = result['n_simulations']

    fig, ax = plt.subplots(figsize=(10, 5))
    fig.patch.set_facecolor(c['fig_facecolor'])
    ax.set_facecolor(c['axes_facecolor'])

    # ---- Histogram of simulated means ----
    n_bins = min(50, max(20, n_sim // 10))
    counts, bin_edges, patches = ax.hist(
        sim_means, bins=n_bins,
        color=c['hist_color'], edgecolor=c['hist_edge'], linewidth=0.4, alpha=0.85,
        label='Simulated means (H₀)',
    )

    # ---- Shade the rejection region (p-value area) ----
    for patch, left_edge in zip(patches, bin_edges[:-1]):
        if left_edge >= observed_mean:
            patch.set_facecolor(c['reject_color'])
            patch.set_alpha(0.9)

    # ---- Vertical line at observed mean ----
    ax.axvline(
        observed_mean, color=c['vline_color'], linewidth=1.8, linestyle='--',
        label=f'Observed mean = {observed_mean:.6f}',
    )

    # ---- Significance label ----
    if p_value <= 0.001:
        significance = '  ★★★  highly significant (p ≤ 0.001)'
    elif p_value <= 0.01:
        significance = '  ★★  very significant (p ≤ 0.01)'
    elif p_value <= 0.05:
        significance = '  ★  statistically significant (p ≤ 0.05)'
    elif p_value <= 0.10:
        significance = '  ~  possibly significant (p ≤ 0.10)'
    else:
        significance = '  ✕  not significant (p > 0.10)'

    info_text = (
        f'p-value = {p_value:.4f}{significance}\n'
        f'Annualised return = {annualized * 100:.4f} %\n'
        f'Observations = {n_obs} bars   |   Simulations = {n_sim}'
    )
    bbox_props = dict(
        boxstyle='round,pad=0.4',
        facecolor=c['box_facecolor'],
        alpha=c['box_alpha'],
        edgecolor=c['spine_color'],
    )
    ax.text(
        0.02, 0.97, info_text,
        transform=ax.transAxes, verticalalignment='top',
        fontsize=9, family='monospace',
        color=c['box_text_color'],
        bbox=bbox_props,
    )

    # ---- Styling ----
    if show_title:
        ax.set_title(
            'Rule Significance Test — Bootstrap',
            fontsize=12, fontweight='bold', color=c['title_color']
        )
    ax.set_xlabel('Mean bar-level log return', color=c['text_color'])
    ax.set_ylabel('Frequency', color=c['text_color'])
    ax.tick_params(colors=c['tick_color'])
    for spine in ax.spines.values():
        spine.set_edgecolor(c['spine_color'])
    ax.grid(True, color=c['grid_color'], linewidth=0.5, alpha=0.5)

    legend = ax.legend(fontsize=9, facecolor=c['legend_facecolor'], edgecolor=c['legend_edgecolor'])
    for text in legend.get_texts():
        text.set_color(c['text_color'])

    plt.tight_layout()

    # ---- Save ----
    if charts_folder is None:
        charts_folder = os.path.abspath('charts')
    os.makedirs(charts_folder, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'rule_significance_bootstrap_{timestamp}.png'
    path = os.path.join(charts_folder, filename)
    plt.savefig(path, dpi=dpi, bbox_inches='tight', facecolor=c['fig_facecolor'])
    plt.close(fig)
    print(f'Saved significance test chart to: {path}')
    return path
