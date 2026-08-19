import pytest

from jesse.testing_utils import single_route_backtest, two_data_routes_backtest


@pytest.mark.parametrize(
    ('is_futures_trading', 'leverage_mode'),
    [
        (False, 'cross'),
        (True, 'cross'),
        (True, 'isolated'),
    ],
    ids=['spot', 'futures-cross', 'futures-isolated'],
)
def test_long_lifecycle_across_trading_modes(
    is_futures_trading: bool,
    leverage_mode: str,
) -> None:
    """Run the same lifecycle contract through every supported trading mode."""
    # A nonzero fee makes this one scenario cover both execution and accounting.
    single_route_backtest(
        'TestLongLifecycleAcrossTradingModes',
        is_futures_trading=is_futures_trading,
        leverage=2,
        leverage_mode=leverage_mode,
        fee=0.001,
    )


@pytest.mark.parametrize(
    ('is_futures_trading', 'leverage_mode'),
    [
        (False, 'cross'),
        (True, 'cross'),
        (True, 'isolated'),
    ],
    ids=['spot', 'futures-cross', 'futures-isolated'],
)
def test_protective_orders_across_trading_modes(
    is_futures_trading: bool,
    leverage_mode: str,
) -> None:
    """Exercise sibling stop-loss and take-profit handling in every mode."""
    # Reuse the same 0.1% fee so mode-specific wallet behavior stays comparable.
    single_route_backtest(
        'TestProtectiveOrdersAcrossTradingModes',
        is_futures_trading=is_futures_trading,
        leverage=2,
        leverage_mode=leverage_mode,
        trend='down',
        fee=0.001,
    )


def test_generated_data_routes_drive_multi_route_execution() -> None:
    """Trade 1m and generated 5m routes while consuming 5m and 15m data routes."""
    two_data_routes_backtest(
        'TestGeneratedDataRouteExecutionBTC',
        'TestGeneratedDataRouteExecutionETH',
    )
