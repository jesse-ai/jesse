import importlib
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from types import SimpleNamespace
from uuid import uuid4

import matplotlib
import matplotlib.image as mpimg
import matplotlib.pyplot as plt
import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from matplotlib.backends.backend_agg import FigureCanvasAgg

from jesse.controllers import backtest_controller
from jesse.models.BacktestSession import BacktestSession
from jesse.services import auth, backtest_report, benchmark, charts, metrics, transformers

DAY_MS = 86_400_000
START = 1_672_531_200_000  # 2023-01-01
SESSION_ID = 'abcd1234-0000-0000-0000-000000000000'
PASSWORD = 'report-password'
AUTHORIZATION = sha256(PASSWORD.encode('utf-8')).hexdigest()


def _curve(name: str, balances, step_ms: int = DAY_MS, timestamps: list = None) -> dict:
    times = timestamps or [START + i * step_ms for i in range(len(balances))]
    return {
        'name': name,
        'color': '#000000',
        'data': [{'time': t / 1000, 'value': float(b), 'color': '#000000'} for t, b in zip(times, balances)],
    }


def _walk(days: int, seed: int, drift: float = 0.001, volatility: float = 0.02) -> np.ndarray:
    random = np.random.default_rng(seed)
    balances = 10_000 * np.cumprod(1 + random.normal(drift, volatility, days))
    balances[0] = 10_000
    return balances


def _metrics(balances, trades: int) -> dict:
    return {
        'total': trades, 'total_winning_trades': trades // 2, 'total_losing_trades': trades - trades // 2,
        'starting_balance': float(balances[0]), 'finishing_balance': float(balances[-1]),
        'net_profit': float(balances[-1] - balances[0]), 'net_profit_percentage': float(balances[-1] / balances[0] - 1) * 100,
        'win_rate': 0.5, 'win_rate_longs': 0.5, 'win_rate_shorts': 0.5, 'longs_percentage': 60.0, 'shorts_percentage': 40.0,
        'ratio_avg_win_loss': 1.5, 'fee': 100.0, 'average_win': 20.0, 'average_loss': 10.0, 'expectancy': 5.0, 'expectancy_percentage': 0.05,
        'gross_profit': 200.0, 'gross_loss': -100.0, 'average_holding_period': 3600.0, 'max_drawdown': -12.5, 'max_underwater_period': 40,
        'annual_return': 25.0, 'annualization': 365, 'sharpe_ratio': 1.25, 'calmar_ratio': 2.0, 'sortino_ratio': 1.8, 'smart_sharpe': 1.2,
        'smart_sortino': 1.7, 'omega_ratio': 1.3, 'serenity_index': 2.1, 'winning_streak': 4, 'losing_streak': 3, 'largest_winning_trade': 50.0,
        'largest_losing_trade': -30.0, 'avg_trades_per_month': 12.0, 'positive_months': 6, 'negative_months': 4,
    }


def _trades(count: int, symbols: list, days: int, seed: int = 1) -> list:
    random = np.random.default_rng(seed)
    pnl = random.normal(5, 25, count)
    return [{
        'symbol': symbols[i % len(symbols)], 'PNL': float(pnl[i]), 'PNL_percentage': float(pnl[i]) / 10, 'fee': 0.5,
        'opened_at': START + int(random.integers(0, max(days, 1))) * DAY_MS + int(random.integers(0, DAY_MS)),
    } for i in range(count)]


def _session(
        days: int = 400, symbols: tuple = ('BTC-USDT',), trades: int = 60, has_benchmark: bool = True, title: str = 'Trend Follower',
        notes: str = None, hyperparameters: list = None, data_routes: list = None, strategies: list = None, balances=None, metric_changes: dict = None,
        form: dict = None,
) -> SimpleNamespace:
    """A session the way it comes back from the database."""
    balances = _walk(days, 1) if balances is None else balances
    curves = [_curve('Portfolio', balances)]
    if has_benchmark:
        holdings = [_walk(len(balances), seed + 2, 0.0008, 0.03) for seed in range(len(symbols))]
        curves += [_curve(symbol, holding) for symbol, holding in zip(symbols, holdings)]
        if len(symbols) > 1:
            curves.append(_curve(benchmark.BUY_AND_HOLD_NAME, np.mean(holdings, axis=0)))

    metrics = _metrics(balances, trades)
    if has_benchmark:
        metrics['benchmark'] = benchmark.calculate_metrics(curves)
    metrics.update(metric_changes or {})

    routes = [
        {'symbol': symbol, 'timeframe': '4h', 'strategy': (strategies or ['TrendFollower'])[i % len(strategies or ['TrendFollower'])]}
        for i, symbol in enumerate(symbols)
    ]
    if form is None:
        form = {
            'exchange': 'Binance Perpetual Futures', 'routes': routes, 'data_routes': data_routes or [], 'start_date': '2023-01-01', 'finish_date': '2024-02-05',
            'config': {'exchange': {'type': 'futures', 'fee': 0.0007, 'futures_leverage': 3, 'futures_leverage_mode': 'cross'}},
        }

    return SimpleNamespace(
        id=SESSION_ID, title=title, description=notes, equity_curve_json=curves, metrics_json=metrics,
        trades_json=_trades(trades, list(symbols), days), hyperparameters_json=hyperparameters or [], state_json={'form': form},
    )


@pytest.fixture
def pages(monkeypatch):
    """The figures of the last report. Saving them stays real, so PDF output problems still surface."""
    figures = []
    save = backtest_report.PdfPages.savefig

    def keep(self, figure, **kwargs):
        figures.append(figure)
        return save(self, figure, **kwargs)

    monkeypatch.setattr(backtest_report.PdfPages, 'savefig', keep)
    return figures


# The shape of the images a real backtest saves, in pixels.
PHOTO_SIZES = {
    'equity_curve': (1286, 505), 'cumulative_returns': (1286, 505), 'drawdown': (1286, 505), 'underwater': (1286, 390),
    'monthly_heatmap': (1286, 400), 'monthly_distribution': (1030, 525), 'trade_pnl': (1030, 525), 'entry_timing': (1286, 455),
}
LIGHT_PHOTO, DARK_PHOTO = (255, 255, 255), (51, 51, 51)


def _save_photos(folder, background: tuple, session_id: str = SESSION_ID, sizes: dict = PHOTO_SIZES) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for name, (width, height) in sizes.items():
        mpimg.imsave(folder / f'{session_id}_{name}.png', np.full((height, width, 3), background, dtype=np.uint8))


@pytest.fixture
def storage(tmp_path, monkeypatch):
    """A disposable project, where backtests save their chart images under storage/."""
    monkeypatch.chdir(tmp_path)
    return tmp_path / 'storage' / 'backtest-charts'


