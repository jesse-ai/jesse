def pytest_configure(config):
    # Route tests share the fully registered app, while production CLI imports
    # stay lightweight until startup has reserved its port and prepared services.
    import jesse.app

    config.addinivalue_line(
        'markers',
        'slow: long-running regression backtests (deselect with -m "not slow")',
    )
