def pytest_configure(config):
    config.addinivalue_line(
        "filterwarnings",
        "ignore:Please use `import python_multipart` instead.:PendingDeprecationWarning",
    )
