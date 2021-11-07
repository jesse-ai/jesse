import os
import shutil
from starlette.responses import JSONResponse


def generate(name: str) -> JSONResponse:
    path = f'strategies/{name}'

    # validation for name duplication
    exists = os.path.isdir(path)
    if exists:
        return JSONResponse({
            'status': 'error',
            'message': f'Strategy "{name}" already exists.'
        })

    # generate from ExampleStrategy
    dirname, filename = os.path.split(os.path.abspath(__file__))

    shutil.copytree(f'{dirname}/ExampleStrategy', path)

    # replace 'ExampleStrategy' with the name of the new strategy
    with open(f"{path}/__init__.py", "rt") as fin:
        data = fin.read()
        data = data.replace('ExampleStrategy', name)
    with open(f"{path}/__init__.py", "wt") as fin:
        fin.write(data)
    # return the location of generated strategy directory
    return JSONResponse({
        'status': 'success',
        'message': path
    })