def _photos_shown(figure) -> list:
    """The images on a page, leaving out the logo in its header."""
    images = [axes.images[0].get_array() for axes in figure.axes if axes.images and not axes.axison]
    return images[1:]


def _texts(figures: list) -> list:
    return [text.get_text() for figure in figures for text in figure.texts]


def _assert_fits_the_pages(figures: list) -> None:
    """Text is laid out by hand, so nothing else stops it from running off the page or into the footer."""
    for figure in figures:
        renderer = FigureCanvasAgg(figure).get_renderer()
        width, height = figure.canvas.get_width_height()
        labels = [text.get_text() for text in figure.texts if text.get_text()]
        boxes = np.array([text.get_window_extent(renderer).extents for text in figure.texts if text.get_text()])
        charts_boxes = np.array([axes.get_window_extent(renderer).extents for axes in figure.axes])
        for name, others in (('text', boxes), ('a chart', charts_boxes)):
            overlaps = (
                (boxes[:, None, 0] < others[None, :, 2]) & (others[None, :, 0] < boxes[:, None, 2])
                & (boxes[:, None, 1] < others[None, :, 3]) & (others[None, :, 1] < boxes[:, None, 3])
            )
            if name == 'text':
                np.fill_diagonal(overlaps, False)
            assert not overlaps.any(), f'overlaps {name}: {labels[np.argwhere(overlaps)[0][0]]}'
        pixels_per_inch = height / backtest_report.PAGE_HEIGHT
        footer_line = backtest_report.CONTENT_BOTTOM + 0.2
        for text in figure.texts:
            box = text.get_window_extent(renderer)
            label = text.get_text()
            assert box.x0 >= 0 and box.x1 <= width, f'runs off the side: {label}'
            top_distance = (height - box.y1) / pixels_per_inch
            assert top_distance >= 0, f'runs off the top: {label}'
            is_footer = abs((1 - text.get_position()[1]) * backtest_report.PAGE_HEIGHT - footer_line) < 0.01
            if not is_footer:
                assert (height - box.y0) / pixels_per_inch <= backtest_report.CONTENT_BOTTOM + 0.05, f'runs into the footer: {label}'
        for axes in figure.axes:
            position = axes.get_position()
            assert position.height > 0 and position.width > 0
            assert 0 <= position.y0 and position.y1 <= 1
            assert 0 <= position.x0 and position.x1 <= 1


def _assert_valid(data: bytes, pages_count: int = None) -> None:
    assert data.startswith(b'%PDF')
    assert data.rstrip().endswith(b'%%EOF')
    if pages_count is not None:
        assert len(re.findall(rb'/Type /Page\b', data)) == pages_count


SCENARIOS = {
    'one route': {},
    'one route without benchmark': {'has_benchmark': False},
    'two routes': {'symbols': ('BTC-USDT', 'ETH-USDT')},
    'five routes, the most drawn as lines': {'symbols': tuple(f'S{i}-USDT' for i in range(5))},
    'six routes, too many to draw': {'symbols': tuple(f'S{i}-USDT' for i in range(6))},
    'twenty routes': {'symbols': tuple(f'S{i}-USDT' for i in range(20))},
    'multiple routes without benchmark': {'symbols': ('BTC-USDT', 'ETH-USDT'), 'has_benchmark': False},
    'a route for every strategy': {'symbols': ('BTC-USDT', 'ETH-USDT', 'SOL-USDT'), 'strategies': ['One', 'Two', 'Three']},
    'a month': {'days': 30, 'trades': 5},
    'three days': {'days': 3, 'trades': 2},
    'two balances': {'days': 2, 'trades': 1},
    'one trade': {'trades': 1},
    'twelve years': {'days': 4380},
    'twenty five years': {'days': 9125},
    'an account that was wiped out': {'balances': np.concatenate([np.linspace(10_000, 1, 200), np.zeros(100)])},
    'balances that went negative': {'balances': np.linspace(10_000, -500, 200)},
    'a balance that never moved': {'balances': np.full(200, 10_000.0)},
    'a balance that only rose': {'balances': np.linspace(10_000, 50_000, 200)},
    'enormous returns': {'balances': np.geomspace(10_000, 1e15, 800)},
    'no title': {'title': None},
    'a title with symbols': {'title': 'Pays $100 a day, 100% of the time_{x} ^2 \\alpha'},
    'a long title': {'title': 'A very long title ' * 30},
    'a long title in wide letters': {'title': 'W' * 200},
    'a title in another script': {'title': 'استراتژی روند 趋势策略'},
    'notes': {'notes': 'Costs $5 per trade.\n\nSecond paragraph with $ and % and _ signs.'},
    'very long notes': {'notes': 'Lorem ipsum dolor sit amet. ' * 600},
    'hyperparameters': {'hyperparameters': [['DNA', 'abc'], ['fast', 10], ['slow', 50]]},
    'more hyperparameters than a page holds': {'hyperparameters': [[f'parameter_{i}', i * 1.5] for i in range(200)]},
    'data routes': {'data_routes': [{'symbol': 'BTC-USDT', 'timeframe': '1D'}] * 200},
    'routes, hyperparameters and notes together': {
        'symbols': tuple(f'S{i}-USDT' for i in range(30)), 'notes': 'Note. ' * 500, 'hyperparameters': [[f'p{i}', i] for i in range(45)],
        'data_routes': [{'symbol': 'BTC-USDT', 'timeframe': '1D'}],
    },
    'a long symbol and strategy': {'symbols': ('1000000MOGULONGSYMBOLNAME-USDT', 'ETH-USDT'), 'strategies': ['AVeryLongStrategyNameThatKeepsGoingAndGoing' * 2]},
    'metrics from an older version': {'metric_changes': {'positive_months': None, 'negative_months': None, 'serenity_index': None, 'avg_trades_per_month': None}},
    'undefined and infinite metrics': {'metric_changes': {
        'ratio_avg_win_loss': float('inf'), 'sortino_ratio': float('inf'), 'omega_ratio': float('nan'), 'calmar_ratio': float('-inf'),
        'average_loss': float('nan'), 'average_holding_period': float('nan'), 'max_underwater_period': float('nan'),
    }},
    'no form': {'form': {}},
    'a form without settings': {'form': {'routes': [{'symbol': 'BTC-USDT'}]}},
    'spot': {'form': {'exchange': 'Binance Spot', 'routes': [{'symbol': 'BTC-USDT', 'timeframe': '1D', 'strategy': 'Hold'}], 'config': {'exchange': {'type': 'spot', 'fee': 0.001}}}},
}


