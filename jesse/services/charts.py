from datetime import datetime, timedelta
from jesse.routes import router
from jesse.store import store
from jesse.services.candle import get_candles
from jesse.utils import prices_to_returns


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
    if store.completed_trades.count == 0:
        return None

    result = []
    start_date = datetime.fromtimestamp(store.app.starting_time / 1000)
    daily_balance = store.app.daily_balance

    # Define the first 10 colors
    colors = ['#818CF8', '#fbbf24', '#fb7185', '#60A5FA', '#f472b6', '#A78BFA', '#f87171', '#6EE7B7', '#93C5FD', '#FCA5A5']

    result.append(_calculate_equity_curve(daily_balance, start_date, 'Portfolio', colors[0]))

    if benchmark:
        initial_balance = daily_balance[0]
        for i, r in enumerate(router.routes):
            _, daily_candles = get_candles(
                r.exchange, r.symbol, '1D', store.app.starting_time,
                store.app.ending_time + 1000 * 60 * 60 * 24, is_for_jesse=False, warmup_candles_num=0, caching=True
            )
            daily_returns = prices_to_returns(daily_candles[:, 2])
            daily_returns[0] = 0
            daily_balance_benchmark = initial_balance * (1 + daily_returns/100).cumprod()

            # If there are more than 10 routes, generate new colors
            if i + 1 >= 10:
                colors.append(_generate_color(colors[-1]))

            result.append(_calculate_equity_curve(daily_balance_benchmark, start_date, r.symbol, colors[(i + 1) % len(colors)]))

    return result
