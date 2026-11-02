"""
The PDF report of a finished backtest. Its charts are the images the backtest saved for the
dashboard, and everything else comes from what the session stored, so it can be generated at
any time. A run on a research runner leaves its images on that machine, so charts without one
are drawn from the session's data instead.
"""
import math
import os
import re
import textwrap
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from io import BytesIO
from typing import Callable

import matplotlib
import matplotlib.dates as mdates
import matplotlib.image as mpimg
import matplotlib.ticker as mticker
import numpy as np
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm
from matplotlib.figure import Figure
from matplotlib.font_manager import FontProperties
from matplotlib.lines import Line2D
from matplotlib.patches import FancyBboxPatch
from matplotlib.textpath import text_to_path

from jesse.services import benchmark as benchmark_service
from jesse.services import metrics as stats
from jesse.services.charts import (
    BACKTEST_CHART_NAMES, _compute_drawdown_series, _compute_entry_timing, _find_worst_drawdown_periods,
)
from jesse.version import __version__

# A4 in inches, the size most reports get printed at.
PAGE_WIDTH, PAGE_HEIGHT = 8.27, 11.69
MARGIN = 0.55
CONTENT_WIDTH = PAGE_WIDTH - 2 * MARGIN
HEADER_HEIGHT = 0.72
FOOTER_HEIGHT = 0.5
CONTENT_BOTTOM = PAGE_HEIGHT - FOOTER_HEIGHT
LOGO_HEIGHT = 0.36
CELL_PADDING = 0.08
# Numbers as tables print them, such as 1,234.56, +12.34%, 45 days or 42.60 (0.43%).
NUMBER_PATTERN = re.compile(r'[-+]?[\d,]+(\.\d+)?(%| days?)?( \([-+]?[\d,]+(\.\d+)?%\))?')
TILE_PADDING = 0.09
# Above a section's heading and between it and what it heads.
SECTION_GAP = 0.3
HEADING_GAP = 0.17
SECTION_HEIGHT = SECTION_GAP + HEADING_GAP
TABLE_ROW_HEIGHT = 0.21
# The table rows of room that a section's heading and its table's title row take, rounded up.
SECTION_ROWS = 4
# Room for the tick labels that sit outside of a chart's axes.
CHART_LEFT_GUTTER = 0.5
CHART_BOTTOM_GUTTER = 0.3
# The room each chart gets. A saved image that is wider than this allows keeps its proportions.
WIDE_CHART_HEIGHT = 2.85
UNDERWATER_HEIGHT = 2.25
DISTRIBUTION_HEIGHT = 2.85
ENTRY_TIMING_HEIGHT = 2.65
# What the drawdown charts leave of their page. A heatmap taller than this gets its own page,
# as shrinking the years of a long backtest would make its numbers unreadable.
HEATMAP_ROOM = CONTENT_BOTTOM - HEADER_HEIGHT - 3 * SECTION_HEIGHT - WIDE_CHART_HEIGHT - UNDERWATER_HEIGHT
FULL_PAGE_CHART_HEIGHT = CONTENT_BOTTOM - HEADER_HEIGHT - SECTION_HEIGHT

PORTFOLIO_LABEL = 'Portfolio'
STRATEGY_COLOR = '#4F46E5'
BENCHMARK_COLOR = '#D97706'
POSITIVE_COLOR = '#15803D'
NEGATIVE_COLOR = '#DC2626'
# Individual symbols, drawn thin behind the strategy and the benchmark.
SYMBOL_COLORS = ['#0891B2', '#DB2777', '#65A30D', '#7C3AED', '#92400E']


@dataclass(frozen=True)
class _Colors:
    page: str
    surface: str
    hairline: str
    ink: str
    muted: str
    logo: str


# Pages take the theme of the saved charts, as dark images on a white page would look pasted in.
# The page is each theme's chart background from services/charts.py, so charts sit on it seamlessly.
LIGHT_COLORS = _Colors(page='#FFFFFF', surface='#F3F4F6', hairline='#E5E7EB', ink='#111827', muted='#6B7280', logo='logo-light.png')
DARK_COLORS = _Colors(page='#333333', surface='#404040', hairline='#4A4A4A', ink='#F6F7EE', muted='#B4B8BF', logo='logo-dark.png')
LOGO_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'report_assets')

# More routes than these would turn the cumulative chart into noise, and the routes table has
# them all anyway.
MAX_SYMBOL_LINES = len(SYMBOL_COLORS)
# What fits on a page at the height of a table row.
ROUTE_ROWS_PER_PAGE = 44
DETAIL_ROWS_PER_PAGE = 44
# The longest a detail can be. Each one fits a page, and what's cut is said to be.
MAX_HYPERPARAMETER_ROWS = 39
MAX_NOTE_LINES = 39
MAX_DATA_ROUTE_LINES = 6
# Beyond this a title on one line gets too small to read.
MAX_TITLE_LENGTH = 90
MAX_HISTOGRAM_BINS = 40
# How many interquartile ranges beyond the quartiles a value is an outlier. Quartiles aren't
# moved by a fat tail, and at this reach a normal distribution has no outliers to speak of.
OUTLIER_QUARTILE_RANGES = 3
# Characters that fit across the page in the small print.
SMALL_PRINT_LINE_LENGTH = 155
# DejaVu Sans averages about this share of the font size per character.
AVERAGE_CHARACTER_WIDTH = 0.56

RC_PARAMS = {
    # Embeds real fonts so the text stays selectable and searchable.
    'pdf.fonttype': 42,
    'font.family': 'DejaVu Sans',
    # Titles and notes are free text, where a "$" must stay a dollar sign rather than open math.
    'text.parse_math': False,
}

# rcParams are global to the process, and requests are served from a thread pool.
_generation_lock = threading.Lock()


@dataclass
class _Series:
    """One balance curve: the portfolio's, or a buy-and-hold one."""
    name: str
    dates: list
    balances: np.ndarray
    timestamps: list

    @property
    def multipliers(self) -> np.ndarray:
        return self.balances / self.balances[0] if self.balances[0] else np.ones(len(self.balances))

    @property
    def monthly_returns(self) -> dict:
        return stats.monthly_returns(self.balances.tolist(), self.timestamps)

    @property
    def yearly_returns(self) -> dict:
        years = {}
        for (year, _), monthly_return in self.monthly_returns.items():
            years[year] = years.get(year, 1.0) * (1 + monthly_return / 100)
        return {year: (growth - 1) * 100 for year, growth in years.items()}


