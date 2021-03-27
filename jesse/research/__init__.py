from .get_candles import get_candles


def init() -> None:
    from pydoc import locate
    import os
    import sys
    import jesse.helpers as jh

    # Python version validation.
    if jh.python_version() < 3.6:
        print(
            jh.color(
                f'Jesse has not beed tested with your Python version ({jh.python_version()}), hence it may not work properly. Consider upgrading to >= 3.7',
                'red'
            )
        )

    # fix directory issue
    sys.path.insert(0, os.getcwd())

    ls = os.listdir('.')
    is_jesse_project = 'strategies' in ls and 'config.py' in ls and 'storage' in ls and 'routes.py' in ls

    if not is_jesse_project:
        print(
            jh.color(
                'Invalid directory. To use Jesse inside notebooks, create notebooks inside the root of a Jesse project.',
                'red'
            )
        )

    if is_jesse_project:
        local_config = locate('config.config')
        from jesse.config import set_config
        set_config(local_config)
