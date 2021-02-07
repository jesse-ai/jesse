import os
import shutil

import jesse.helpers as jh


def generate(name: str) -> None:
    """

    :param name:
    :return:
    """
    path = 'strategies/{}'.format(name)

    # validation for name duplication
    exists = os.path.isdir(path)
    if exists:
        print(jh.color('Strategy "{}" already exists.'.format(name), 'red'))
        return

    # generate from ExampleStrategy
    dirname, filename = os.path.split(os.path.abspath(__file__))

    shutil.copytree('{}/ExampleStrategy'.format(dirname), path)

    # replace 'ExampleStrategy' with the name of the new strategy
    fin = open("{}/__init__.py".format(path), "rt")
    data = fin.read()
    data = data.replace('ExampleStrategy', name)
    fin.close()
    fin = open("{}/__init__.py".format(path), "wt")
    fin.write(data)
    fin.close()

    # output the location of generated strategy directory
    print(jh.color('Strategy created at: {}'.format(path), 'green'))
