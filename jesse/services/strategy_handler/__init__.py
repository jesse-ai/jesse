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
        
    # create the reports folder inside the startegy folder
    os.makedirs(f"{path}/reports", exist_ok=True)
        
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


def fork_strategy(new_name: str, content: str) -> JSONResponse:
    import re
    path = f'strategies/{new_name}'

    if os.path.isdir(path):
        return JSONResponse({
            'status': 'error',
            'message': f'Strategy "{new_name}" already exists.'
        }, status_code=409)

    # Replace the class name in the code with the new strategy name
    updated_content = re.sub(r'(?m)^class\s+(\w+)\b', f'class {new_name}', content)

    os.makedirs(path, exist_ok=True)

    with open(f"{path}/__init__.py", "wt") as fin:
        fin.write(updated_content)

    return JSONResponse({
        'status': 'success',
        'message': f'Strategy "{new_name}" has been created.'
    })


def import_strategy(name: str, code: str) -> JSONResponse:
    import re
    
    # Sanitize strategy name to create valid folder name
    # Remove any characters that aren't alphanumeric, underscore, or hyphen
    sanitized_name = re.sub(r'[^a-zA-Z0-9_-]', '_', name)
    # Replace multiple underscores with a single one
    sanitized_name = re.sub(r'_+', '_', sanitized_name)
    # Remove leading/trailing underscores
    sanitized_name = sanitized_name.strip('_')
    
    # Ensure name is not empty after sanitization
    if not sanitized_name:
        return JSONResponse({
            'status': 'error',
            'message': 'Invalid strategy name'
        }, status_code=400)
    
    path = f'strategies/{sanitized_name}'

    # Check if strategy already exists
    exists = os.path.isdir(path)
    if exists:
        return JSONResponse({
            'status': 'error',
            'message': f'Strategy "{sanitized_name}" already exists.'
        }, status_code=409)

    # Create strategy directory
    os.makedirs(path, exist_ok=True)

    # Write the strategy code to __init__.py
    with open(f"{path}/__init__.py", "wt") as f:
        f.write(code)

    return JSONResponse({
        'status': 'success',
        'message': f'Strategy "{sanitized_name}" has been imported.',
        'path': path,
        'name': sanitized_name
    })


def delete_strategy(name: str) -> JSONResponse:
    path = f'strategies/{name}'
    reports_path = f'{path}/reports'
    exists = os.path.isdir(path)

    if not exists:
        return JSONResponse({
            'status': 'error',
            'message': f'Strategy "{name}" does not exist.'
        }, status_code=404)

    # Explicitly remove report artifacts first, then the strategy directory.
    # This keeps behavior clear even if deletion logic changes later.
    if os.path.isdir(reports_path):
        shutil.rmtree(reports_path)

    shutil.rmtree(path)

    return JSONResponse({
        'status': 'success',
        'message': f'Strategy "{name}" has been deleted.'
    })