@pytest.mark.parametrize('background', [None, LIGHT_PHOTO, DARK_PHOTO], ids=['drawn charts', 'light images', 'dark images'])
@pytest.mark.parametrize('scenario', SCENARIOS.values(), ids=SCENARIOS.keys())
def test_every_scenario_makes_a_report_that_fits_its_pages(scenario, background, pages, storage):
    if background:
        _save_photos(storage, background)

    data = backtest_report.generate_pdf(_session(**scenario))

    _assert_valid(data, len(pages))
    _assert_fits_the_pages(pages)


def test_a_report_has_its_core_pages():
    report_pages = backtest_report._plan_pages(backtest_report._load_report(_session()))

    assert [title for title, _ in report_pages] == ['Summary', 'Metrics', 'Drawdowns and returns', 'Distributions and timing']


def test_the_report_uses_the_images_the_backtest_saved(pages, storage):
    _save_photos(storage, LIGHT_PHOTO)

    backtest_report.generate_pdf(_session())

    shown = [image for figure in pages for image in _photos_shown(figure)]
    assert len(shown) == len(charts.BACKTEST_CHART_NAMES)
    # the pixels of the saved files, and no chart drawn again next to them
    assert sorted((image.shape[1], image.shape[0]) for image in shown) == sorted(PHOTO_SIZES.values())
    assert not [axes for figure in pages for axes in figure.axes if axes.axison]


def test_every_chart_has_the_title_the_dashboard_gives_it(pages, storage):
    _save_photos(storage, LIGHT_PHOTO)

    backtest_report.generate_pdf(_session())

    texts = _texts(pages)
    for title in (
        'Cumulative Returns vs Benchmark', 'Cumulative Returns vs Benchmark (Log Scaled)', 'Drawdown (Worst 5 Periods)', 'Underwater Plot',
        'Monthly Returns Heatmap', 'Monthly Returns Distribution', 'Trade PnL Distribution', 'Entry Timing (Hour × Weekday)',
    ):
        assert title in texts


def test_a_run_without_the_benchmark_titles_its_charts_like_the_dashboard(pages, storage):
    _save_photos(storage, LIGHT_PHOTO)

    backtest_report.generate_pdf(_session(has_benchmark=False))

    assert 'Cumulative Returns' in _texts(pages)
    assert 'Cumulative Returns (Log Scaled)' in _texts(pages)


def test_the_pages_take_the_theme_of_the_images(pages, storage):
    _save_photos(storage, DARK_PHOTO)

    backtest_report.generate_pdf(_session())

    assert all(matplotlib.colors.to_hex(figure.get_facecolor()) == backtest_report.DARK_COLORS.page.lower() for figure in pages)


def test_light_images_keep_the_pages_white(pages, storage):
    _save_photos(storage, LIGHT_PHOTO)

    backtest_report.generate_pdf(_session())

    assert all(matplotlib.colors.to_hex(figure.get_facecolor()) == '#ffffff' for figure in pages)


def test_a_dark_page_has_no_dark_text(pages, storage):
    _save_photos(storage, DARK_PHOTO)

    backtest_report.generate_pdf(_session())

    colors = {matplotlib.colors.to_hex(text.get_color()) for figure in pages for text in figure.texts}
    assert colors <= {backtest_report.DARK_COLORS.ink.lower(), backtest_report.DARK_COLORS.muted.lower()}


@pytest.mark.parametrize('background, logo', [(None, 'logo-light.png'), (LIGHT_PHOTO, 'logo-light.png'), (DARK_PHOTO, 'logo-dark.png')])
def test_every_page_has_the_logo_for_its_theme(background, logo, pages, storage):
    if background:
        _save_photos(storage, background)

    backtest_report.generate_pdf(_session(symbols=tuple(f'S{i}-USDT' for i in range(60)), notes='Notes.'))

    expected = mpimg.imread(os.path.join(backtest_report.LOGO_FOLDER, logo))
    for figure in pages:
        assert 'Jesse' in [text.get_text() for text in figure.texts]
        assert np.array_equal(figure.axes[0].images[0].get_array(), expected)


def test_the_logos_ship_with_the_package():
    manifest = os.path.join(os.path.dirname(backtest_report.__file__), '..', '..', 'MANIFEST.in')

    assert os.path.exists(os.path.join(backtest_report.LOGO_FOLDER, backtest_report.LIGHT_COLORS.logo))
    assert os.path.exists(os.path.join(backtest_report.LOGO_FOLDER, backtest_report.DARK_COLORS.logo))
    assert 'include jesse/services/report_assets/*.png' in open(manifest).read()


def test_a_missing_image_is_drawn_and_the_rest_stay_images(pages, storage):
    _save_photos(storage, LIGHT_PHOTO)
    (storage / f'{SESSION_ID}_underwater.png').unlink()

    backtest_report.generate_pdf(_session())

    assert len([image for figure in pages for image in _photos_shown(figure)]) == len(charts.BACKTEST_CHART_NAMES) - 1
    assert len([axes for figure in pages for axes in figure.axes if axes.axison]) == 1
    assert 'Underwater Plot' in _texts(pages)


def test_a_broken_image_counts_as_missing(pages, storage):
    _save_photos(storage, LIGHT_PHOTO)
    (storage / f'{SESSION_ID}_drawdown.png').write_bytes(b'this is not a png')
    (storage / f'{SESSION_ID}_trade_pnl.png').write_bytes(b'')

    _assert_valid(backtest_report.generate_pdf(_session()))

    assert 'Trade PnL Distribution' in _texts(pages)


def test_without_any_image_the_charts_are_drawn_on_a_light_page(pages, storage):
    backtest_report.generate_pdf(_session())

    assert all(matplotlib.colors.to_hex(figure.get_facecolor()) == '#ffffff' for figure in pages)
    assert len([axes for figure in pages for axes in figure.axes if axes.axison]) >= 5
    # these two have no data of their own to be drawn from
    assert 'Drawdown (Worst 5 Periods)' not in _texts(pages)


def test_an_image_from_another_session_is_never_used(pages, storage):
    _save_photos(storage, DARK_PHOTO, session_id='ffffffff-0000-0000-0000-000000000000')

    backtest_report.generate_pdf(_session())

    assert all(matplotlib.colors.to_hex(figure.get_facecolor()) == '#ffffff' for figure in pages)


def test_a_tall_heatmap_gets_a_page_of_its_own_at_full_width(pages, storage):
    # what a 25 year backtest saves
    _save_photos(storage, LIGHT_PHOTO, sizes={**PHOTO_SIZES, 'monthly_heatmap': (1286, 1800)})

    backtest_report.generate_pdf(_session())

    titles = [figure.texts[1].get_text() for figure in pages]
    assert titles == ['Summary', 'Metrics', 'Drawdowns and returns', 'Monthly returns', 'Distributions and timing']
    # the room it left goes to the next chart, and every chart still appears exactly once
    assert 'Monthly Returns Distribution' in [text.get_text() for text in pages[2].texts]
    assert _texts(pages).count('Monthly Returns Distribution') == 1
    assert len([image for figure in pages for image in _photos_shown(figure)]) == len(charts.BACKTEST_CHART_NAMES)
    _assert_fits_the_pages(pages)


