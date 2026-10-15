"""Standalone download worker; avoids importing Jesse or touching its installation."""
import sys

import requests


def download(url: str, destination: str) -> None:
    """Stream into a caller-owned temporary file that is removed after cancellation."""
    # Bound connection and stalled reads; the parent can terminate us sooner on S.
    with requests.get(url, stream=True, timeout=(10, 30)) as response:
        response.raise_for_status()
        with open(destination, 'wb') as output:
            # Small chunks bound memory usage regardless of the package size.
            for chunk in response.iter_content(chunk_size=8192):
                output.write(chunk)


if __name__ == '__main__':
    try:
        download(sys.argv[1], sys.argv[2])
    except Exception as exc:
        sys.stderr.write(f"Python Language Server download failed: {exc}\n")
        sys.exit(1)
