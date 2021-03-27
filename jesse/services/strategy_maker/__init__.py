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

    # replace 'ExampleStrategy' with the name of the new strategy
    fin = open(f"{path}/__init__.py", "rt")
    data = fin.read()
    data = data.replace('ExampleStrategy', name)
    fin.close()
    fin = open(f"{path}/__init__.py", "wt")
    fin.write(data)
    fin.close()

    # output the location of generated strategy directory
    print(jh.color(f'Strategy created at: {path}', 'green'))