def test_a_short_routes_table_shares_the_metrics_page(pages, storage):
    backtest_report.generate_pdf(_session(symbols=('BTC-USDT', 'ETH-USDT', 'SOL-USDT', 'XRP-USDT'), notes='Short note.'))

    assert len(pages) == 4
    metrics_page = [text.get_text() for text in pages[1].texts]
    assert 'Results by route' in metrics_page and 'XRP-USDT' in metrics_page
    assert 'Short note.' in metrics_page
    _assert_fits_the_pages(pages)


def test_a_long_routes_table_gets_its_own_page(pages, storage):
    backtest_report.generate_pdf(_session(symbols=tuple(f'S{i}-USDT' for i in range(30))))

    assert 'Results by route' not in [text.get_text() for text in pages[1].texts]
    assert 'Results by route' in [text.get_text() for text in pages[4].texts]


def test_the_yearly_returns_are_a_table_of_both_sides(pages, storage):
    session = _session(days=800)

    backtest_report.generate_pdf(session)

    report = backtest_report._load_report(session)
    rows = backtest_report._yearly_rows(report)
    assert [row[0] for row in rows] == ['2023', '2024', '2025']
    assert rows[0][1] == backtest_report._percent(report.strategy.yearly_returns[2023], signed=True)
    assert rows[0][2] == backtest_report._percent(report.buy_and_hold.yearly_returns[2023], signed=True)
    assert 'Yearly returns' in _texts(pages)


def _row_of(page, label: str) -> list:
    y = next(text.get_position()[1] for text in page.texts if text.get_text() == label)
    return [text.get_text() for text in sorted(page.texts, key=lambda text: text.get_position()[0]) if text.get_position()[1] == y and text.get_text()]


def test_the_portfolio_is_the_column_on_the_right(pages, storage):
    session = _session(days=800, symbols=('BTC-USDT', 'ETH-USDT'))

    backtest_report.generate_pdf(session)

    report = backtest_report._load_report(session)
    metrics_page = next(page for page in pages if 'Buy & Hold' in [text.get_text() for text in page.texts])
    # The Trading table starts on the same line, so only the first columns are the comparison.
    assert _row_of(metrics_page, 'Buy & Hold')[:2] == ['Buy & Hold', 'Portfolio']
    label, value, holding = next(row for row in backtest_report._performance_rows(report) if row[1] != row[2])
    assert _row_of(metrics_page, label)[:3] == [label, holding, value]
    year, value, holding = backtest_report._yearly_rows(report)[0]
    yearly_page = next(page for page in pages if 'Yearly returns' in [text.get_text() for text in page.texts])
    assert _row_of(yearly_page, year)[:3] == [year, holding, value]
    # The names of the strategies themselves stay under their own heading.
    assert 'Strategy' in _texts(pages)


def test_a_run_without_the_benchmark_has_one_portfolio_column(pages, storage):
    backtest_report.generate_pdf(_session(has_benchmark=False))

    assert 'Portfolio' in _texts(pages)
    assert 'Buy & Hold' not in _texts(pages)


def test_a_long_backtest_splits_its_yearly_returns_in_two_columns(pages, storage):
    backtest_report.generate_pdf(_session(days=9125))

    assert '2023' in _texts(pages) and '2047' in _texts(pages)
    _assert_fits_the_pages(pages)


def test_the_benchmark_appears_in_the_report(pages):
    session = _session(symbols=('BTC-USDT', 'ETH-USDT'))

    backtest_report.generate_pdf(session)

    texts = _texts(pages)
    holding = session.metrics_json['benchmark']['portfolio']
    assert 'Buy & Hold' in texts
    assert backtest_report._percent(holding['max_drawdown']) in texts
    assert backtest_report._number(holding['sharpe_ratio']) in texts
    assert f"Buy & Hold {backtest_report._number(holding['sharpe_ratio'])}" in texts
    assert any('equally between the 2 symbols' in text for text in texts)


def test_a_single_route_says_which_symbol_is_held(pages):
    backtest_report.generate_pdf(_session())

    assert any('whole starting balance in BTC-USDT' in text for text in _texts(pages))


def test_nothing_mentions_a_benchmark_that_didnt_run(pages):
    backtest_report.generate_pdf(_session(has_benchmark=False))

    assert not any('Buy & Hold' in text for text in _texts(pages))


def test_the_report_lists_every_route_across_pages(pages):
    symbols = tuple(f'S{i}-USDT' for i in range(100))

    data = backtest_report.generate_pdf(_session(symbols=symbols))

    texts = _texts(pages)
    assert all(symbol in texts for symbol in symbols)
    # the four core pages and three of routes: 44, 44 and 12
    _assert_valid(data, 7)
    assert 'Page 7 of 7' in texts


def test_one_route_has_no_routes_table(pages):
    backtest_report.generate_pdf(_session())

    assert 'Results by route' not in _texts(pages)


def test_a_route_shows_what_it_earned_and_its_own_buy_and_hold(pages):
    session = _session(symbols=('BTC-USDT', 'ETH-USDT'), trades=4)
    session.trades_json = [
        {'symbol': 'BTC-USDT', 'PNL': 30.0, 'PNL_percentage': 3.0, 'fee': 1.0, 'opened_at': START},
        {'symbol': 'BTC-USDT', 'PNL': -10.0, 'PNL_percentage': -1.0, 'fee': 1.0, 'opened_at': START},
        {'symbol': 'ETH-USDT', 'PNL': 5.0, 'PNL_percentage': 0.5, 'fee': 2.0, 'opened_at': START},
    ]

    rows = backtest_report._route_rows(backtest_report._load_report(session))

    holding = session.metrics_json['benchmark']['routes'][0]
    assert rows[0][:7] == ('BTC-USDT', '4h', 'TrendFollower', '2', '50.00%', '20.00', '2.00')
    assert rows[0][7] == backtest_report._percent(holding['net_profit_percentage'], signed=True)
    assert rows[1][3:7] == ('1', '100.00%', '5.00', '2.00')


def test_a_route_without_trades_or_a_benchmark_shows_as_such():
    session = _session(symbols=('BTC-USDT', 'ETH-USDT'), has_benchmark=False)
    session.trades_json = [t for t in session.trades_json if t['symbol'] == 'BTC-USDT']

    row = backtest_report._route_rows(backtest_report._load_report(session))[1]

    assert row[3:] == ('0', 'N/A', '0.00', '0.00', 'N/A', 'N/A')


