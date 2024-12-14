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
        }, status_code=409)

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


def get_strategies() -> JSONResponse:
    path = 'strategies'
    directories = []

    # Iterate through the items in the specified path
    for item in os.listdir(path):
        # Construct full path
        full_path = os.path.join(path, item)
        # Check if the item is a directory
        if os.path.isdir(full_path):
            directories.append(item)

    return JSONResponse({
        'status': 'success',
        'strategies': directories
    })


def get_strategy(name: str) -> JSONResponse:
    path = f'strategies/{name}'
    exists = os.path.isdir(path)

    if not exists:
        return JSONResponse({
            'status': 'error',
            'message': f'Strategy "{name}" does not exist.'
        }, status_code=404)

    with open(f"{path}/__init__.py", "rt") as fin:
        content = fin.read()

    return JSONResponse({
        'status': 'success',
        'content': content
    })


def save_strategy(name: str, content: str) -> JSONResponse:
    path = f'strategies/{name}'
    exists = os.path.isdir(path)

    if not exists:
        return JSONResponse({
            'status': 'error',
            'message': f'Strategy "{name}" does not exist.'
        }, status_code=404)

    with open(f"{path}/__init__.py", "wt") as fin:
        fin.write(content)

    return JSONResponse({
        'status': 'success',
        'message': f'Strategy "{name}" has been saved.'
    })


def delete_strategy(name: str) -> JSONResponse:
    path = f'strategies/{name}'
    exists = os.path.isdir(path)

    if not exists:
        return JSONResponse({
            'status': 'error',
            'message': f'Strategy "{name}" does not exist.'
        }, status_code=404)

    shutil.rmtree(path)

    return JSONResponse({
        'status': 'success',
        'message': f'Strategy "{name}" has been deleted.'
    })
