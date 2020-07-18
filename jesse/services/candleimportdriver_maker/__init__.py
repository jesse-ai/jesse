import os
import shutil

import jesse.helpers as jh


def generate(name):
    """

    :param name:
    :return:
    """
    path = 'plugins/CandlesImportDrivers'
    driverfullpathname = os.path.join(path, "{}.py".format(name.lower()))
    # validation for name duplication
    exists = os.path.isdir(driverfullpathname)
    if exists:
        print(jh.color('Driver "{}" for importing candles already exists.'.format(name), 'red'))
        return

    # generate from ExampleStrategy
    dirname, filename = os.path.split(os.path.abspath(__file__))

    if not os.path.exists(path):
        os.makedirs(path)
    shutil.copyfile('{}/CandlesImportDrivers/DummyDriver.py'.format(dirname), driverfullpathname)

    # replace 'DummyDriver' with the name of the new driver
    fin = open(driverfullpathname, "rt")
    data = fin.read()
    data = data.replace('DummyDriver', name.title())
    fin.close()
    fin = open(driverfullpathname, "wt")
    fin.write(data)
    fin.close()