@dataclass
class _Report:
    title: str
    subject: str
    form: dict
    exchange_config: dict
    routes: list
    metrics: dict
    benchmark_metrics: dict | None
    strategy: _Series
    buy_and_hold: _Series | None
    symbols: list
    trades: list
    hyperparameters: list
    notes: str
    photos: dict
    colors: _Colors
    logo: np.ndarray

    @property
    def period(self) -> str:
        start, finish = self.form.get('start_date'), self.form.get('finish_date')
        return f'{start} to {finish}' if start and finish else _date(self.strategy.dates[0]) + ' to ' + _date(self.strategy.dates[-1])


def is_available(session) -> bool:
    """Reports need the stored balances, kept by backtests run with Export PDF that made a trade."""
    return bool(session.equity_curve_json) and bool((session.metrics_json or {}).get('total'))


def file_name(session) -> str:
    """An ASCII name, as the Content-Disposition header can't carry a free-text title."""
    form = (session.state_json or {}).get('form') or {}
    parts = [session.title or _strategies_label(form.get('routes') or []), form.get('start_date'), form.get('finish_date')]
    slug = re.sub(r'[^a-z0-9]+', '-', ' '.join(str(part) for part in parts if part).lower()).strip('-')[:80]
    return f'jesse-backtest-{slug or str(session.id)[:8]}.pdf'


def generate_pdf(session) -> bytes:
    """Build the report of a finished backtest. Check is_available() first."""
    report = _load_report(session)
    pages = _plan_pages(report)
    buffer = BytesIO()

    colors = report.colors
    theme = {'text.color': colors.ink, 'xtick.color': colors.muted, 'ytick.color': colors.muted, 'axes.labelcolor': colors.muted}
    with _generation_lock, matplotlib.rc_context({**RC_PARAMS, **theme}):
        metadata = {'Title': f'Backtest report: {report.subject}', 'Author': 'Jesse', 'Creator': f'Jesse {__version__}'}
        with PdfPages(buffer, metadata=metadata) as pdf:
            for number, (title, draw) in enumerate(pages, start=1):
                page = _Page(report, title, number, len(pages))
                draw(report, page)
                pdf.savefig(page.figure)

    return buffer.getvalue()


def _load_report(session) -> _Report:
    curves = session.equity_curve_json
    metrics = session.metrics_json
    form = (session.state_json or {}).get('form') or {}
    routes = form.get('routes') or []
    benchmark_curves = curves[1:]
    combined = next((c for c in benchmark_curves if c['name'] == benchmark_service.BUY_AND_HOLD_NAME), None)
    symbol_curves = [c for c in benchmark_curves if c['name'] != benchmark_service.BUY_AND_HOLD_NAME]
    holding = combined or (symbol_curves[0] if symbol_curves else None)
    strategies = _strategies_label(routes)
    photos = _load_photos(session.id)
    colors = _colors_of(photos)

    return _Report(
        title=session.title or strategies or 'Backtest',
        subject=session.title or strategies or str(session.id)[:8],
        form=form,
        exchange_config=(form.get('config') or {}).get('exchange') or {},
        routes=routes,
        metrics=metrics,
        benchmark_metrics=metrics.get('benchmark'),
        strategy=_strategy_series(curves[0]),
        buy_and_hold=_benchmark_series(holding, benchmark_service.BUY_AND_HOLD_NAME) if holding else None,
        symbols=[_benchmark_series(c, c['name']) for c in symbol_curves],
        trades=session.trades_json or [],
        # A strategy without a DNA has an empty row for it.
        hyperparameters=[row for row in session.hyperparameters_json or [] if row[1] not in ('', None)],
        notes=(session.description or '').strip(),
        photos=photos,
        colors=colors,
        logo=mpimg.imread(os.path.join(LOGO_FOLDER, colors.logo)),
    )


def _load_photos(session_id) -> dict:
    """The chart images the backtest saved, by chart. One that can't be read counts as missing."""
    folder = os.path.abspath('storage/backtest-charts')
    photos = {}
    for name in BACKTEST_CHART_NAMES:
        path = os.path.join(folder, f'{session_id}_{name}.png')
        if os.path.exists(path):
            try:
                photos[name] = mpimg.imread(path)
            except (OSError, ValueError, SyntaxError):
                continue
    return photos


def _colors_of(photos: dict) -> _Colors:
    """Tell the theme a backtest's charts were saved in from their background."""
    if not photos:
        return LIGHT_COLORS
    corner = next(iter(photos.values()))[0, 0, :3]
    return DARK_COLORS if float(corner.mean()) < 0.5 else LIGHT_COLORS


def _strategy_series(curve: dict) -> _Series:
    return _curve_to_series(PORTFOLIO_LABEL, curve, [round(point['time'] * 1000) for point in curve['data']])


def _benchmark_series(curve: dict, name: str) -> _Series:
    return _curve_to_series(name, curve, benchmark_service.sample_timestamps(curve))


def _curve_to_series(name: str, curve: dict, timestamps: list) -> _Series:
    dates = [datetime.fromtimestamp(timestamp / 1000, timezone.utc).replace(tzinfo=None) for timestamp in timestamps]
    return _Series(name, dates, np.array([point['value'] for point in curve['data']], dtype=float), timestamps)


def _strategies_label(routes: list) -> str:
    names = list(dict.fromkeys(r.get('strategy') for r in routes if r.get('strategy')))
    if len(names) > 1:
        return f'{names[0]} + {len(names) - 1} more'
    return names[0] if names else ''


def _plan_pages(report: _Report) -> list:
    """List the pages up front, so that each one can say how many there are."""
    route_rows = _route_rows(report) if len(report.routes) > 1 else []
    details = _detail_sections(report)

    # What's short shares the metrics page, rather than leaving a page of its own mostly empty.
    room = _rows_left_on_metrics_page(report)
    extras = []
    if route_rows and len(route_rows) + SECTION_ROWS <= room:
        rows = route_rows
        room -= len(rows) + SECTION_ROWS
        route_rows = []
        extras.append(lambda r, page: _draw_routes(r, page, rows))
    if not route_rows:
        extras += _take_sections(details, room)

    heatmap_fits = _heatmap_height(report) <= HEATMAP_ROOM
    pages: list[tuple[str, Callable]] = [
        ('Summary', _draw_summary),
        ('Metrics', _combined(_draw_metrics, *extras)),
        ('Drawdowns and returns', lambda r, page: _draw_drawdowns(r, page, heatmap_fits)),
    ]
    if not heatmap_fits:
        pages.append(('Monthly returns', lambda r, page: _draw_heatmap(r, page, FULL_PAGE_CHART_HEIGHT)))
    pages.append(('Distributions and timing', lambda r, page: _draw_distributions(r, page, heatmap_fits)))

    chunks = [route_rows[i:i + ROUTE_ROWS_PER_PAGE] for i in range(0, len(route_rows), ROUTE_ROWS_PER_PAGE)]
    for chunk in chunks:
        sharing = _take_sections(details, ROUTE_ROWS_PER_PAGE - len(chunk) - SECTION_ROWS) if chunk is chunks[-1] else []
        pages.append(('Routes', _combined(lambda r, page, rows=chunk: _draw_routes(r, page, rows), *sharing)))

    while details:
        # A section taller than a page is placed anyway, or this would never end.
        pages.append(('Details', _combined(*(_take_sections(details, DETAIL_ROWS_PER_PAGE) or [details.pop(0)[1]]))))

    return pages


