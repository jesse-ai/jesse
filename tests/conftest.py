def pytest_configure(config):
    config.addinivalue_line(
        'markers',
        'slow: long-running regression backtests (deselect with -m "not slow")',
    )
