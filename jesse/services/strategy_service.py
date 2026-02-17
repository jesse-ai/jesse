from typing import Any
from jesse.routes import router


def get_strategy(exchange: str, symbol: str) -> Any:
    if exchange is None or symbol is None:
        raise ValueError(f"exchange and symbol cannot be None. exchange: {exchange}, symbol: {symbol}")

    r = next(r for r in router.routes
             if r.exchange == exchange and r.symbol == symbol)
    return r.strategy