def _combined(*draws: Callable) -> Callable:
    """Draw several blocks on one page, one under the other."""
    def draw_all(report: _Report, page: '_Page') -> None:
        for draw in draws:
            draw(report, page)

    return draw_all


def _take_sections(sections: list, room: int) -> list:
    """Remove the sections that fit the room, in order, and return what draws them."""
    taken = []
    while sections and sections[0][0] <= room:
        rows, draw = sections.pop(0)
        room -= rows
        taken.append(draw)
    return taken


def _rows_left_on_metrics_page(report: _Report) -> int:
    """Lay the metrics page out once to see how many table rows of room it leaves."""
    page = _Page(report, '', 1, 1)
    _draw_metrics(report, page)
    return int((CONTENT_BOTTOM - page.y) / TABLE_ROW_HEIGHT)


class _Page:
    """A page laid out in inches from its top left corner, with a cursor for the next block."""

    def __init__(self, report: _Report, title: str, number: int, total: int) -> None:
        self.colors = report.colors
        self.figure = Figure(figsize=(PAGE_WIDTH, PAGE_HEIGHT), facecolor=self.colors.page)
        self.y = HEADER_HEIGHT

        logo_height, logo_width = report.logo.shape[:2]
        self.image(report.logo, 0, 0.13, LOGO_HEIGHT * logo_width / logo_height, LOGO_HEIGHT)
        self.text(0.46, 0.38, 'Jesse', size=12, weight='bold')
        self.text(CONTENT_WIDTH, 0.38, title, size=8.5, color=self.colors.muted, ha='right')
        self.line(0.58)
        footer = _truncate(f'{report.subject}  |  {report.period}', MAX_TITLE_LENGTH)
        self.text(0, CONTENT_BOTTOM + 0.2, footer, size=_fitted_size(footer, CONTENT_WIDTH - 1, 7), color=self.colors.muted)
        self.text(CONTENT_WIDTH, CONTENT_BOTTOM + 0.2, f'Page {number} of {total}', size=7, color=self.colors.muted, ha='right')

    def text(self, x: float, y: float, value: str, **kwargs) -> None:
        kwargs.setdefault('va', 'baseline')
        self.figure.text((MARGIN + x) / PAGE_WIDTH, 1 - y / PAGE_HEIGHT, value, **kwargs)

    def line(self, y: float, left: float = 0, width: float = CONTENT_WIDTH) -> None:
        position = 1 - y / PAGE_HEIGHT
        self.figure.add_artist(Line2D(
            [(MARGIN + left) / PAGE_WIDTH, (MARGIN + left + width) / PAGE_WIDTH], [position, position],
            color=self.colors.hairline, linewidth=0.6, transform=self.figure.transFigure,
        ))

    def section(self, title: str) -> None:
        self.y += SECTION_GAP
        self.text(0, self.y, title, size=10, weight='bold')
        self.y += HEADING_GAP

    def small_print(self, value: str) -> None:
        for line in textwrap.wrap(value, width=SMALL_PRINT_LINE_LENGTH):
            self.y += 0.14
            self.text(0, self.y, line, size=6.5, color=self.colors.muted)

    def image(self, image: np.ndarray, left: float, top: float, width: float, height: float) -> None:
        axes = self.figure.add_axes(((MARGIN + left) / PAGE_WIDTH, 1 - (top + height) / PAGE_HEIGHT, width / PAGE_WIDTH, height / PAGE_HEIGHT))
        # 'none' keeps the image's own pixels instead of resampling them.
        axes.imshow(image, interpolation='none', aspect='auto')
        axes.set_axis_off()

    def photo(self, image: np.ndarray, max_height: float) -> None:
        """Place a saved chart across the page, or narrower and centered if that would be too tall."""
        pixel_height, pixel_width = image.shape[:2]
        width = min(CONTENT_WIDTH, max_height * pixel_width / pixel_height)
        height = width * pixel_height / pixel_width
        self.image(image, (CONTENT_WIDTH - width) / 2, self.y, width, height)
        self.y += height

    def axes(self, height: float, left: float = 0, width: float = CONTENT_WIDTH):
        """Add a chart that fills the height, keeping room for its tick labels, and move below it."""
        axes = self.figure.add_axes((
            (MARGIN + left + CHART_LEFT_GUTTER) / PAGE_WIDTH,
            1 - (self.y + height - CHART_BOTTOM_GUTTER) / PAGE_HEIGHT,
            (width - CHART_LEFT_GUTTER) / PAGE_WIDTH,
            (height - CHART_BOTTOM_GUTTER) / PAGE_HEIGHT,
        ))
        self.y += height
        axes.set_facecolor(self.colors.page)
        axes.tick_params(colors=self.colors.muted, labelsize=7, length=2, width=0.5)
        axes.yaxis.grid(True, color=self.colors.hairline, linewidth=0.5)
        axes.set_axisbelow(True)
        for side in ('top', 'right'):
            axes.spines[side].set_visible(False)
        for side in ('left', 'bottom'):
            axes.spines[side].set_color(self.colors.hairline)
        return axes

    def tile(self, left: float, width: float, height: float, value_size: float, label: str, value: str, detail: str = '') -> None:
        self.figure.add_artist(FancyBboxPatch(
            ((MARGIN + left) / PAGE_WIDTH, 1 - (self.y + height) / PAGE_HEIGHT),
            width / PAGE_WIDTH, height / PAGE_HEIGHT,
            boxstyle='round,pad=0,rounding_size=0.006', facecolor=self.colors.surface, edgecolor='none',
            transform=self.figure.transFigure, mutation_aspect=PAGE_WIDTH / PAGE_HEIGHT,
        ))
        self.text(left + TILE_PADDING, self.y + 0.2, label, size=7, color=self.colors.muted)
        self.text(left + TILE_PADDING, self.y + 0.46, value, size=value_size, weight='bold')
        self.text(left + TILE_PADDING, self.y + 0.63, detail, size=_fitted_size(detail, width - 2 * TILE_PADDING, 6.5), color=self.colors.muted)


