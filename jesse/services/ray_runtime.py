"""Startup rules shared by Jesse's local Ray workers."""

import sys

import ray
from packaging.version import Version
from ray._private import ray_constants, utils

# Ray 2.48 fixes the Windows logging handle/file-descriptor regression in Ray 2.45-2.47
# (ray-project/ray#53852). Keep this supported minimum in step with requirements.txt so a
# manually pinned affected build is rejected before entering native startup.
WINDOWS_MINIMUM_RAY_VERSION = Version('2.48.0')


class UnsupportedRayVersionError(RuntimeError):
    """The installed Ray does not meet Jesse's supported minimum for this platform."""


def require_supported_ray() -> None:
    """Check the Windows version minimum before entering Ray's native startup."""
    if sys.platform != 'win32' or Version(ray.__version__) >= WINDOWS_MINIMUM_RAY_VERSION:
        return
    raise UnsupportedRayVersionError(
        f'Jesse requires Ray {WINDOWS_MINIMUM_RAY_VERSION} or newer on Windows '
        f'(installed Ray {ray.__version__}). This minimum avoids the Windows logging '
        f'startup regression fixed in Ray 2.48 (ray-project/ray#53852). Upgrade Ray with: '
        f'python -m pip install --upgrade "ray>={WINDOWS_MINIMUM_RAY_VERSION}"'
    )


def _default_object_store_memory(available: int) -> int:
    """Use Ray's platform sizing, including versions without its sizing helper."""
    resolver = getattr(utils, 'resolve_object_store_memory', None)
    if resolver is not None:
        return int(resolver(available))

    # Older Ray versions keep this calculation inside ResourceSpec.resolve().
    # Retain its caps rather than allocating an oversized store on large hosts.
    size = int(available * ray_constants.DEFAULT_OBJECT_STORE_MEMORY_PROPORTION)
    if sys.platform == 'darwin':
        size = min(size, ray_constants.MAC_DEGRADED_PERF_MMAP_SIZE_LIMIT)
    cap = ray_constants.DEFAULT_OBJECT_STORE_MAX_MEMORY_BYTES
    if sys.platform in ('linux', 'linux2'):
        # Ray leaves 5% of shared memory free and permits its disk-backed
        # fallback up to REQUIRE_SHM_SIZE_THRESHOLD on small /dev/shm mounts.
        shared_cap = max(ray_constants.REQUIRE_SHM_SIZE_THRESHOLD,
                         int(utils.get_shared_memory_bytes() * 0.95))
        cap = min(cap, shared_cap)
    return min(size, cap) if cap else size


def object_store_memory() -> int:
    """Resolve a valid store size before Ray starts consuming head-service RAM."""
    # Ray's estimator respects Docker's cgroup limit and current usage. Host RAM
    # alone would overstate the memory available to a capped Jesse container.
    available = int(utils.estimate_available_memory())
    minimum = int(ray_constants.OBJECT_STORE_MINIMUM_MEMORY_BYTES)
    if available <= minimum:
        raise MemoryError(
            f'Not enough available memory to start research workers '
            f'({available / 1024**2:.1f} MiB available). Ray needs at least '
            f'{minimum / 1024**2:.1f} MiB for shared data, plus memory for workers. '
            'Free memory or increase the Jesse container memory limit.'
        )

    # Passing None lets Ray re-estimate after launching its head services and
    # choose a store below its floor. Resolve once, with the same platform caps;
    # Ray still checks the remaining worker heap and monitors physical memory.
    return max(minimum, _default_object_store_memory(available))


def initialize_ray(cpu_cores: int) -> None:
    """Start local research workers and explain Ray's startup memory rejections."""
    require_supported_ray()
    try:
        # Research progress uses Jesse's dashboard, so Ray's web frontend stays off.
        ray.init(num_cpus=cpu_cores, ignore_reinit_error=True,
                 object_store_memory=object_store_memory(), include_dashboard=False)
    except ValueError as error:
        # Ray checks the worker heap after starting head services. Available RAM
        # can fall between our estimate and that check; fewer CPUs do not fix it.
        message = str(error)
        if ('available for tasks and actors' in message
                or 'Attempting to cap object store memory usage' in message):
            raise MemoryError(
                'Not enough available memory to start research workers. '
                'Free memory, stop other research sessions, or increase the Jesse '
                'container memory limit. Ray needs room for its services, shared '
                'candle data, and Python workers.'
            ) from error
        raise
