import os
import shutil

import jesse.helpers as jh


def generate(name: str) -> None:
    path = '{}'.format(name)

    # validate that doesn't create if current directory is inside a Jesse project
    ls = os.listdir('.')
    is_jesse_project = 'strategies' in ls and 'config.py' in ls and 'storage' in ls and 'routes.py' in ls
    if is_jesse_project:
        print(jh.color('You are already inside a Jesse project. Check your working directory.'.format(name), 'red'))
        return

    # validation for name duplication
    exists = os.path.isdir(path)
    if exists:
        print(jh.color('Project "{}" already exists.'.format(name), 'red'))
        return

    # generate from ExampleStrategy
    dirname, filename = os.path.split(os.path.abspath(__file__))

    shutil.copytree('{}/project_template'.format(dirname), path)

    # output the location of generated strategy directory
    print(
        jh.color(
            'Your project is created successfully. \nRun "cd {}" to begin algo-trading!'.format(path, name),
            'green'
        )
    )

    # reminder for subscribe and forum
    print(
        jh.color(
            "\nDon't forget to subscribe for future updates at https://Jesse.Trade and make sure to check out the forum for support at https://forum.jesse.trade",
            "blue"
        )
    )