def test_undefined_values_are_shown_as_such():
    assert backtest_report._number(None) == 'N/A'
    assert backtest_report._number(float('nan')) == 'N/A'
    assert backtest_report._number(float('inf')) == '∞'
    assert backtest_report._number(float('-inf')) == '-∞'
    assert backtest_report._percent(None) == 'N/A'
    assert backtest_report._ratio_percent(None) == 'N/A'
    assert backtest_report._ratio_percent(0.5) == '50.00%'
    assert backtest_report._duration(None) == 'N/A'
    assert backtest_report._whole(float('nan')) == 'N/A'


def test_numbers_are_readable():
    assert backtest_report._number(1234567.891) == '1,234,567.89'
    assert backtest_report._percent(12.345, signed=True) == '+12.35%'
    assert backtest_report._percent(-12.345, signed=True) == '-12.35%'
    assert backtest_report._days(45) == '45 days'
    assert backtest_report._duration(30) == '30s'
    assert backtest_report._duration(5400) == '1h 30m'
    assert backtest_report._duration(3 * 86400 + 7200) == '3d 2h'


def test_a_year_compounds_its_months():
    balances = [100, 110, 121]
    series = backtest_report._Series('Portfolio', [], np.array(balances, dtype=float), [
        1_675_209_660_000,  # 2023-02-01 00:01, closing January
        1_677_628_860_000,  # 2023-03-01 00:01, closing February
        1_680_307_260_000,  # 2023-04-01 00:01, closing March
    ])

    assert series.monthly_returns == pytest.approx({(2023, 2): 10.0, (2023, 3): 10.0})
    assert series.yearly_returns == pytest.approx({2023: 21.0})


def test_worst_drawdowns_show_an_open_one_as_not_recovered():
    series = backtest_report._Series(
        'Portfolio', [backtest_report.datetime(2023, 1, day) for day in range(1, 6)],
        np.array([100, 80, 100, 90, 85], dtype=float), [],
    )

    rows = backtest_report._worst_drawdown_rows(series)

    assert rows[0] == ('1', '2023-01-01', '2023-01-01', '2023-01-02', '-20.00%', '1 day')
    assert rows[1][3] == 'Not recovered'
    assert rows[1][4] == '-15.00%'


def test_the_longest_drawdown_agrees_with_max_underwater_period():
    # regression: an open drawdown read a day shorter than Max Underwater Period
    timestamps = [START + i * DAY_MS + 60_000 for i in range(8)]
    balances = [100.0, 110.0, 105.0, 104.0, 103.0, 102.0, 101.0, 100.0]
    dates = [backtest_report.datetime.fromtimestamp(t / 1000, backtest_report.timezone.utc).replace(tzinfo=None) for t in timestamps]

    rows = backtest_report._worst_drawdown_rows(backtest_report._Series('Portfolio', dates, np.array(balances), timestamps))

    expected = metrics.calculate_max_underwater_period(balances, timestamps)
    assert rows[0][5] == f'{expected} days'


def test_drawdown_dates_are_the_days_they_measure():
    # regression: a balance sampled just after midnight was dated the day after it measured
    timestamps = [START + i * DAY_MS + 60_000 for i in range(4)]
    dates = [backtest_report.datetime.fromtimestamp(t / 1000, backtest_report.timezone.utc).replace(tzinfo=None) for t in timestamps]

    rows = backtest_report._worst_drawdown_rows(backtest_report._Series('Portfolio', dates, np.array([100.0, 90.0, 95.0, 100.0]), timestamps))

    assert rows[0][1:4] == ('2023-01-01', '2023-01-01', '2023-01-03')


def test_long_numbers_shrink_instead_of_losing_digits(pages):
    # regression: table cells cut numbers the way they cut names, turning +12,345.67% into +12,345.6…
    session = _session(symbols=('BTC-USDT', 'ETH-USDT'), trades=4)
    session.trades_json[0]['fee'] = 1_234_567.89
    session.metrics_json['benchmark']['routes'][0]['net_profit_percentage'] = 12_345.67

    backtest_report.generate_pdf(session)

    assert '1,234,568.39' in _texts(pages) or any(text.startswith('1,234,5') and '…' not in text for text in _texts(pages))
    assert '+12,345.67%' in _texts(pages)
    assert not [text for text in _texts(pages) if '…' in text and any(c.isdigit() for c in text)]
    _assert_fits_the_pages(pages)


def test_a_day_is_one_day():
    assert backtest_report._days(1) == '1 day'
    assert backtest_report._days(2) == '2 days'
    assert backtest_report._days(0) == '0 days'


def test_a_side_that_never_traded_has_no_win_rate():
    rows = dict(backtest_report._trading_rows({'win_rate_longs': 0.5, 'win_rate_shorts': 0, 'longs_count': 4, 'shorts_count': 0}))

    assert rows['Win rate longs'] == '50.00%'
    assert rows['Win rate shorts'] == 'N/A'


def test_a_strategy_without_a_dna_has_no_empty_row(pages):
    backtest_report.generate_pdf(_session(hyperparameters=[['DNA', ''], ['fast', 10], ['gone', None]]))

    assert 'DNA' not in _texts(pages) and 'gone' not in _texts(pages)
    assert 'fast' in _texts(pages)


def test_the_tiles_share_one_font_size(pages):
    backtest_report.generate_pdf(_session(metric_changes={'net_profit_percentage': 123_456.78}))

    labels = ('+123,456.78%', '+25.00%', '-12.50%', '1.25')
    sizes = {text.get_fontsize() for text in pages[0].texts if text.get_text() in labels}
    assert len(sizes) == 1


def test_cumulative_ticks_read_as_returns():
    assert charts._percent_tick(2.0, 0) == '+100%'
    assert charts._percent_tick(0.5, 0) == '-50%'
    assert charts._percent_tick(1.0, 0) == '0%'
    assert charts._percent_tick(0.9962, 2) == '-0.38%'
    # regression: small moves read -0% on every tick
    assert charts._percent_tick(0.9999, 0) == '0%'


def test_the_dark_page_is_the_background_of_the_dark_charts():
    assert backtest_report.DARK_COLORS.page == charts._THEMES['dark']['fig_facecolor']


def test_a_drawn_chart_isnt_called_log_scaled_when_it_may_not_be(pages):
    backtest_report.generate_pdf(_session())

    assert 'Cumulative Returns vs Benchmark' in _texts(pages)
    assert 'Cumulative Returns vs Benchmark (Log Scaled)' not in _texts(pages)


def test_a_drawn_legend_stays_inside_its_chart(pages):
    backtest_report.generate_pdf(_session(symbols=('BTC-USDT', 'ETH-USDT', 'SOL-USDT', 'XRP-USDT')))

    FigureCanvasAgg(pages[0]).draw()
    axes = next(axes for axes in pages[0].axes if axes.axison)
    box, frame = axes.get_legend().get_window_extent(), axes.get_window_extent()
    assert frame.x0 <= box.x0 and box.x1 <= frame.x1 and frame.y0 <= box.y0 and box.y1 <= frame.y1
    assert axes.get_legend().get_texts()[0].get_text() == 'Portfolio'


