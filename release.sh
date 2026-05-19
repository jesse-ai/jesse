#!/usr/bin/env bash

set -Eeuo pipefail

REPO_DIR="${REPO_DIR:-/home/jesse}"
DOCKER_IMAGE="${DOCKER_IMAGE:-salehmir/jesse}"
PYTHON_RELEASE_IMAGE="${PYTHON_RELEASE_IMAGE:-python:3.11-slim-bullseye}"

log() {
  printf '[release] %s\n' "$*"
}

fail() {
  printf '[release] error: %s\n' "$*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "missing required command: $1"
}

extract_setup_version() {
  sed -nE 's/^VERSION = "([^"]+)"$/\1/p' setup.py
}

extract_package_version() {
  sed -nE 's/^__version__ = "([^"]+)"$/\1/p' jesse/version.py
}

require_command git
require_command docker

cd "$REPO_DIR" || fail "cannot enter repo directory: $REPO_DIR"

git rev-parse --is-inside-work-tree >/dev/null 2>&1 || fail "$REPO_DIR is not a git repository"

if ! git diff --quiet || ! git diff --cached --quiet; then
  fail "git worktree is not clean; commit or discard local VPS changes first"
fi

log "pulling latest code"
git pull --ff-only

setup_version="$(extract_setup_version)"
package_version="$(extract_package_version)"

[ -n "$setup_version" ] || fail "could not read VERSION from setup.py"
[ -n "$package_version" ] || fail "could not read __version__ from jesse/version.py"

if [ "$setup_version" != "$package_version" ]; then
  fail "version mismatch: setup.py=$setup_version, jesse/version.py=$package_version"
fi

VERSION="${VERSION:-$setup_version}"

if [ "$VERSION" != "$setup_version" ]; then
  fail "VERSION=$VERSION does not match repository version $setup_version"
fi

if [ -z "${PYPI_TOKEN:-}" ]; then
  fail "PYPI_TOKEN is not set"
fi

log "rebuilding package artifacts"
rm -rf dist build *.egg-info

log "building Docker image ${DOCKER_IMAGE}:${VERSION}"
docker build -t "${DOCKER_IMAGE}:${VERSION}" .

log "building Docker image ${DOCKER_IMAGE}:latest"
docker build -t "${DOCKER_IMAGE}:latest" .

log "publishing Python package to PyPI from ${PYTHON_RELEASE_IMAGE}"
docker run --rm \
  -v "${REPO_DIR}:/app" \
  -w /app \
  -e TWINE_USERNAME=__token__ \
  -e TWINE_PASSWORD="${PYPI_TOKEN}" \
  "${PYTHON_RELEASE_IMAGE}" \
  sh -eu -c '
    python -m pip install --no-cache-dir --upgrade pip build twine
    rm -rf dist build *.egg-info
    python -m build
    python -m twine upload dist/*
  '

log "pushing Docker image ${DOCKER_IMAGE}:${VERSION}"
docker push "${DOCKER_IMAGE}:${VERSION}"

log "pushing Docker image ${DOCKER_IMAGE}:latest"
docker push "${DOCKER_IMAGE}:latest"

log "release completed for version ${VERSION}"
