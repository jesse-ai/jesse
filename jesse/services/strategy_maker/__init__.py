import os
import shutil

import jesse.helpers as jh


def generate(name: str) -> None:
    """

    :param name:
    :return:
    """
    path = f'strategies/{name}'

    # validation for name duplication
    exists = os.path.isdir(path)
    if exists:
        print(jh.color(f'Strategy "{name}" already exists.', 'red'))
        return

    # generate from ExampleStrategy
    dirname, filename = os.path.split(os.path.abspath(__file__))

    shutil.copytree(f'{dirname}/ExampleStrategy', path)

    with open(f"{path}/__init__.py") as fin:
        data = fin.read()
        data = data.replace('ExampleStrategy', name)
    with open(f"{path}/__init__.py", "wt") as fin:
        fin.write(data)
    # output the location of generated strategy directory
    print(jh.color(f'Strategy created at: {path}', 'green'))