def test_long_text_in_a_table_is_cut_and_stays_readable(pages):
    # regression: right-aligned text shrank like a number, down to an unreadable size
    strategy = 'AVeryLongStrategyNameThatKeepsGoing' * 2
    form = {
        'routes': [{'symbol': 'BTC-USDT', 'timeframe': timeframe, 'strategy': strategy} for timeframe in ('1m', '3m', '5m', '15m', '30m', '45m', '1h', '2h', '3h', '4h', '6h', '8h', '12h', '1D')],
    }

    backtest_report.generate_pdf(_session(form=form, title='Title', strategies=[strategy]))

    setup = [text for text in pages[0].texts if text.get_text().endswith('…')]
    assert len(setup) == 2
    assert all(text.get_fontsize() == 7.5 for text in setup)


def test_only_what_is_a_number_counts_as_one():
    for value in ('1,234.56', '+12.34%', '-5%', '45 days', '1 day', '0', '1,538,311.72', '42.60 (0.43%)', '-8.49 (-0.08%)'):
        assert backtest_report.NUMBER_PATTERN.fullmatch(value), value
    for value in ('1m, 5m, 15m', 'GoldenCross', '2023-01-01 to 2024-12-31', 'N/A', '5x cross'):
        assert not backtest_report.NUMBER_PATTERN.fullmatch(value), value


def test_data_routes_share_one_size_and_keep_their_symbols_whole(pages):
    # regression: lines shrank one by one, and a symbol could split at its hyphen
    data_routes = [{'symbol': f'WWWWWWWW{i}-USDT', 'timeframe': '1D'} for i in range(14)]

    backtest_report.generate_pdf(_session(data_routes=data_routes))

    lines = [text for figure in pages for text in figure.texts if 'WWWWWWWW' in text.get_text()]
    assert len({text.get_fontsize() for text in lines}) == 1
    assert not [text for text in lines if text.get_text().rstrip().endswith('-')]
    _assert_fits_the_pages(pages)


def test_notes_with_nothing_in_them_have_no_heading(pages):
    backtest_report.generate_pdf(_session(notes='   \n  '))

    assert 'Notes' not in _texts(pages)


def test_a_missing_log_chart_doesnt_repeat_the_chart_above_it(pages, storage):
    _save_photos(storage, LIGHT_PHOTO)
    (storage / f'{SESSION_ID}_cumulative_returns.png').unlink()

    backtest_report.generate_pdf(_session())

    assert _texts(pages).count('Cumulative Returns vs Benchmark') == 1


def test_a_section_too_tall_for_a_page_cant_hang_the_report(monkeypatch):
    monkeypatch.setattr(backtest_report, 'MAX_NOTE_LINES', 500)

    assert backtest_report.generate_pdf(_session(notes='\n'.join(f'Line {i}.' for i in range(200)))).startswith(b'%PDF')


def test_all_the_details_at_their_limits_flow_onto_pages(pages):
    # regression: the longest hyperparameters and data routes pushed the notes onto the footer
    notes = '\n'.join(f'Note number {i}.' for i in range(80))
    session = _session(hyperparameters=[[f'parameter_{i}', i] for i in range(200)], data_routes=[{'symbol': 'BTC-USDT', 'timeframe': '1D'}] * 300, notes=notes)

    backtest_report.generate_pdf(session)

    texts = _texts(pages)
    assert 'Hyperparameters' in texts and 'Data routes' in texts and 'Notes' in texts
    assert 'Note number 38.' in texts
    assert 'And 161 more hyperparameters.' in texts and 'And 41 more lines of notes.' in texts
    _assert_fits_the_pages(pages)


def test_two_columns_of_years_leave_room_for_what_follows(pages):
    # regression: an odd number of years left the next heading on top of the last row
    backtest_report.generate_pdf(_session(days=6200, hyperparameters=[['fast', 10]]))

    _assert_fits_the_pages(pages)


def test_a_balance_that_never_fell_has_no_drawdowns(pages):
    backtest_report.generate_pdf(_session(balances=np.linspace(10_000, 50_000, 200)))

    assert 'The balance never fell below a previous high.' in _texts(pages)


def test_a_benchmark_shorter_than_the_strategy_still_works(pages):
    session = _session()
    session.equity_curve_json[1]['data'] = session.equity_curve_json[1]['data'][:20]

    _assert_valid(backtest_report.generate_pdf(session))
    _assert_fits_the_pages(pages)


def test_a_benchmark_with_one_candle_still_works(pages):
    session = _session()
    session.equity_curve_json[1]['data'] = session.equity_curve_json[1]['data'][:1]
    session.metrics_json['benchmark'] = benchmark.calculate_metrics(session.equity_curve_json)

    _assert_valid(backtest_report.generate_pdf(session))
    assert 'N/A' in _texts(pages)


def test_long_values_stay_inside_their_tiles(pages):
    backtest_report.generate_pdf(_session(metric_changes={'net_profit_percentage': 1e15, 'annual_return': -1e12, 'total': 123_456_789}))

    _assert_fits_the_pages(pages)
    tile_left, tile_width = 0.0, (backtest_report.CONTENT_WIDTH - 0.4) / 6
    summary = pages[0]
    renderer = FigureCanvasAgg(summary).get_renderer()
    value = next(text for text in summary.texts if text.get_text().startswith('+1,000,000,000,000,000'))
    box = value.get_window_extent(renderer)
    assert box.x1 / summary.dpi <= backtest_report.MARGIN + tile_left + tile_width


@pytest.mark.parametrize('value, spread, signed, expected', [
    (120.0, 400, True, '+120%'),
    (1234.0, 4000, False, '1,234%'),
    (-2.5, 8, False, '-2.5%'),
    (-0.38, 0.4, False, '-0.38%'),
    (0.25, 0.4, True, '+0.25%'),
    (0.0, 400, True, '0%'),
    # just below the shown precision, where it would otherwise read -0.00%
    (-0.001, 0.4, False, '0%'),
])
def test_percent_labels_show_what_their_axis_needs(value, spread, signed, expected):
    assert backtest_report._percent_label(value, spread, signed=signed) == expected


def _chart_labeled(label: str, figures: list):
    return next(axes for figure in figures for axes in figure.axes if axes.get_xlabel().startswith(label))


