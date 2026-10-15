"""Exercise the real native service with isolated ports, tokens and namespaces.

No existing Redis or PostgreSQL server is contacted. Each owned subprocess is
terminated by its fixture, including when an assertion fails.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import importlib.util
import shutil
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
import queue
import threading
import uuid

import pytest

try:
    import fcntl
    import resource
except ImportError:
    # Windows has socket handles, not the Unix high-descriptor regression.
    fcntl = resource = None

ROOT = Path(__file__).resolve().parents[1]
NATIVE = Path(os.environ.get('JESSE_COORDINATOR_SOURCE', str(ROOT.parent / 'jesse-rust' / 'coordination')))
CLIENT_SOURCE = ROOT / 'jesse' / 'services' / 'coordination_client.py'
# Load the standalone client without importing the full Jesse application. Native
# compatibility CI needs only Python, pytest and Rust; application checks run separately.
spec = importlib.util.spec_from_file_location('native_client_under_test', CLIENT_SOURCE)
assert spec is not None and spec.loader is not None
client_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(client_module)
AsyncClient = client_module.AsyncClient
Client = client_module.Client
CoordinationConnectionError = client_module.CoordinationConnectionError
CoordinationError = client_module.CoordinationError
LockError = client_module.LockError


@pytest.fixture(scope='session')
def binary():
    """Build only cached dependencies; never install tools or fetch packages."""
    required = os.environ.get('JESSE_COORDINATION_REQUIRE_TESTS') == '1'
    # Application-only checkouts lack Rust sources; dedicated native CI supplies
    # them and treats missing sources as a failure rather than skipping coverage.
    if not NATIVE.is_dir():
        if required:
            pytest.fail('Native coordinator source checkout is unavailable')
        pytest.skip('Native sources are unavailable; coordinator checks run in dedicated CI')
    if shutil.which('cargo') is None:
        if required:
            pytest.fail('Native coordinator checks require Cargo')
        pytest.skip('Cargo is unavailable; native coordinator checks run in dedicated CI')
    built = subprocess.run(['cargo', 'build', '--offline', '--locked'], cwd=NATIVE, capture_output=True, text=True)
    if built.returncode:
        unavailable = 'could not compile' not in built.stderr and 'error[' not in built.stderr
        if unavailable and not required:
            pytest.skip('Cargo dependency cache is unavailable; native coordinator checks run in dedicated CI')
        pytest.fail(built.stderr)
    return NATIVE / 'target' / 'debug' / ('jesse-coordinator.exe' if os.name == 'nt' else 'jesse-coordinator')


class Service:
    """Own an ephemeral native process and allow a deliberate restart on its port."""

    def __init__(self, binary, descriptor_limit=None, stderr=subprocess.PIPE):
        self.binary = binary
        self.descriptor_limit = descriptor_limit
        self.stderr = stderr
        self.token = secrets.token_hex(32)
        self.port = 0
        self.process = None
        self.start()

    def start(self):
        env = {**os.environ, 'JESSE_COORDINATION_TOKEN': self.token,
               'JESSE_COORDINATION_BIND': f'127.0.0.1:{self.port}'}
        command = [str(self.binary)]
        if self.descriptor_limit is not None:
            # Restrict only the owned child before exec, never pytest or the user shell.
            code = "import os,resource,sys; n=int(sys.argv[2]); resource.setrlimit(resource.RLIMIT_NOFILE,(n,n)); os.execv(sys.argv[1],[sys.argv[1]])"
            command = [sys.executable, '-c', code, str(self.binary), str(self.descriptor_limit)]
        self.process = subprocess.Popen(command, env=env, stdout=subprocess.PIPE, stderr=self.stderr, text=True)
        # A failed native startup must not hang a CI runner indefinitely.
        lines = queue.Queue()
        threading.Thread(target=lambda: lines.put(self.process.stdout.readline()), daemon=True).start()
        try:
            line = lines.get(timeout=15).strip()
        except queue.Empty:
            self.stop()
            raise AssertionError('Native coordinator startup timed out')
        if not line.startswith('jesse-coordinator listening on '):
            self.stop()
            raise AssertionError('Native coordinator failed to start')
        self.port = int(line.rsplit(':', 1)[1])

    def client(self, namespace=None):
        return Client('127.0.0.1', self.port, self.token, namespace or uuid.uuid4().hex)

    def stop(self):
        if self.process is not None:
            self.process.terminate()
            try:
                self.output, self.error = self.process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.output, self.error = self.process.communicate(timeout=5)


@pytest.fixture
def service(binary):
    server = Service(binary)
    try:
        yield server
    finally:
        server.stop()


@pytest.fixture
def client(service):
    return service.client()


@pytest.mark.parametrize('value', [b'', b'\x00\xff\r\n', 'hello', 'فارسی 日本語', 17, -2, 1.25])
def test_value_round_trip_and_delete(client, value):
    assert client.get('missing') is None
    assert client.set('value', value)
    assert client.get('value') == (value if isinstance(value, bytes) else str(value).encode())
    assert client.delete('value') == 1
    assert client.delete('value') == 0


def test_expiry_overwrite_and_counter_preservation(client):
    assert client.ttl('missing') == -2
    client.setex('n', 1, 10)
    assert client.incrby('n', 2) == 12
    time.sleep(1.2)
    assert client.get('n') is None
    client.setex('n', 1, 2)
    client.set('n', 3)
    time.sleep(1.2)
    assert client.get('n') == b'3'
    assert client.ttl('n') == -1
    assert client.expire('n', 1)
    assert not client.expire('missing', 1)
    time.sleep(1.2)
    assert client.get('n') is None


@pytest.mark.parametrize('ttl', [0, -1, float('nan'), float('inf'), True])
def test_invalid_expiry_does_not_mutate(client, ttl):
    client.set('n', 'original')
    with pytest.raises(ValueError):
        client.set('n', 'changed', ex=ttl)
    assert client.get('n') == b'original'


def test_sets_and_wrong_types(client):
    assert client.smembers('workers') == set()
    assert client.sadd('workers', 'one', b'\xff', 'one') == 2
    assert client.smembers('workers') == {b'one', b'\xff'}
    assert client.sismember('workers', 'one')
    assert client.srem('workers', 'one', 'absent') == 1
    with pytest.raises(CoordinationError, match='type:'):
        client.get('workers')
    assert client.srem('workers', b'\xff') == 1
    assert client.ttl('workers') == -2


def test_atomic_increments_under_concurrency(client):
    def increment(_):
        for _ in range(50):
            client.incrby('count', 1)
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(increment, range(8)))
    assert client.get('count') == b'400'


def test_counter_overflow_and_noninteger_are_not_committed(client):
    client.set('n', 2**63 - 1)
    with pytest.raises(CoordinationError, match='overflow'):
        client.incrby('n')
    assert client.get('n') == str(2**63 - 1).encode()
    client.set('n', 'not a number')
    with pytest.raises(CoordinationError, match='integer'):
        client.incrby('n')
    assert client.get('n') == b'not a number'


def test_namespace_isolation(service):
    first, second = service.client('one'), service.client('two')
    first.set('same', 'private')
    first.sadd('workers', 'job')
    assert second.get('same') is None
    assert second.smembers('workers') == set()


def test_token_and_generation_checks_precede_mutations(service, client):
    unauthorized = Client('127.0.0.1', service.port, 'wrong' * 8, client.namespace)
    with pytest.raises(CoordinationError, match='auth:'):
        unauthorized.set('key', 'bad')
    client.set('key', 'good')
    service.stop()
    service.start()
    with pytest.raises(CoordinationConnectionError, match='generation'):
        client.set('key', 'stale')
    fresh = service.client(client.namespace)
    assert fresh.get('key') is None
    assert fresh.set('key', 'new')


def test_lock_ownership_expiration_and_contention(client):
    first = client.lock('lock', timeout=1)
    second = client.lock('lock', timeout=2)
    assert first.acquire()
    assert not second.acquire()
    time.sleep(1.2)
    assert second.acquire()
    with pytest.raises(LockError, match='ownership'):
        first.release()
    assert not client.lock('lock', timeout=1).acquire()
    second.release()
    with client.lock('lock', timeout=1):
        with pytest.raises(LockError):
            with client.lock('lock', timeout=1, blocking_timeout=.05):
                pytest.fail('Contended lock was entered')


def test_lock_serializes_read_modify_write(client):
    client.set('value', 0)
    def increment(_):
        for _ in range(10):
            with client.lock('guard', timeout=5, blocking_timeout=5):
                client.set('value', int(client.get('value')) + 1)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(increment, range(4)))
    assert client.get('value') == b'40'


def test_lock_body_error_survives_expired_lease(client):
    with pytest.raises(ValueError, match='body') as error:
        with client.lock('short', timeout=.01):
            time.sleep(.03)
            raise ValueError('body failed')
    if sys.version_info >= (3, 11):
        assert any('expired' in note for note in error.value.__notes__)


def test_publications_order_filtering_namespace_and_unsubscribe(service, client):
    async def exercise():
        asynchronous = AsyncClient(client)
        subscription, = await asynchronous.psubscribe('events:*')
        other = service.client('other-namespace')
        assert other.publish('events:one', 'private') == 0
        assert client.publish('unrelated', 'ignored') == 0
        for i in range(20):
            # Let the independent reader drain between small bursts.
            assert await asynchronous.publish('events:one', str(i)) == 1
        messages = subscription.iter()
        received = [await asyncio.wait_for(anext(messages), 3) for _ in range(20)]
        assert received == [(b'events:one', str(i).encode()) for i in range(20)]
        await asynchronous.punsubscribe('events:*')
        await messages.aclose()
    asyncio.run(exercise())


def test_subscription_closes_on_service_failure(service, client):
    async def exercise():
        asynchronous = AsyncClient(client)
        subscription, = await asynchronous.psubscribe('events:*')
        service.stop()
        with pytest.raises((CoordinationConnectionError, OSError)):
            await asyncio.wait_for(anext(subscription.iter()), 3)
        await asynchronous.punsubscribe('events:*')
    asyncio.run(exercise())


def test_invalid_subscription_pattern(client):
    async def exercise():
        with pytest.raises(ValueError):
            await AsyncClient(client).psubscribe('events:??')
    asyncio.run(exercise())


def test_raw_protocol_rejects_malformed_frame_and_keeps_serving(service, client):
    with socket.create_connection(client.address, timeout=2) as sock:
        sock.sendall(b'not json\n')
        reply = json.loads(sock.makefile('rb').readline())
        assert not reply['ok']
    assert client.set('alive', 'yes')


def test_large_snapshot_and_event_capacity(client):
    # Chart snapshots and event notifications have different resource budgets.
    snapshot = b'x' * (2 * 1024 * 1024)
    assert client.set('chart', snapshot)
    assert client.get('chart') == snapshot
    assert client.publish('events:large', snapshot) == 0
    with pytest.raises(ValueError, match='8 MiB'):
        client.set('too-big', b'x' * (9 * 1024 * 1024))
    assert client.get('too-big') is None


def test_protocol_rejects_bad_requests_without_mutation(client):
    client.connect()
    for op, args in [
        ('put', {'key': 'x', 'value': 'zz'}),
        ('put', {'key': 'x', 'value': '61', 'ttl_ms': 0}),
        ('put', {'key': 'x', 'value': '61', 'ttl_ms': -1}),
        ('put', {'key': 'x', 'value': '61', 'ttl_ms': True}),
        ('increment', {'key': 'x', 'amount': 1.5}),
        ('add_members', {'key': 'x', 'members': ['61', 'odd']}),
        ('acquire_lock', {'key': 'x', 'owner': 'me'}),
        ('unknown', {'key': 'x'}),
    ]:
        with pytest.raises(CoordinationError):
            client.request(op, **args)
        assert client.get('x') is None


def test_counter_cannot_replace_lock(client):
    with client.lock('guard', timeout=1):
        with pytest.raises(CoordinationError, match='type:'):
            client.incrby('guard')
        assert not client.lock('guard', timeout=1).acquire()


def test_subscription_replacement_and_cancellation(service, client):
    async def exercise():
        asynchronous = AsyncClient(client)
        first, = await asynchronous.psubscribe('events:*')
        second, = await asynchronous.psubscribe('events:*')
        assert first.writer.is_closing()
        reader = second.iter()
        pending = asyncio.create_task(anext(reader))
        await asyncio.sleep(.01)
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
        assert second.writer.is_closing()
        await asynchronous.punsubscribe('events:*')
    asyncio.run(exercise())


def test_restart_rejects_resubscription(service, client):
    client.connect()
    service.stop()
    service.start()
    async def exercise():
        with pytest.raises(CoordinationConnectionError, match='generation'):
            await AsyncClient(client).psubscribe('events:*')
    asyncio.run(exercise())


def test_subscriptions_reserve_room_for_publishers(client):
    async def exercise():
        asynchronous = AsyncClient(client)
        try:
            for i in range(32):
                await asynchronous.psubscribe(f'events:{i}:*')
            with pytest.raises(CoordinationError, match='subscription limit'):
                await asynchronous.psubscribe('overflow:*')
            assert await asynchronous.publish('events:0:one', 'still responsive') == 1
            assert client.set('rpc-still-works', 'yes')
        finally:
            for pattern in list(asynchronous._subscriptions):
                await asynchronous.punsubscribe(pattern)
    asyncio.run(exercise())


def test_partial_request_has_a_whole_frame_deadline(client):
    with socket.create_connection(client.address, timeout=2) as sock:
        sock.settimeout(7)
        sock.sendall(b'{')
        started = time.monotonic()
        # A valid peer must still work while this unauthenticated one is idle.
        assert client.set('parallel', 'yes')
        assert sock.recv(1) == b''
        assert time.monotonic() - started < 6.5


def test_authentication_rejects_header_before_body(service, client):
    header = {'version': 1, 'token': 'wrong-token', 'namespace': 'test', 'op': 'hello'}
    with socket.create_connection(client.address, timeout=2) as sock:
        # No body is sent: an unauthenticated client must get rejected immediately.
        sock.sendall(json.dumps(header).encode() + b'\n')
        response = json.loads(sock.makefile('rb').readline())
        assert response['error'].startswith('auth:')


def test_lost_lock_acquire_reply_is_cleaned_up(client, monkeypatch):
    request = client.request
    def lose_reply(op, **args):
        result = request(op, **args)
        if op == 'acquire_lock':
            # Model the precise ambiguity: server committed, response was lost.
            raise CoordinationConnectionError('Reply lost after commit')
        return result
    monkeypatch.setattr(client, 'request', lose_reply)
    with pytest.raises(CoordinationConnectionError):
        client.lock('ambiguous', timeout=600).acquire()
    monkeypatch.setattr(client, 'request', request)
    with client.lock('ambiguous', timeout=1):
        pass


def test_set_mutations_preserve_expiry(client):
    client.sadd('members', 'one')
    client.expire('members', 1)
    client.sadd('members', 'two')
    client.srem('members', 'one')
    time.sleep(1.2)
    assert client.smembers('members') == set()
    assert client.ttl('members') == -2


def test_large_event_and_burst_are_delivered(client):
    async def exercise():
        asynchronous = AsyncClient(client)
        subscription, = await asynchronous.psubscribe('events:*')
        stream = subscription.iter()
        payload = b'x' * (2 * 1024 * 1024)
        received = asyncio.create_task(anext(stream))
        assert await asynchronous.publish('events:result', payload) == 1
        assert (await asyncio.wait_for(received, 5))[1] == payload
        for i in range(100):
            assert client.publish('events:burst', str(i)) == 1
        assert [(await asyncio.wait_for(anext(stream), 5))[1] for _ in range(100)] == [str(i).encode() for i in range(100)]
        await asynchronous.punsubscribe('events:*')
        await stream.aclose()
    asyncio.run(exercise())


def test_independent_python_processes_share_state(service, client):
    # Spawn fresh interpreters, not threads or inherited client sockets.
    code = '''import os
import runpy
Client = runpy.run_path(os.environ['LAB_CLIENT_SOURCE'])['Client']
c = Client('127.0.0.1', int(os.environ['LAB_PORT']), os.environ['LAB_TOKEN'], os.environ['LAB_NAMESPACE'])
for i in range(15): c.incrby('process-count')
'''
    env = {**os.environ, 'COORDINATION_BACKEND': 'rust', 'LAB_PORT': str(service.port),
           'LAB_TOKEN': service.token, 'LAB_NAMESPACE': client.namespace, 'LAB_CLIENT_SOURCE': str(CLIENT_SOURCE)}
    children = [subprocess.Popen([sys.executable, '-c', code], cwd=ROOT, env=env,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE) for _ in range(3)]
    try:
        for child in children:
            _, error = child.communicate(timeout=30)
            assert child.returncode == 0, error.decode()
        assert client.get('process-count') == b'45'
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
                child.communicate(timeout=5)


def test_large_body_rejection_preserves_typed_error(service, client):
    client.connect()
    stale = Client(*client.address, service.token, client.namespace, generation='stale-generation')
    with pytest.raises(CoordinationConnectionError, match='restart:'):
        stale.set('large', b'x' * (2 * 1024 * 1024))
    unauthorized = Client(*client.address, 'wrong' * 8, client.namespace, generation=client.generation)
    with pytest.raises(CoordinationError, match='auth:'):
        unauthorized.set('large', b'x' * (2 * 1024 * 1024))
    assert client.get('large') is None


def test_connection_overload_is_transient_and_recovers(client):
    if resource is not None and resource.getrlimit(resource.RLIMIT_NOFILE)[0] < 320:
        pytest.skip('Full 256-socket saturation needs descriptor headroom; low-limit recovery is tested separately')
    client.connect()
    client.close()  # Reserve every server slot explicitly, excluding cached RPCs.
    held = []
    try:
        # Receive the authentication ack to ensure each of the 256 slots is held,
        # then withhold its body. The server deadline releases abandoned slots.
        for _ in range(256):
            sock = socket.create_connection(client.address, timeout=2)
            held.append(sock)
            sock.sendall(client._frame('get', {'key': 'unused'}).split(b'\n', 1)[0] + b'\n')
            assert json.loads(sock.makefile('rb').readline())['value'] == 'ready'
        with pytest.raises(CoordinationConnectionError):
            client.get('busy')
    finally:
        for sock in held:
            sock.close()
    deadline = time.monotonic() + 5
    while True:
        try:
            assert client.set('recovered', 'yes')
            break
        except CoordinationConnectionError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(.02)


def test_slow_subscriber_does_not_disconnect_healthy_reader(client):
    async def exercise():
        client.connect()
        slow = socket.create_connection(client.address, timeout=2)
        # A small receive window makes the slow-consumer boundary reproducible
        # without relying on the host's default multi-megabyte socket buffers.
        slow.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024)
        reader = slow.makefile('rb')
        header, body = client._frame('subscribe', {'prefix': 'events:'}).split(b'\n', 1)
        slow.sendall(header + b'\n')
        assert json.loads(reader.readline())['value'] == 'ready'
        slow.sendall(body)
        assert json.loads(reader.readline())['value'] is True
        asynchronous = AsyncClient(client)
        subscription, = await asynchronous.psubscribe('events:*')
        stream = subscription.iter()
        try:
            payload = b'x' * (512 * 1024)
            counts = []
            for _ in range(40):
                receive = asyncio.create_task(anext(stream))
                counts.append(await asynchronous.publish('events:load', payload))
                assert (await asyncio.wait_for(receive, 5))[1] == payload
            assert 1 in counts  # The slow stream was dropped while this one lived.
        finally:
            reader.close()
            slow.close()
            await asynchronous.punsubscribe('events:*')
            await stream.aclose()
    asyncio.run(exercise())


def test_explicit_busy_retry_never_repeats_a_committed_mutation(client, monkeypatch):
    exchange = client._exchange
    attempts = []
    def busy_twice(op, args):
        if op == 'increment':
            attempts.append(op)
            if len(attempts) < 3:
                raise client_module.CoordinationBusyError('busy: synthetic pre-execution rejection')
        return exchange(op, args)
    monkeypatch.setattr(client, '_exchange', busy_twice)
    assert client.incrby('once') == 1
    assert len(attempts) == 3
    assert client.get('once') == b'1'


def test_ambiguous_mutation_is_never_retried(client, monkeypatch):
    exchange = client._exchange
    attempts = []
    def lose_response(op, args):
        result = exchange(op, args)
        if op == 'increment':
            attempts.append(op)
            raise CoordinationConnectionError('Synthetic response loss after commit')
        return result
    monkeypatch.setattr(client, '_exchange', lose_response)
    with pytest.raises(CoordinationConnectionError):
        client.incrby('once')
    assert len(attempts) == 1
    assert client.get('once') == b'1'


def test_busy_release_keeps_owner_for_explicit_retry(client, monkeypatch):
    lock = client.lock('guard', timeout=10)
    assert lock.acquire()
    exchange = client._exchange
    def busy_release(op, args):
        if op == 'release_lock':
            raise client_module.CoordinationBusyError('busy: synthetic pre-execution rejection')
        return exchange(op, args)
    monkeypatch.setattr(client, '_exchange', busy_release)
    with pytest.raises(client_module.CoordinationBusyError):
        lock.release()
    monkeypatch.setattr(client, '_exchange', exchange)
    lock.release()
    assert client.lock('guard', timeout=1).acquire()


def test_warm_calls_reuse_one_connection(client):
    for _ in range(100):
        client.incrby('warm')
    assert client.get('warm') == b'100'
    assert client._pool.qsize() == 1
    client.close()
    assert client._pool.qsize() == 0
    assert client.get('warm') == b'100'


def test_inherited_client_is_rejected_before_touching_io_locks(client, monkeypatch):
    client.connect()
    monkeypatch.setattr(client, '_pid', -1)
    with pytest.raises(CoordinationConnectionError, match='after fork'):
        client.set('should-not-write', 'value')


def test_partial_binary_upload_never_mutates_state(client):
    client.connect()
    header, _ = client._parts('put', {'key': 'partial', '_payload': b'eight!!!'})
    with socket.create_connection(client.address, timeout=2) as sock:
        sock.sendall(header)
        reader = sock.makefile('rb')
        assert json.loads(reader.readline())['value'] == 'ready'
        # Declare eight bytes, deliver four and close only our write direction.
        sock.sendall(b'{"key":"partial"}\n1234')
        sock.shutdown(socket.SHUT_WR)
        assert reader.read() == b''
        reader.close()
    assert client.get('partial') is None


def test_many_idle_process_clients_do_not_exhaust_server(service):
    clients = [service.client() for _ in range(70)]
    try:
        for index, connection in enumerate(clients):
            assert connection.set('value', index)
        assert all(connection.get('value') == str(index).encode() for index, connection in enumerate(clients))
    finally:
        for connection in clients:
            connection.close()


def test_idle_pool_socket_is_replaced_before_mutation(client):
    client.set('value', 0)
    connection, reader, _ = client._pool.get_nowait()
    client._pool.put_nowait((connection, reader, time.monotonic() - 11))
    assert client.incrby('value') == 1
    assert connection.fileno() == -1


def test_pool_contention_keeps_bound_and_exact_totals(client):
    with ThreadPoolExecutor(max_workers=24) as pool:
        list(pool.map(lambda _: client.incrby('count'), range(240)))
    assert client.get('count') == b'240'
    assert 1 <= client._pool.qsize() <= 8


def test_high_numbered_descriptor_pool_reuse(client):
    if fcntl is None or resource is None:
        pytest.skip('Unix descriptor-number limit regression')
    if resource.getrlimit(resource.RLIMIT_NOFILE)[0] <= 1100:
        pytest.skip('Host descriptor limit is below the regression range')
    client.set('value', 0)
    connection, reader, returned_at = client._pool.get_nowait()
    duplicate = socket.socket(fileno=fcntl.fcntl(connection.fileno(), fcntl.F_DUPFD, 1100))
    duplicate.settimeout(client.timeout)
    reader.close()
    connection.close()
    client._pool.put_nowait((duplicate, duplicate.makefile('rb'), returned_at))
    assert client.incrby('value') == 1
    assert client.incrby('value') == 2


def test_partial_event_never_yields_corrupted_bytes():
    async def exercise():
        reader = asyncio.StreamReader()
        reader.feed_data(b'{"channel":"events:x","payload_bytes":8}\n1234')
        reader.feed_eof()
        class Writer:
            # Only the close contract is used after the simulated mid-frame EOF.
            def close(self):
                pass
            async def wait_closed(self):
                pass
        subscription = client_module.Subscription(reader, Writer())
        with pytest.raises(CoordinationConnectionError, match='incomplete'):
            await anext(subscription.iter())
    asyncio.run(exercise())


def test_descriptor_exhaustion_rejects_then_recovers(binary):
    if resource is None:
        pytest.skip('Unix descriptor limit regression')
    hard = resource.getrlimit(resource.RLIMIT_NOFILE)[1]
    if hard != resource.RLIM_INFINITY and hard < 64:
        pytest.skip('Host hard limit is too low for the child-only regression')
    server = Service(binary, descriptor_limit=64)
    held = []
    probe = server.client()
    try:
        probe.connect()
        probe.close()
        # Each successful handshake holds one slot, without ever sending a body.
        # A low-limit server must still acknowledge explicit non-execution on exhaustion.
        rejected = False
        for _ in range(70):
            connection = socket.create_connection(probe.address, timeout=2)
            held.append(connection)
            connection.sendall(probe._frame('get', {'key': 'unused'}).split(b'\n', 1)[0] + b'\n')
            reader = connection.makefile('rb')
            frame = reader.readline()
            if not frame:
                server.stop()
                pytest.fail(f'Early EOF after {len(held)} sockets: {server.error}')
            response = json.loads(frame)
            reader.close()
            if not response['ok']:
                assert response['error'].startswith('busy: operating system')
                rejected = True
                break
        assert rejected
        for connection in held:
            connection.close()
        held.clear()
        # Closing peers wakes their server handlers asynchronously.
        deadline = time.monotonic() + 5
        while True:
            try:
                assert probe.set('recovered', 'yes')
                break
            except client_module.CoordinationBusyError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(.02)
    finally:
        for connection in held:
            connection.close()
        probe.close()
        server.stop()


def test_closed_error_log_does_not_prevent_startup(binary):
    if resource is None:
        pytest.skip('Unix descriptor limit forces the startup diagnostic')
    hard = resource.getrlimit(resource.RLIMIT_NOFILE)[1]
    if hard != resource.RLIM_INFINITY and hard < 64:
        pytest.skip('Host hard limit is too low for the child-only regression')
    # A reduced child limit deterministically emits a diagnostic. With no reader,
    # stderr writes fail just as they do after a piped supervisor disappears.
    reader, writer = os.pipe()
    os.close(reader)
    try:
        server = Service(binary, descriptor_limit=64, stderr=writer)
    finally:
        os.close(writer)
    client = None
    try:
        client = server.client()
        assert client.set('survived-log-failure', 'yes')
        assert client.get('survived-log-failure') == b'yes'
    finally:
        if client is not None:
            client.close()
        server.stop()


def test_low_descriptor_subscription_cap_preserves_rpc_capacity(binary):
    if resource is None:
        pytest.skip('Unix descriptor limit regression')
    hard = resource.getrlimit(resource.RLIMIT_NOFILE)[1]
    if hard != resource.RLIM_INFINITY and hard < 32:
        pytest.skip('Host hard limit is too low for the child-only regression')
    server = Service(binary, descriptor_limit=32)
    client = server.client()
    async def exercise():
        asynchronous = AsyncClient(client)
        try:
            # Soft32 minus16 runtime headroom gives16 connections. Subscriptions
            # get at most half, leaving eight connection slots available for RPCs.
            for index in range(8):
                await asynchronous.psubscribe(f'events:{index}:*')
            with pytest.raises(CoordinationError, match='subscription limit'):
                await asynchronous.psubscribe('events:overflow:*')
            assert client.publish('events:0:probe', b'works') == 1
            assert client.set('rpc', 'works')
        finally:
            for pattern in list(asynchronous._subscriptions):
                await asynchronous.punsubscribe(pattern)
    try:
        asyncio.run(exercise())
    finally:
        client.close()
        server.stop()


@pytest.mark.parametrize('timeout', [None, 0, -1, True, float('inf'), float('nan')])
def test_blocking_or_invalid_timeout_is_rejected_before_io(timeout):
    with pytest.raises(ValueError, match='timeout'):
        Client('127.0.0.1', 1, 'x' * 32, 'test', timeout=timeout)