def _text_width(value: str, size: float) -> float:
    """The width of text in inches, measured in bold to be safe."""
    width, _, _ = text_to_path.get_text_width_height_descent(value, FontProperties(family='DejaVu Sans', weight='bold', size=size), False)
    return width / 72


def _fitted_size(value: str, width: float, size: float) -> float:
    """The font size that keeps text within a width in inches."""
    if not value:
        return size
    natural_width = _text_width(value, size)
    return size if natural_width <= width else size * width / natural_width


def _fitted_text(value, width: float, size: float) -> str:
    """Shorten text until it fits a width in inches."""
    value = str(value)
    # Even the widest letters are about twice the average, so most values can skip the measuring.
    if len(value) * size * AVERAGE_CHARACTER_WIDTH * 2 <= width * 72:
        return value
    if _text_width(value, size) <= width:
        return value
    while len(value) > 1 and _text_width(value + '…', size) > width:
        value = value[:-1]
    return value.rstrip() + '…'


def _truncate(value, max_characters: int) -> str:
    value = str(value)
    return value if len(value) <= max_characters else value[:max_characters - 1].rstrip() + '…'


def _date(date: datetime) -> str:
    return date.strftime('%Y-%m-%d')


def _is_defined(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and not math.isnan(value)


def _number(value, digits: int = 2, suffix: str = '', signed: bool = False) -> str:
    if not _is_defined(value):
        return 'N/A'
    if math.isinf(value):
        return '∞' if value > 0 else '-∞'
    return f'{value:{"+" if signed else ""},.{digits}f}{suffix}'


def _percent(value, signed: bool = False) -> str:
    return _number(value, suffix='%', signed=signed)


def _ratio_percent(value) -> str:
    """Win rates are stored as ratios."""
    return _percent(value * 100) if _is_defined(value) else 'N/A'


def _whole(value) -> str:
    return _number(value, digits=0)


def _days(value) -> str:
    return _number(value, digits=0, suffix=' day' if value == 1 else ' days')


def _duration(seconds) -> str:
    if not _is_defined(seconds) or math.isinf(seconds):
        return 'N/A'
    minutes = int(seconds // 60)
    days, minutes = divmod(minutes, 1440)
    hours, minutes = divmod(minutes, 60)
    parts = [f'{amount}{unit}' for amount, unit in ((days, 'd'), (hours, 'h'), (minutes, 'm')) if amount]
    return ' '.join(parts[:2]) or f'{seconds:.0f}s'


def _table(page: _Page, columns: list, rows: list, left: float = 0, width: float = CONTENT_WIDTH, row_height: float = TABLE_ROW_HEIGHT, size: float = 7.5) -> None:
    """
    Draw rows of text between hairlines. Columns are (title, share of the width, alignment).
    Values too long for their column are shortened, as text can't wrap inside a fixed row.
    """
    has_titles = any(title for title, _, _ in columns)
    y = page.y + (0.18 if has_titles else 0.06)
    x = left
    positions = []
    for title, share, align in columns:
        column_width = width * share
        positions.append((x + column_width if align == 'right' else x, align, column_width))
        if has_titles:
            page.text(positions[-1][0], y - 0.07, title, size=size - 0.5, color=page.colors.muted, ha=align)
        x += column_width
    page.line(y, left, width)

    for row in rows:
        y += row_height
        for value, (x_position, align, column_width) in zip(row, positions):
            cell_width = column_width - CELL_PADDING
            # A number shrinks to fit, as cutting one would change it. Text can be cut.
            if NUMBER_PATTERN.fullmatch(str(value)):
                page.text(x_position, y - 0.06, str(value), size=_fitted_size(str(value), cell_width, size), ha=align)
            else:
                page.text(x_position, y - 0.06, _fitted_text(value, cell_width, size), size=size, ha=align)
        page.line(y, left, width)

    page.y = y


def _show_message(axes, report: _Report, message: str) -> None:
    axes.set_xticks([])
    axes.set_yticks([])
    axes.text(0.5, 0.5, message, ha='center', va='center', transform=axes.transAxes, color=report.colors.muted, size=8)


def _format_dates(axes) -> None:
    locator = mdates.AutoDateLocator(minticks=3, maxticks=9)
    axes.xaxis.set_major_locator(locator)
    axes.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))
    axes.margins(x=0)


def _add_legend(axes, report: _Report) -> None:
    handles, labels = axes.get_legend_handles_labels()
    # 'best' finds the emptiest corner of the chart.
    # The legend leads with what matters most, whatever order the lines were drawn in.
    order = sorted(range(len(labels)), key=lambda i: (labels[i] != PORTFOLIO_LABEL, labels[i] != benchmark_service.BUY_AND_HOLD_NAME, i))
    axes.legend(
        [handles[i] for i in order], [labels[i] for i in order],
        fontsize=7, loc='best', facecolor=report.colors.page, edgecolor=report.colors.hairline, framealpha=0.85,
        ncol=min(len(labels), 3), handlelength=1.6, columnspacing=1.2,
    )


def _percent_label(value: float, spread: float, signed: bool = False) -> str:
    """Label a percentage with the decimals its axis needs: a run that moved 0.4% needs more than one that moved 400%."""
    decimals = 0 if spread >= 10 else 1 if spread >= 1 else 2
    if abs(value) < 0.5 * 10 ** -decimals:
        return '0%'
    return f'{value:{"+" if signed else ""},.{decimals}f}%'


def _plot_cumulative_returns(axes, report: _Report) -> None:
    lines = []
    if 1 < len(report.symbols) <= MAX_SYMBOL_LINES:
        lines += [(series, color, 0.7) for series, color in zip(report.symbols, SYMBOL_COLORS)]
    if report.buy_and_hold:
        lines.append((report.buy_and_hold, BENCHMARK_COLOR, 1.2))
    lines.append((report.strategy, STRATEGY_COLOR, 1.4))

    for series, color, line_width in lines:
        axes.plot(series.dates, series.multipliers, color=color, linewidth=line_width, label=series.name)
    axes.axhline(1, color=report.colors.muted, linewidth=0.5)

    values = np.concatenate([series.multipliers for series, _, _ in lines])
    # A log scale keeps a long compounding run readable. Across a narrow range it would have
    # no ticks to show, and it can't draw a balance that reached zero.
    if values.min() > 0 and values.max() / values.min() >= 3:
        axes.set_yscale('log')
        axes.yaxis.set_major_locator(mticker.LogLocator(base=10, subs=(1, 2, 5), numticks=8))
        axes.yaxis.set_minor_formatter(mticker.NullFormatter())
    spread = (values.max() - values.min()) * 100
    axes.yaxis.set_major_formatter(mticker.FuncFormatter(lambda value, _: _percent_label((value - 1) * 100, spread, signed=True)))
    _format_dates(axes)
    if len(lines) > 1:
        _add_legend(axes, report)