def test_a_tiny_move_still_has_readable_axes(pages):
    # regression: a one-day run that lost 0.38% labeled every tick of its axes 0%
    balances = np.linspace(10_000, 9_962, 2)

    backtest_report.generate_pdf(_session(balances=balances, trades=2))

    FigureCanvasAgg(pages[0]).draw()
    FigureCanvasAgg(pages[2]).draw()
    for axes in [axes for page in (pages[0], pages[2]) for axes in page.axes if axes.axison and axes.lines]:
        labels = [tick.get_text() for tick in axes.get_yticklabels() if tick.get_text()]
        assert len(set(labels)) == len(labels), labels


def test_a_few_huge_trades_dont_flatten_the_distribution(pages):
    session = _session(trades=200)
    session.trades_json[0]['PNL_percentage'] = 15_000.0
    session.trades_json[1]['PNL_percentage'] = -900.0

    backtest_report.generate_pdf(session)

    distribution = _chart_labeled('PnL per trade', pages)
    assert 'outliers grouped at the edges' in distribution.get_xlabel()
    assert distribution.get_xlim()[1] < 1_000
    # the mean still counts them, even though they are drawn at the edges
    expected = np.mean([trade['PNL_percentage'] for trade in session.trades_json])
    assert f'Mean {expected:+,.2f}%' in [text.get_text() for text in distribution.get_legend().get_texts()]


def test_a_normal_distribution_keeps_its_real_range(pages):
    backtest_report.generate_pdf(_session(trades=200))

    assert 'outliers' not in _chart_labeled('PnL per trade', pages).get_xlabel()


def test_trades_that_all_returned_the_same_still_work(pages):
    session = _session(trades=10)
    for trade in session.trades_json:
        trade['PNL_percentage'] = 2.5

    _assert_valid(backtest_report.generate_pdf(session))


def test_a_market_that_closes_on_weekends_still_works(pages):
    days = [i for i in range(400) if (i + 6) % 7 < 5]
    timestamps = [START + day * DAY_MS for day in days]
    balances = _walk(len(days), 3)
    session = _session(balances=balances)
    session.equity_curve_json = [_curve('Portfolio', balances, timestamps=timestamps), _curve('AAPL-USD', _walk(len(days), 4), timestamps=timestamps)]
    session.metrics_json['annualization'] = 252
    session.metrics_json['benchmark'] = benchmark.calculate_metrics(session.equity_curve_json)

    _assert_valid(backtest_report.generate_pdf(session))
    _assert_fits_the_pages(pages)


# Windows can't switch the process's timezone, as time.tzset() only exists on Unix.
@pytest.mark.skipif(not hasattr(time, 'tzset'), reason='needs time.tzset()')
def test_a_report_is_the_same_in_every_timezone(pages):
    session = _session()
    original = os.environ.get('TZ')

    try:
        tables = []
        for timezone in ('UTC', 'Pacific/Auckland', 'America/Los_Angeles'):
            os.environ['TZ'] = timezone
            time.tzset()
            pages.clear()
            backtest_report.generate_pdf(session)
            tables.append(_texts(pages))
    finally:
        if original is None:
            os.environ.pop('TZ', None)
        else:
            os.environ['TZ'] = original
        time.tzset()

    assert tables[0] == tables[1] == tables[2]


def test_reports_can_be_generated_at_the_same_time():
    sessions = [_session(symbols=tuple(f'S{i}-USDT' for i in range(i + 1))) for i in range(6)]

    with ThreadPoolExecutor(max_workers=6) as executor:
        reports = list(executor.map(backtest_report.generate_pdf, sessions))

    for data in reports:
        _assert_valid(data)


def test_generating_a_report_leaves_no_trace_in_the_process():
    settings = dict(matplotlib.rcParams)
    figures = plt.get_fignums()

    backtest_report.generate_pdf(_session())

    assert plt.get_fignums() == figures
    assert matplotlib.rcParams['pdf.fonttype'] == settings['pdf.fonttype']
    assert matplotlib.rcParams['text.parse_math'] == settings['text.parse_math']
    assert matplotlib.rcParams['text.color'] == settings['text.color']


def test_the_report_shows_the_serenity_index_of_both_sides(pages):
    session = _session()

    backtest_report.generate_pdf(session)

    texts = _texts(pages)
    assert 'Serenity index' in texts
    assert backtest_report._number(session.metrics_json['serenity_index']) in texts
    assert backtest_report._number(session.metrics_json['benchmark']['portfolio']['serenity_index']) in texts


def test_the_report_keeps_its_text_as_text():
    data = backtest_report.generate_pdf(_session())

    # type 42 embeds a real font, where the default would turn text into drawings
    assert b'/FontFile2' in data


def test_availability_needs_balances_and_trades():
    assert backtest_report.is_available(_session())
    assert not backtest_report.is_available(SimpleNamespace(equity_curve_json=[], metrics_json={'total': 3}))
    assert not backtest_report.is_available(SimpleNamespace(equity_curve_json=[{}], metrics_json={'total': 0}))
    assert not backtest_report.is_available(SimpleNamespace(equity_curve_json=[{}], metrics_json=None))
    assert not backtest_report.is_available(SimpleNamespace(equity_curve_json=[], metrics_json=None))


@pytest.mark.parametrize('title, expected', [
    ('Trend Follower', 'jesse-backtest-trend-follower-2023-01-01-2024-02-05.pdf'),
    (None, 'jesse-backtest-trendfollower-2023-01-01-2024-02-05.pdf'),
    ('استراتژی 趋势', 'jesse-backtest-2023-01-01-2024-02-05.pdf'),
    ('a/b\\c"d\r\nX-Header: 1', 'jesse-backtest-a-b-c-d-x-header-1-2023-01-01-2024-02-05.pdf'),
])
def test_the_file_name_is_safe_for_a_header(title, expected):
    name = backtest_report.file_name(_session(title=title))

    assert name == expected
    name.encode('ascii')


def test_a_session_with_nothing_to_name_it_uses_its_id():
    session = _session(title=None, form={})

    assert backtest_report.file_name(session) == 'jesse-backtest-abcd1234.pdf'


def test_a_long_title_keeps_the_file_name_short():
    assert len(backtest_report.file_name(_session(title='long ' * 100))) < 110


class _StoredSession(BacktestSession):
    """The model's real JSON properties, without a database behind them."""

    def __init__(self, **values) -> None:
        super().__init__(attributes={'id': uuid4(), 'status': 'finished', 'created_at': 1, 'updated_at': 2, **values})

    class Meta:
        database = None


def _stored(session: SimpleNamespace) -> _StoredSession:
    return _StoredSession(
        title=session.title, description=session.description, metrics=json.dumps(session.metrics_json),
        equity_curve=json.dumps(session.equity_curve_json), trades=json.dumps(session.trades_json),
        hyperparameters=json.dumps(session.hyperparameters_json), state=json.dumps(session.state_json),
    )


