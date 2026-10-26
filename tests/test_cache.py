import multiprocessing
import os
import pickle
import time

from jesse.services.cache import INDEX_NAME, Cache


def _fill(path, prefix, count):
    cache = Cache(path)
    for i in range(count):
        cache.set_value(f'{prefix}-{i}', [prefix, i], expire_seconds=600)


def test_a_value_stored_by_another_process_is_found(tmp_path):
    first, second = Cache(str(tmp_path)), Cache(str(tmp_path))  # both read the empty index

    first.set_value('a', [1, 2])
    second.set_value('b', [3])

    assert second.get_value('a') == [1, 2]
    assert first.get_value('b') == [3]
    assert set(Cache(str(tmp_path)).db) == {'a', 'b'}  # neither write dropped the other's record


def test_parallel_processes_keep_every_record(tmp_path):
    context = multiprocessing.get_context('spawn')
    workers = [context.Process(target=_fill, args=(str(tmp_path), f'w{n}', 15)) for n in range(6)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(60)
        assert worker.exitcode == 0

    cache = Cache(str(tmp_path))
    assert len(cache.db) == 90
    assert all(cache.get_value(f'w{n}-{i}') == [f'w{n}', i] for n in range(6) for i in range(15))
    assert not [name for name in os.listdir(tmp_path) if name.endswith('.tmp')]


def test_records_are_found_whatever_path_an_older_index_stored(tmp_path):
    # Older versions stored a path relative to the folder Jesse was started in.
    with open(tmp_path / 'k.pickle', 'wb') as f:
        pickle.dump('value', f)
    with open(tmp_path / INDEX_NAME, 'wb') as f:
        pickle.dump({'k': {'expire_seconds': 60, 'expire_at': time.time() + 60, 'path': 'storage/temp/k.pickle'}}, f)

    assert Cache(str(tmp_path)).get_value('k') == 'value'


def test_an_expired_or_missing_value_is_forgotten(tmp_path):
    cache = Cache(str(tmp_path))
    cache.set_value('old', 1, expire_seconds=-1)
    cache.set_value('gone', 2)
    os.remove(tmp_path / 'gone.pickle')

    assert cache.get_value('old') is False
    assert cache.get_value('gone') is False
    assert not os.path.exists(tmp_path / 'old.pickle')
    assert Cache(str(tmp_path)).db == {}


def test_flush_removes_every_value_file_and_nothing_else(tmp_path):
    cache = Cache(str(tmp_path))
    cache.set_value('a', 1)
    with open(tmp_path / 'orphan.pickle', 'wb') as f:  # a file the index lost track of
        pickle.dump(2, f)
    os.makedirs(tmp_path / 'optuna')

    Cache(str(tmp_path)).flush()

    assert sorted(os.listdir(tmp_path)) == sorted([INDEX_NAME, 'cache_database.lock', 'optuna'])
    assert cache.get_value('a') is False
