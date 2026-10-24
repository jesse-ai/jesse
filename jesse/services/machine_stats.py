"""
How busy this machine is, for the research runners list: CPU use, memory, load. Uses psutil when it
is installed, else what the operating system offers without it (Linux and macOS). Every value can
be None when the system does not tell.
"""

import os
import re
import subprocess
from typing import Optional


def _memory_without_psutil() -> tuple:
    try:
        total = os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES')
    except (ValueError, OSError, AttributeError):
        return None, None
    available = None
    try:
        if os.path.exists('/proc/meminfo'):
            with open('/proc/meminfo') as f:
                match = re.search(r'^MemAvailable:\s+(\d+) kB', f.read(), re.M)
            if match:
                available = int(match.group(1)) * 1024
        else:
            output = subprocess.run(['vm_stat'], capture_output=True, text=True, timeout=2).stdout
            page = int(re.search(r'page size of (\d+) bytes', output).group(1))
            pages = {name: int(value) for name, value in re.findall(r'^Pages ([\w -]+):\s+(\d+)\.', output, re.M)}
            # Free, inactive and purgeable memory can be handed to new work right away.
            available = page * (pages.get('free', 0) + pages.get('inactive', 0) + pages.get('purgeable', 0))
    except Exception:
        available = None
    return total, available


def collect() -> dict:
    """{'cpu_percent', 'load_1m', 'memory_total_bytes', 'memory_used_bytes', 'memory_percent'}."""
    stats = {'cpu_percent': None, 'load_1m': None, 'memory_total_bytes': None, 'memory_used_bytes': None,
             'memory_percent': None}
    try:
        stats['load_1m'] = round(os.getloadavg()[0], 2)
    except (OSError, AttributeError):
        pass
    try:
        import psutil

        # Since the previous call (the runner calls it every few seconds); the first call reads 0.
        stats['cpu_percent'] = round(psutil.cpu_percent(interval=None), 1)
        memory = psutil.virtual_memory()
        stats['memory_total_bytes'], used = int(memory.total), int(memory.total - memory.available)
    except Exception:
        cores = os.cpu_count() or 1
        if stats['load_1m'] is not None:
            stats['cpu_percent'] = round(min(100.0, stats['load_1m'] / cores * 100), 1)
        total, available = _memory_without_psutil()
        stats['memory_total_bytes'] = total
        used = None if total is None or available is None else max(0, total - available)
    stats['memory_used_bytes'] = used
    if used is not None and stats['memory_total_bytes']:
        stats['memory_percent'] = round(used / stats['memory_total_bytes'] * 100, 1)
    return stats


def gigabytes(value: Optional[int]) -> Optional[float]:
    return None if value is None else round(value / 1024 ** 3, 1)