@pytest.fixture
def client(monkeypatch) -> TestClient:
    monkeypatch.setitem(auth.ENV_VALUES, 'PASSWORD', PASSWORD)
    app = FastAPI()

    @app.exception_handler(auth.InvalidAuthError)
    async def invalid_auth_handler(_request, _exc):
        return auth.unauthorized_response()

    app.include_router(backtest_controller.router)
    return TestClient(app)


def _serve(monkeypatch, session) -> None:
    monkeypatch.setattr(backtest_controller, 'get_backtest_session_by_id_from_db', lambda session_id: session)


def test_the_endpoint_downloads_the_report(client, monkeypatch):
    session = _stored(_session())
    _serve(monkeypatch, session)

    response = client.get(f'/backtest/sessions/{session.id}/report', params={'token': AUTHORIZATION})

    assert response.status_code == 200
    assert response.headers['content-type'] == 'application/pdf'
    assert response.headers['content-disposition'] == 'attachment; filename="jesse-backtest-trend-follower-2023-01-01-2024-02-05.pdf"'
    _assert_valid(response.content)


def test_the_endpoint_accepts_the_authorization_header(client, monkeypatch):
    session = _stored(_session())
    _serve(monkeypatch, session)

    response = client.get(f'/backtest/sessions/{session.id}/report', headers={'Authorization': AUTHORIZATION})

    assert response.status_code == 200


def test_a_title_in_another_script_downloads_too(client, monkeypatch):
    session = _stored(_session(title='استراتژی 趋势'))
    _serve(monkeypatch, session)

    assert client.get(f'/backtest/sessions/{session.id}/report', params={'token': AUTHORIZATION}).status_code == 200


def test_the_endpoint_needs_authentication(client, monkeypatch):
    session = _stored(_session())
    _serve(monkeypatch, session)

    assert client.get(f'/backtest/sessions/{session.id}/report').status_code == 401
    assert client.get(f'/backtest/sessions/{session.id}/report', params={'token': 'wrong'}).status_code == 401


def test_an_unknown_session_is_not_found(client, monkeypatch):
    _serve(monkeypatch, None)

    response = client.get(f'/backtest/sessions/{uuid4()}/report', params={'token': AUTHORIZATION})

    assert response.status_code == 404
    assert 'not found' in response.json()['error']


def test_a_malformed_id_is_rejected(client):
    assert client.get('/backtest/sessions/not-a-uuid/report', params={'token': AUTHORIZATION}).status_code == 422


def test_a_session_without_a_report_explains_itself(client, monkeypatch):
    session = _stored(_session())
    session.equity_curve = None
    _serve(monkeypatch, session)

    response = client.get(f'/backtest/sessions/{session.id}/report', params={'token': AUTHORIZATION})

    assert response.status_code == 404
    assert 'Export PDF' in response.json()['error']


def test_a_session_without_trades_has_no_report(client, monkeypatch):
    session = _stored(_session())
    session.metrics = json.dumps({'total': 0})
    _serve(monkeypatch, session)

    assert client.get(f'/backtest/sessions/{session.id}/report', params={'token': AUTHORIZATION}).status_code == 404


def _export(client, session, **body):
    return client.post(f'/backtest/sessions/{session.id}/report/export-to-project', json=body, headers={'Authorization': AUTHORIZATION})


def test_a_report_can_be_written_into_the_project(client, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    session = _stored(_session())
    _serve(monkeypatch, session)

    response = _export(client, session)

    assert response.status_code == 201
    path = response.json()['path']
    assert path.startswith('research_scripts/backtest_reports/jesse-backtest-trend-follower-')
    assert path.endswith(f'-{str(session.id)[:8]}.pdf')
    assert response.json()['overwritten'] is False
    _assert_valid((tmp_path / path).read_bytes())


def test_an_exported_report_is_only_replaced_when_asked(client, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    session = _stored(_session())
    _serve(monkeypatch, session)
    built = []
    monkeypatch.setattr(backtest_controller.backtest_report, 'generate_pdf', lambda session: built.append(session) or b'%PDF-1')

    assert _export(client, session, path='research_scripts/mine.pdf').status_code == 201
    refused = _export(client, session, path='research_scripts/mine.pdf')
    replaced = _export(client, session, path='research_scripts/mine.pdf', overwrite=True)

    assert refused.status_code == 409
    # A file that can't be replaced is refused before the report is built.
    assert len(built) == 2
    assert replaced.status_code == 201
    assert replaced.json()['overwritten'] is True


@pytest.mark.parametrize('path', ['strategies/Mine/report.pdf', 'research_scripts/report.txt', '../report.pdf', '/tmp/report.pdf'])
def test_a_report_stays_a_pdf_under_research_scripts(client, monkeypatch, tmp_path, path):
    monkeypatch.chdir(tmp_path)
    session = _stored(_session())
    _serve(monkeypatch, session)

    response = _export(client, session, path=path)

    assert response.status_code == 400
    assert response.json()['error_type'] == 'invalid_path'
    assert not (tmp_path / 'research_scripts').exists()


def test_exporting_a_session_without_a_report_says_how_to_get_one(client, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    session = _stored(_session())
    session.equity_curve = None
    _serve(monkeypatch, session)

    response = _export(client, session)

    assert response.status_code == 404
    assert response.json()['error_type'] == 'no_report'
    assert 'Export PDF' in response.json()['error']


def test_exporting_an_unknown_session_is_not_found(client, monkeypatch):
    monkeypatch.setattr(backtest_controller, 'get_backtest_session_by_id_from_db', lambda session_id: None)

    response = client.post(f'/backtest/sessions/{uuid4()}/report/export-to-project', json={}, headers={'Authorization': AUTHORIZATION})

    assert response.status_code == 404
    assert response.json()['error_type'] == 'not_found'


def test_exporting_needs_authentication(client, monkeypatch):
    monkeypatch.setattr(backtest_controller, 'get_backtest_session_by_id_from_db', lambda session_id: None)

    assert client.post(f'/backtest/sessions/{uuid4()}/report/export-to-project', json={}).status_code == 401


def test_a_session_tells_the_dashboard_whether_it_has_a_report():
    session = _stored(_session())
    assert transformers.get_backtest_session_for_load_more(session)['has_report'] is True

    session.equity_curve = None
    assert transformers.get_backtest_session_for_load_more(session)['has_report'] is False


def test_the_dashboard_gets_benchmark_metrics_it_can_read():
    plain = _session(balances=np.full(200, 10_000.0))
    plain.metrics_json['benchmark']['portfolio']['sortino_ratio'] = float('inf')
    plain.metrics_json['benchmark']['portfolio']['omega_ratio'] = float('nan')

    payload = transformers.get_backtest_session_for_load_more(_stored(plain))

    holding = payload['metrics']['benchmark']['portfolio']
    assert holding['sortino_ratio'] is None
    assert holding['omega_ratio'] is None
    json.dumps(payload, allow_nan=False)