def _plot_underwater(axes, report: _Report) -> None:
    strategy = _compute_drawdown_series(report.strategy.balances.tolist(), report.strategy.dates)
    axes.fill_between([d for d, _ in strategy], [v for _, v in strategy], 0, color=STRATEGY_COLOR, alpha=0.25, linewidth=0)
    axes.plot([d for d, _ in strategy], [v for _, v in strategy], color=STRATEGY_COLOR, linewidth=0.8, label=report.strategy.name)
    if report.buy_and_hold:
        holding = _compute_drawdown_series(report.buy_and_hold.balances.tolist(), report.buy_and_hold.dates)
        axes.plot([d for d, _ in holding], [v for _, v in holding], color=BENCHMARK_COLOR, linewidth=0.8, label=report.buy_and_hold.name)
        _add_legend(axes, report)
    spread = abs(min(value for _, value in strategy))
    axes.yaxis.set_major_formatter(mticker.FuncFormatter(lambda value, _: _percent_label(value, spread)))
    _format_dates(axes)


def _plot_monthly_heatmap(axes, report: _Report) -> None:
    monthly = report.strategy.monthly_returns
    if not monthly:
        _show_message(axes, report, 'Not enough data')
        return

    years = sorted({year for year, _ in monthly})
    yearly = report.strategy.yearly_returns
    grid = np.full((len(years), 13), np.nan)
    for (year, month), value in monthly.items():
        grid[years.index(year), month - 1] = value
    for row, year in enumerate(years):
        grid[row, 12] = yearly[year]

    # Scaled by the months alone and capped, so that neither a year's total nor one extreme
    # month washes out all the others.
    limit = max(10.0, min(float(np.nanmax(np.abs(grid[:, :12]))), 50.0))
    colors = LinearSegmentedColormap.from_list('monthly_returns', [NEGATIVE_COLOR, report.colors.surface, POSITIVE_COLOR]).copy()
    colors.set_bad(report.colors.page)
    axes.imshow(np.ma.masked_invalid(grid), cmap=colors, norm=TwoSlopeNorm(vmin=-limit, vcenter=0, vmax=limit), aspect='auto')

    font_size = min(6.5, 90 / len(years) + 3)
    for row in range(len(years)):
        for month in range(13):
            value = grid[row, month]
            if not np.isnan(value):
                color = 'white' if abs(value) > limit * 0.6 else report.colors.ink
                weight = 'bold' if month == 12 else 'normal'
                axes.text(month, row, f'{value:,.1f}', ha='center', va='center', size=font_size, color=color, weight=weight)

    axes.set_xticks(range(13), ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec', 'Year'])
    axes.xaxis.tick_top()
    axes.set_yticks(range(len(years)), [str(year) for year in years])
    axes.tick_params(length=0)
    axes.yaxis.grid(False)
    for spine in axes.spines.values():
        spine.set_visible(False)


def _plot_histogram(axes, report: _Report, values: list, label: str, empty_message: str) -> None:
    array = np.array([value for value in values if _is_defined(value) and not math.isinf(value)], dtype=float)
    if len(array) < 2:
        _show_message(axes, report, empty_message)
        return

    mean = float(array.mean())
    # A few leveraged winners can stretch the axis until everything else is a single spike, so
    # those outliers are grouped at the edges. The mean is taken before they are moved.
    lower_quartile, upper_quartile = np.percentile(array, [25, 75])
    reach = OUTLIER_QUARTILE_RANGES * (upper_quartile - lower_quartile)
    low, high = lower_quartile - reach, upper_quartile + reach
    if reach > 0 and (array.min() < low or array.max() > high):
        array = np.clip(array, low, high)
        label += ' (outliers grouped at the edges)'

    # 'auto' picks a sensible width, and the cap keeps the bars from turning into hairlines.
    edges = np.histogram_bin_edges(array, bins='auto')
    if len(edges) > MAX_HISTOGRAM_BINS + 1:
        edges = np.linspace(array.min(), array.max(), MAX_HISTOGRAM_BINS + 1)
    counts, edges = np.histogram(array, bins=edges)
    centers = (edges[:-1] + edges[1:]) / 2
    colors = [POSITIVE_COLOR if center >= 0 else NEGATIVE_COLOR for center in centers]
    axes.bar(centers, counts, width=(edges[1] - edges[0]) * 0.86, color=colors)

    axes.axvline(np.clip(mean, edges[0], edges[-1]), color=report.colors.ink, linewidth=0.9, linestyle='--', label=f'Mean {mean:+,.2f}%')
    axes.set_xlabel(label, size=7)
    spread = float(array.max() - array.min())
    axes.xaxis.set_major_formatter(mticker.FuncFormatter(lambda value, _: _percent_label(value, spread)))
    axes.yaxis.set_major_locator(mticker.MaxNLocator(integer=True, nbins=5))
    _add_legend(axes, report)


def _plot_entry_timing(axes, report: _Report) -> None:
    grid = _compute_entry_timing([trade['opened_at'] for trade in report.trades])
    colors = LinearSegmentedColormap.from_list('entry_timing', [report.colors.surface, STRATEGY_COLOR])
    axes.pcolormesh(grid, cmap=colors, vmin=0, vmax=max(int(grid.max()), 1), edgecolors=report.colors.page, linewidth=1)
    axes.invert_yaxis()
    axes.set_xticks(np.arange(24) + 0.5, range(24))
    axes.set_yticks(np.arange(7) + 0.5, ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'])
    axes.set_xlabel('Hour of day (UTC)', size=7)
    axes.tick_params(length=0)
    axes.yaxis.grid(False)
    for spine in axes.spines.values():
        spine.set_visible(False)


def _monthly_extreme(series: _Series | None, pick: Callable) -> str:
    returns = series.monthly_returns.values() if series else []
    return _percent(pick(returns), signed=True) if returns else 'N/A'


def _performance_rows(report: _Report) -> list:
    """Rows of (label, portfolio value, buy-and-hold value)."""
    strategy = report.metrics
    holding = (report.benchmark_metrics or {}).get('portfolio', {})
    fields = [
        ('Starting balance', 'starting_balance', _number),
        ('Finishing balance', 'finishing_balance', _number),
        ('Net profit', 'net_profit', _number),
        ('Net profit %', 'net_profit_percentage', lambda value: _percent(value, signed=True)),
        ('Annual return', 'annual_return', lambda value: _percent(value, signed=True)),
        ('Max drawdown', 'max_drawdown', _percent),
        ('Max underwater period', 'max_underwater_period', _days),
        ('Sharpe ratio', 'sharpe_ratio', _number),
        ('Smart Sharpe', 'smart_sharpe', _number),
        ('Sortino ratio', 'sortino_ratio', _number),
        ('Smart Sortino', 'smart_sortino', _number),
        ('Calmar ratio', 'calmar_ratio', _number),
        ('Omega ratio', 'omega_ratio', _number),
        ('Serenity index', 'serenity_index', _number),
        ('Positive months', 'positive_months', _whole),
        ('Negative months', 'negative_months', _whole),
    ]
    rows = [(label, render(strategy.get(key)), render(holding.get(key))) for label, key, render in fields]
    rows.append(('Best month', _monthly_extreme(report.strategy, max), _monthly_extreme(report.buy_and_hold, max)))
    rows.append(('Worst month', _monthly_extreme(report.strategy, min), _monthly_extreme(report.buy_and_hold, min)))
    return rows


def _side_win_rate(metrics: dict, side: str) -> str:
    """A side that never traded has no win rate, though it's stored as 0."""
    return _ratio_percent(metrics.get(f'win_rate_{side}s')) if metrics.get(f'{side}s_count') != 0 else 'N/A'


def _trading_rows(metrics: dict) -> list:
    get = metrics.get
    return [
        ('Total trades', _whole(get('total'))),
        ('Winning | losing', f"{_whole(get('total_winning_trades'))} | {_whole(get('total_losing_trades'))}"),
        ('Win rate', _ratio_percent(get('win_rate'))),
        ('Win rate longs', _side_win_rate(metrics, 'long')),
        ('Win rate shorts', _side_win_rate(metrics, 'short')),
        ('Longs | shorts', f"{_percent(get('longs_percentage'))} | {_percent(get('shorts_percentage'))}"),
        ('Average win', _number(get('average_win'))),
        ('Average loss', _number(get('average_loss'))),
        ('Avg win / avg loss', _number(get('ratio_avg_win_loss'))),
        ('Expectancy', f"{_number(get('expectancy'))} ({_percent(get('expectancy_percentage'))})"),
        ('Largest win', _number(get('largest_winning_trade'))),
        ('Largest loss', _number(get('largest_losing_trade'))),
        ('Winning streak', _whole(get('winning_streak'))),
        ('Losing streak', _whole(get('losing_streak'))),
        ('Gross profit', _number(get('gross_profit'))),
        ('Gross loss', _number(get('gross_loss'))),
        ('Paid fees', _number(get('fee'))),
        ('Avg holding time', _duration(get('average_holding_period'))),
    ]


def _worst_drawdown_rows(series: _Series) -> list:
    dates = series.dates
    lag = timedelta(milliseconds=stats.BALANCE_SAMPLE_LAG_MS)
    rows = []
    for rank, period in enumerate(_find_worst_drawdown_periods(series.balances.tolist(), dates, n=5), start=1):
        recovery = period['recovery']
        # The peak is the sample before the fall and the end the last one below it, which is how
        # Max Underwater Period measures, so that the longest of these two agree.
        peak = dates[dates.index(period['start']) - 1]
        last_below_peak = dates[dates.index(recovery) - 1] if recovery else dates[-1]
        rows.append((
            str(rank),
            # Balances are sampled just after the day they measure ended.
            _date(period['start'] - lag),
            _date(period['bottom'] - lag),
            _date(recovery - lag) if recovery else 'Not recovered',
            _percent(period['max_drawdown']),
            _days((last_below_peak - peak).days),
        ))
    return rows


def _yearly_rows(report: _Report) -> list:
    """Rows of (year, strategy return, buy-and-hold return)."""
    strategy = report.strategy.yearly_returns
    holding = report.buy_and_hold.yearly_returns if report.buy_and_hold else {}
    return [
        (str(year), _percent(strategy.get(year), signed=True), _percent(holding.get(year), signed=True))
        for year in sorted(set(strategy) | set(holding))
    ]


def _route_rows(report: _Report) -> list:
    holdings = {r['symbol']: r for r in (report.benchmark_metrics or {}).get('routes', [])}
    rows = []
    for route in report.routes:
        symbol = route.get('symbol')
        trades = [t for t in report.trades if t.get('symbol') == symbol]
        wins = sum(1 for t in trades if t['PNL'] > 0)
        holding = holdings.get(symbol, {})
        rows.append((
            symbol,
            route.get('timeframe'),
            route.get('strategy'),
            str(len(trades)),
            _percent(wins / len(trades) * 100) if trades else 'N/A',
            _number(sum(t['PNL'] for t in trades)),
            _number(sum(t['fee'] for t in trades)),
            _percent(holding.get('net_profit_percentage'), signed=True),
            _percent(holding.get('max_drawdown')),
        ))
    return rows


def _setting_rows(report: _Report) -> list:
    config = report.exchange_config
    leverage = config.get('futures_leverage')
    leverage_mode = config.get('futures_leverage_mode')
    is_futures = config.get('type') == 'futures'
    timeframes = list(dict.fromkeys(str(r.get('timeframe')) for r in report.routes if r.get('timeframe')))
    fee = config.get('fee')
    single_route = len(report.routes) == 1

    return [
        ('Strategy', _strategies_label(report.routes) or 'N/A'),
        ('Exchange', report.form.get('exchange') or config.get('name') or 'N/A'),
        ('Period', report.period),
        ('Symbol' if single_route else 'Routes', report.routes[0].get('symbol') if single_route else str(len(report.routes))),
        ('Timeframes', ', '.join(timeframes) or 'N/A'),
        ('Starting balance', _number(report.metrics.get('starting_balance'))),
        ('Fee', _percent(fee * 100) if _is_defined(fee) else 'N/A'),
        ('Leverage', f'{leverage}x {leverage_mode or ""}'.strip() if is_futures and leverage else 'None'),
        ('Annualization', _whole(report.metrics.get('annualization'))),
        ('Generated', f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')} by Jesse {__version__}"),
    ]


def _cumulative_title(report: _Report, suffix: str = '') -> str:
    """The title the dashboard gives this chart."""
    return f"Cumulative Returns{' vs Benchmark' if report.buy_and_hold else ''}{suffix}"


def _draw_chart(report: _Report, page: _Page, name: str, title: str, height: float, draw: Callable = None, top_gutter: float = 0) -> None:
    """
    Show the image the backtest saved for a chart, or draw it when that image doesn't exist.
    Charts with nothing to draw them from are left out.
    """
    photo = report.photos.get(name)
    if photo is None and draw is None:
        return

    page.section(title)
    if photo is not None:
        page.photo(photo, height)
    else:
        page.y += top_gutter
        draw(page.axes(height - top_gutter))


def _draw_summary(report: _Report, page: _Page) -> None:
    metrics = report.metrics
    holding = (report.benchmark_metrics or {}).get('portfolio')

    page.text(0, page.y + 0.24, 'Backtest report', size=8.5, color=page.colors.muted)
    title = _truncate(report.title, MAX_TITLE_LENGTH)
    page.text(0, page.y + 0.56, title, size=_fitted_size(title, CONTENT_WIDTH, 17), weight='bold')
    page.y += 0.76

    def versus(key: str, render: Callable) -> str:
        return f'Buy & Hold {render(holding.get(key))}' if holding else ''

    signed = lambda value: _percent(value, signed=True)
    tiles = [
        ('Net profit', signed(metrics.get('net_profit_percentage')), versus('net_profit_percentage', signed)),
        ('Annual return', signed(metrics.get('annual_return')), versus('annual_return', signed)),
        ('Max drawdown', _percent(metrics.get('max_drawdown')), versus('max_drawdown', _percent)),
        ('Sharpe ratio', _number(metrics.get('sharpe_ratio')), versus('sharpe_ratio', _number)),
        ('Win rate', _ratio_percent(metrics.get('win_rate')), f"{_whole(metrics.get('total_winning_trades'))} won, {_whole(metrics.get('total_losing_trades'))} lost"),
        ('Total trades', _whole(metrics.get('total')), f"{_number(metrics.get('avg_trades_per_month'), digits=1)} per month"),
    ]
    gap = 0.08
    tile_width = (CONTENT_WIDTH - gap * (len(tiles) - 1)) / len(tiles)
    # They share one size, the one the longest value needs, so the row reads evenly.
    value_size = min(_fitted_size(value, tile_width - 2 * TILE_PADDING, 14) for _, value, _ in tiles)
    for index, tile in enumerate(tiles):
        page.tile(index * (tile_width + gap), tile_width, 0.75, value_size, *tile)
    page.y += 0.75

    _draw_chart(report, page, 'equity_curve', _cumulative_title(report), WIDE_CHART_HEIGHT)
    # Without the saved images, the one chart left takes the room of both, and its scale depends on the data.
    log_height = WIDE_CHART_HEIGHT if 'equity_curve' in report.photos else 2 * WIDE_CHART_HEIGHT + SECTION_HEIGHT
    log_title = _cumulative_title(report, ' (Log Scaled)' if 'cumulative_returns' in report.photos else '')
    # The saved chart above already shows this, under the same title, if only its log version is missing.
    draw_returns = None if 'equity_curve' in report.photos else (lambda axes: _plot_cumulative_returns(axes, report))
    _draw_chart(report, page, 'cumulative_returns', log_title, log_height, draw_returns)

    page.section('Setup')
    rows = _setting_rows(report)
    half = len(rows) // 2
    top = page.y
    column_width = (CONTENT_WIDTH - 0.3) / 2
    columns = [('', 0.4, 'left'), ('', 0.6, 'right')]
    _table(page, columns, rows[:half], width=column_width)
    page.y = top
    _table(page, columns, rows[half:], left=column_width + 0.3, width=column_width)

    page.y += 0.06
    page.small_print('Simulated results from historical data. Past performance does not guarantee future results.')


def _draw_metrics(report: _Report, page: _Page) -> None:
    gap = 0.3
    performance_width = 3.95

    page.section('Performance')
    page.text(performance_width + gap, page.y - HEADING_GAP, 'Trading', size=10, weight='bold')
    start = page.y
    rows = _performance_rows(report)
    if report.buy_and_hold:
        columns = [('', 0.44, 'left'), ('Buy & Hold', 0.28, 'right'), (PORTFOLIO_LABEL, 0.28, 'right')]
        rows = [(label, holding, value) for label, value, holding in rows]
    else:
        columns = [('', 0.55, 'left'), (PORTFOLIO_LABEL, 0.45, 'right')]
        rows = [row[:2] for row in rows]
    _table(page, columns, rows, width=performance_width)
    bottom = page.y

    page.y = start
    _table(page, [('', 0.5, 'left'), (PORTFOLIO_LABEL, 0.5, 'right')], _trading_rows(report.metrics), left=performance_width + gap, width=CONTENT_WIDTH - performance_width - gap)
    page.y = max(bottom, page.y)

    if report.buy_and_hold:
        count = len(report.symbols)
        holding = f'splits the starting balance equally between the {count} symbols of this backtest and never rebalances' if count > 1 \
            else f'invests the whole starting balance in {report.symbols[0].name}' if count else 'holds the traded symbol'
        page.y += 0.04
        page.small_print(f'Buy & Hold {holding}. It buys at the close of the first day, with no leverage and no fees.')

    page.section('Worst drawdowns')
    rows = _worst_drawdown_rows(report.strategy)
    if rows:
        _table(page, [('#', 0.06, 'left'), ('Started', 0.2, 'left'), ('Bottom', 0.2, 'left'), ('Recovered', 0.2, 'left'), ('Depth', 0.17, 'right'), ('Length', 0.17, 'right')], rows)
    else:
        page.y += 0.1
        page.text(0, page.y, 'The balance never fell below a previous high.', size=7.5, color=page.colors.muted)

    _draw_yearly_returns(report, page)


def _draw_yearly_returns(report: _Report, page: _Page) -> None:
    rows = _yearly_rows(report)
    if not rows:
        return

    page.section('Yearly returns')
    if report.buy_and_hold:
        columns = [('Year', 0.3, 'left'), ('Buy & Hold', 0.35, 'right'), (PORTFOLIO_LABEL, 0.35, 'right')]
        rows = [(year, holding, value) for year, value, holding in rows]
    else:
        columns = [('Year', 0.5, 'left'), (PORTFOLIO_LABEL, 0.5, 'right')]
        rows = [row[:2] for row in rows]

    # The header row and a little air come out of what's left of the page.
    fitting_rows = int((CONTENT_BOTTOM - page.y - 0.3) / TABLE_ROW_HEIGHT)
    if len(rows) <= fitting_rows:
        _table(page, columns, rows)
        return

    # A long backtest takes two columns, keeping its latest years if even those run out.
    rows = rows[-2 * fitting_rows:]
    gap = 0.3
    width = (CONTENT_WIDTH - gap) / 2
    top = page.y
    middle = (len(rows) + 1) // 2
    _table(page, columns, rows[:middle], width=width)
    bottom = page.y
    page.y = top
    _table(page, columns, rows[middle:], left=width + gap, width=width)
    page.y = max(bottom, page.y)


def _heatmap_height(report: _Report) -> float:
    """The height the heatmap needs: the shape of its saved image, or a row per year when drawn."""
    photo = report.photos.get('monthly_heatmap')
    if photo is not None:
        return CONTENT_WIDTH * photo.shape[0] / photo.shape[1]
    years = {year for year, _ in report.strategy.monthly_returns}
    return max(1.3, 0.75 + len(years) * 0.3)


def _draw_heatmap(report: _Report, page: _Page, max_height: float) -> None:
    height = min(_heatmap_height(report), max_height)
    # A drawn heatmap has its month names above its axes.
    _draw_chart(report, page, 'monthly_heatmap', 'Monthly Returns Heatmap', height, lambda axes: _plot_monthly_heatmap(axes, report), top_gutter=0.2)


def _draw_monthly_distribution(report: _Report, page: _Page) -> None:
    monthly_returns = list(report.strategy.monthly_returns.values())
    _draw_chart(report, page, 'monthly_distribution', 'Monthly Returns Distribution', DISTRIBUTION_HEIGHT, lambda axes: _plot_histogram(axes, report, monthly_returns, 'Monthly return', 'Not enough data'))


def _draw_drawdowns(report: _Report, page: _Page, heatmap_fits: bool) -> None:
    _draw_chart(report, page, 'drawdown', 'Drawdown (Worst 5 Periods)', WIDE_CHART_HEIGHT)
    _draw_chart(report, page, 'underwater', 'Underwater Plot', UNDERWATER_HEIGHT, lambda axes: _plot_underwater(axes, report))
    # When the heatmap needs a page of its own, the room it leaves goes to the next chart.
    if heatmap_fits:
        _draw_heatmap(report, page, HEATMAP_ROOM)
    else:
        _draw_monthly_distribution(report, page)


def _draw_distributions(report: _Report, page: _Page, with_monthly_distribution: bool) -> None:
    trade_returns = [trade.get('PNL_percentage') for trade in report.trades]

    if with_monthly_distribution:
        _draw_monthly_distribution(report, page)
    _draw_chart(report, page, 'trade_pnl', 'Trade PnL Distribution', DISTRIBUTION_HEIGHT, lambda axes: _plot_histogram(axes, report, trade_returns, 'PnL per trade', 'Not enough trades'))
    _draw_chart(report, page, 'entry_timing', 'Entry Timing (Hour × Weekday)', ENTRY_TIMING_HEIGHT, lambda axes: _plot_entry_timing(axes, report))


def _draw_routes(report: _Report, page: _Page, rows: list) -> None:
    page.section('Results by route')
    columns = [
        ('Symbol', 0.15, 'left'), ('TF', 0.06, 'left'), ('Strategy', 0.2, 'left'), ('Trades', 0.07, 'right'), ('Win rate', 0.09, 'right'),
        ('Net profit', 0.13, 'right'), ('Fees', 0.1, 'right'), ('B&H return', 0.11, 'right'), ('B&H DD', 0.09, 'right'),
    ]
    _table(page, columns, rows, size=7)


def _note_lines(notes: str) -> list:
    return [line for paragraph in notes.splitlines() for line in (textwrap.wrap(paragraph, width=120) or [''])]


def _data_route_lines(report: _Report) -> list:
    data_routes = report.form.get('data_routes') or []
    return textwrap.wrap(', '.join(f"{r.get('symbol')} {r.get('timeframe')}" for r in data_routes), width=125, break_on_hyphens=False)


def _detail_sections(report: _Report) -> list:
    """The details a backtest has, each as the table rows of room it takes and what draws it."""
    sections = []
    # A cut section has one more line, to say so.
    for lines, limit, draw in (
        (report.hyperparameters, MAX_HYPERPARAMETER_ROWS, _draw_hyperparameters),
        (_data_route_lines(report), MAX_DATA_ROUTE_LINES, _draw_data_routes),
        (_note_lines(report.notes), MAX_NOTE_LINES, _draw_notes),
    ):
        if lines:
            sections.append((min(len(lines), limit) + (len(lines) > limit) + SECTION_ROWS, draw))
    return sections


def _say_what_was_cut(page: _Page, total: int, limit: int, unit: str) -> None:
    if total > limit:
        page.small_print(f'And {total - limit} more {unit}.')


def _draw_hyperparameters(report: _Report, page: _Page) -> None:
    page.section('Hyperparameters')
    rows = [(str(name), str(value)) for name, value in report.hyperparameters[:MAX_HYPERPARAMETER_ROWS]]
    _table(page, [('', 0.5, 'left'), ('', 0.5, 'right')], rows)
    _say_what_was_cut(page, len(report.hyperparameters), MAX_HYPERPARAMETER_ROWS, 'hyperparameters')


def _draw_lines(page: _Page, lines: list) -> None:
    page.y += 0.04
    # One size for the block, the one its longest line needs.
    size = min(_fitted_size(line, CONTENT_WIDTH, 7.5) for line in lines)
    for line in lines:
        page.text(0, page.y, line, size=size)
        page.y += 0.17


def _draw_data_routes(report: _Report, page: _Page) -> None:
    lines = _data_route_lines(report)
    page.section('Data routes')
    _draw_lines(page, lines[:MAX_DATA_ROUTE_LINES])
    _say_what_was_cut(page, len(lines), MAX_DATA_ROUTE_LINES, 'lines of data routes')


def _draw_notes(report: _Report, page: _Page) -> None:
    lines = _note_lines(report.notes)
    page.section('Notes')
    _draw_lines(page, lines[:MAX_NOTE_LINES])
    _say_what_was_cut(page, len(lines), MAX_NOTE_LINES, 'lines of notes')
