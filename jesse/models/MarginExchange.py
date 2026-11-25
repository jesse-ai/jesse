from jesse.models.FuturesExchange import FuturesExchange


class MarginExchange(FuturesExchange):
    """
    A broker margin account (US equities on Alpaca, CFD/FX brokers later).

    Backtest and paper bookkeeping are inherited from the cross-margin perpetual model: margin is
    reserved when an order is submitted, realized PnL is credited when a position closes, and fees
    are charged on notional. What differs is declarative:

    - ``type`` is ``'margin'`` so the engine, reports and the dashboard label it honestly;
    - the leverage mode is always ``cross`` (a broker account has one shared margin pool);
    - ``futures_leverage`` is a *cap* chosen by the user, validated by the live driver against the
      broker's account multiplier; it is not sent to the venue;
    - there is no liquidation price and no funding: ``Position`` reports ``nan``/``None`` for both.

    Borrow fees, margin interest and maintenance-margin calls are not simulated; they are documented
    as execution assumptions. Live values arrive through ``update_from_stream`` exactly like futures:
    ``wallet_balance`` is the broker's equity (includes unrealized PnL) and ``available_margin`` is
    the unleveraged excess equity.
    """

    def __init__(self, name: str, starting_balance: float, fee_rate: float, leverage_cap: int):
        super().__init__(
            name, starting_balance, fee_rate,
            futures_leverage_mode='cross',
            futures_leverage=leverage_cap,
        )
        self.type = 'margin'

    @property
    def leverage_cap(self) -> int:
        return self.futures_leverage
