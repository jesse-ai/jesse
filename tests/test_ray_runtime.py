"""Regression coverage for Ray's object-store floor in memory-capped containers."""

from types import SimpleNamespace

import pytest

from jesse.services import ray_runtime


def test_normal_memory_keeps_ray_default_proportion(monkeypatch):
    monkeypatch.setattr(ray_runtime.utils, 'estimate_available_memory', lambda: 4 * 1024**3)
    assert ray_runtime.object_store_memory() == int(4 * 1024**3 * 0.3)


def test_head_service_estimate_drop_does_not_reintroduce_invalid_store(monkeypatch):
    # Actual Tokyo observation: head startup reduces 277 MB available to 147 MB.
    # The second estimate must not let Ray select a 44 MB store below its floor.
    estimates = iter([277_000_000, 147_000_000])
    monkeypatch.setattr(ray_runtime.utils, 'estimate_available_memory', lambda: next(estimates))
    calls = []

    def start(**kwargs):
        remaining = ray_runtime.utils.estimate_available_memory()
        assert remaining == 147_000_000
        assert kwargs['object_store_memory'] == 83_100_000
        calls.append(kwargs)

    monkeypatch.setattr(ray_runtime.ray, 'init', start)
    ray_runtime.initialize_ray(1)
    assert len(calls) == 1


@pytest.mark.parametrize('platform,available,shared,expected', [
    ('darwin', 100 * 1024**3, 0, 2 * 1024**3),
    ('linux', 100 * 1024**3, 64 * 1024**2, 10_000_000_000),
    ('linux', 100 * 1024**3, 20_000_000_000, 19_000_000_000),
    ('linux', 1024**4, 1024**4, 200_000_000_000),
    ('win32', 1024**4, 0, 200_000_000_000),
])
def test_older_ray_platform_caps(monkeypatch, platform, available, shared, expected):
    # These are Ray's documented platform limits, not Jesse-specific quotas.
    monkeypatch.delattr(ray_runtime.utils, 'resolve_object_store_memory', raising=False)
    # Stub only this helper's platform view; pytest plugins keep the real OS.
    monkeypatch.setattr(ray_runtime, 'sys', SimpleNamespace(platform=platform))
    monkeypatch.setattr(ray_runtime.utils, 'estimate_available_memory', lambda: available)
    monkeypatch.setattr(ray_runtime.utils, 'get_shared_memory_bytes', lambda: shared)
    assert ray_runtime.object_store_memory() == expected


def test_newer_ray_platform_resolver_is_used(monkeypatch):
    monkeypatch.setattr(ray_runtime.utils, 'estimate_available_memory', lambda: 4 * 1024**3)
    calls = []

    def resolve(available):
        calls.append(available)
        return 1_000_000_000

    monkeypatch.setattr(ray_runtime.utils, 'resolve_object_store_memory', resolve, raising=False)
    assert ray_runtime.object_store_memory() == 1_000_000_000
    assert calls == [4 * 1024**3]


@pytest.mark.parametrize('available', [240_000_000, 250_000_000, 260_000_000])
def test_small_container_uses_ray_minimum(monkeypatch, available):
    # These estimates put Ray's 30% default below its mandatory 75 MiB floor,
    # reproducing the rejected Tokyo startup without consuming the host's RAM.
    monkeypatch.setattr(ray_runtime.utils, 'estimate_available_memory', lambda: available)
    assert ray_runtime.object_store_memory() == ray_runtime.ray_constants.OBJECT_STORE_MINIMUM_MEMORY_BYTES


@pytest.mark.parametrize('remaining', [0, 1])
def test_insufficient_memory_has_actionable_error(monkeypatch, remaining):
    minimum = ray_runtime.ray_constants.OBJECT_STORE_MINIMUM_MEMORY_BYTES
    monkeypatch.setattr(ray_runtime.utils, 'estimate_available_memory', lambda: minimum - remaining)
    with pytest.raises(MemoryError, match='increase the Jesse container memory limit'):
        ray_runtime.object_store_memory()


@pytest.mark.parametrize('message', [
    'After taking into account object store memory, memory available for tasks and actors is too small',
    'Attempting to cap object store memory usage at 75000000 bytes, but the minimum allowed is 78643200',
])
def test_late_ray_memory_rejection_is_actionable(monkeypatch, message):
    monkeypatch.setattr(ray_runtime.utils, 'estimate_available_memory', lambda: 4 * 1024**3)
    calls = []

    def rejected_start(**kwargs):
        calls.append(kwargs)
        raise ValueError(message)

    monkeypatch.setattr(ray_runtime.ray, 'init', rejected_start)
    with pytest.raises(MemoryError, match='increase the Jesse container memory limit'):
        ray_runtime.initialize_ray(1)
    assert len(calls) == 1


def test_non_memory_ray_error_is_preserved(monkeypatch):
    monkeypatch.setattr(ray_runtime.utils, 'estimate_available_memory', lambda: 4 * 1024**3)

    def bad_configuration(**kwargs):
        raise ValueError('Invalid CPU configuration')

    monkeypatch.setattr(ray_runtime.ray, 'init', bad_configuration)
    with pytest.raises(ValueError, match='Invalid CPU configuration'):
        ray_runtime.initialize_ray(1)
