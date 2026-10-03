"""Small standard-library client for Jesse's native coordination service.

The wire protocol uses versioned JSON control frames and raw binary payloads. Familiar method names keep the
existing call sites small; only the operations Jesse uses are supported. Only explicit
pre-execution busy rejections are retried; after a network failure a mutation
may have committed, so it is never retried automatically.
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import queue
import select
import socket
import threading
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any


# Must match the server bounds for JSON metadata and raw binary payloads.
MAX_FRAME = 16 * 1024 * 1024
MAX_HEADER = 4096
MAX_PAYLOAD = 8 * 1024 * 1024
# Server subscriptions send a heartbeat every two seconds. Six seconds tolerates
# scheduling delays while still detecting an unresponsive service promptly.
SUBSCRIPTION_TIMEOUT = 6.0


class CoordinationConnectionError(ConnectionError):
    """The service is unavailable, or its generation changed after a restart."""


class CoordinationBusyError(CoordinationConnectionError):
    """Transient rejection; the server did not apply this operation."""


class CoordinationError(RuntimeError):
    """The service rejected an authenticated request."""


class CoordinationCapacityError(CoordinationError):
    """An explicit size or resident-state limit rejected the operation."""


class CoordinationSizeError(ValueError):
    """An encoded request exceeds a protocol bound before transmission."""


class LockError(CoordinationError):
    """A lock could not be acquired or is no longer owned by this caller."""


def _bytes(value: str | bytes | int | float) -> bytes:
    """Keep binary payloads intact and encode scalar values consistently."""
    if isinstance(value, bytes):
        return value
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise TypeError('Shared values must be bytes, strings, or numbers')
    return str(value).encode('utf-8')


def _ttl_ms(seconds: float) -> int:
    """Round up so a positive sub-millisecond lifetime never means no expiry."""
    if isinstance(seconds, bool) or not math.isfinite(seconds) or seconds <= 0:
        raise ValueError('Expiry must be a finite positive number')
    return math.ceil(seconds * 1000)


def _response(frame: bytes) -> Any:
    """Decode one bounded reply without exposing request credentials in errors."""
    if not frame or len(frame) > MAX_FRAME or not frame.endswith(b'\n'):
        raise CoordinationConnectionError('Coordinator closed the connection or sent an invalid frame')
    try:
        response = json.loads(frame)
    except (ValueError, UnicodeError) as exc:
        raise CoordinationConnectionError('Coordinator sent invalid JSON') from exc
    if not isinstance(response, dict) or not isinstance(response.get('ok'), bool):
        raise CoordinationConnectionError('Coordinator sent an invalid response')
    if not response['ok']:
        error = str(response.get('error', 'Unknown coordinator error'))
        if error.startswith('busy:'):
            raise CoordinationBusyError(error)
        if error.startswith('restart:'):
            raise CoordinationConnectionError(error)
        if error.startswith('capacity:'):
            raise CoordinationCapacityError(error)
        raise CoordinationError(error)
    return response.get('value')


def _socket_readable(connection: socket.socket) -> bool:
    """Retire EOF/unexpected data without descriptor-number limits or poll setup."""
    try:
        timeout = connection.gettimeout()
        if timeout is None or timeout <= 0:
            return True
        if os.name == 'posix':
            # Positive Python socket timeouts use nonblocking OS descriptors.
            # No duplicated/inherited holder may change that shared OS flag;
            # clients reject forked use and never expose their pooled sockets.
            # RPC sockets are exclusively owned here and never receive unsolicited
            # data: any successful read (including EOF) means discard this socket.
            os.read(connection.fileno(), 1)
            return True
        # Windows socket handles are not CRT file descriptors; select on one
        # socket avoids its socket-count limit and never consumes response data.
        return bool(select.select([connection], [], [], 0)[0])
    except BlockingIOError:
        return False
    except (OSError, ValueError):
        return True


class Client:
    """Share values across processes using a bounded process-local connection pool.

    Generation pinning prevents a restarted empty service from accepting work
    under locks that belonged to its predecessor. Recreate the whole Jesse
    instance after a coordinator restart; do not transparently reset this pin.
    """

    def __init__(self, host: str, port: int, token: str, namespace: str,
                 timeout: float = 2.0, generation: str | None = None):
        if host not in ('127.0.0.1', '::1'):
            raise ValueError('Coordinator host must be a loopback IP address')
        if len(token.encode()) < 32 or not namespace or len(namespace.encode()) > 128:
            raise ValueError('Coordinator requires a token of at least 32 bytes and a namespace of at most 128 bytes')
        # Idle-socket probing depends on timeout-mode (nonblocking) descriptors.
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError('Coordinator timeout must be a finite positive number')
        self.address = (host, port)
        self.token = token
        self.namespace = namespace
        self.timeout = timeout
        self.generation = generation
        self._reset_pool()

    def _reset_pool(self) -> None:
        """Each process owns at most eight RPC connections; subscriptions are separate."""
        self._pid = os.getpid()
        self._handshake_lock = threading.Lock()
        self._header_cache = {}
        self._pool = queue.LifoQueue(maxsize=8)
        self._slots = threading.BoundedSemaphore(8)

    def close(self) -> None:
        """Release cached idle sockets. In-flight calls retain their own ownership."""
        while True:
            try:
                connection, reader, _ = self._pool.get_nowait()
            except queue.Empty:
                break
            reader.close()
            connection.close()

    def _parts(self, op: str, args: dict[str, Any]) -> tuple[bytes, bytes]:
        """Bound and encode metadata separately from the unexpanded byte payload."""
        args = args.copy()
        payload = args.pop('_payload', b'')
        if not isinstance(payload, bytes):
            raise TypeError('Coordinator payload must be bytes')
        if len(payload) > MAX_PAYLOAD:
            raise CoordinationSizeError('Coordinator binary payload exceeds 8 MiB')
        identity = (self.generation, self.namespace, self.token, len(payload))
        cached = self._header_cache.get(op)
        if cached is not None and cached[0] == identity:
            header = cached[1]
        else:
            header = json.dumps({
                'version': 2, 'token': self.token, 'namespace': self.namespace,
                'generation': self.generation, 'op': op, 'payload_bytes': len(payload),
            }, separators=(',', ':'), ensure_ascii=True).encode() + b'\n'
            # Keep only one recent header per operation. Bound unknown operation
            # names too, so dynamic callers cannot grow this optimization forever.
            if len(self._header_cache) >= 32:
                self._header_cache.clear()
            self._header_cache[op] = (identity, header)
        frame = json.dumps(args, separators=(',', ':'), ensure_ascii=True).encode() + b'\n'
        if len(header) > MAX_HEADER:
            raise CoordinationSizeError('Coordinator header exceeds 4 KiB')
        if len(frame) > MAX_FRAME:
            raise CoordinationSizeError('Coordinator request metadata exceeds 16 MiB')
        # Binary data follows length-delimited metadata without hex/JSON expansion.
        return header, frame + payload

    def _frame(self, op: str, args: dict[str, Any]) -> bytes:
        """Encode a complete request for raw protocol diagnostics."""
        return b''.join(self._parts(op, args))

    def _exchange(self, op: str, args: dict[str, Any]) -> Any:
        """Exclusively borrow one socket and recycle only fully consumed replies."""
        header, body = self._parts(op, args)
        if not self._slots.acquire(timeout=self.timeout):
            raise CoordinationBusyError('busy: local connection pool is occupied')
        connection = reader = None
        reusable = False
        fresh = True
        try:
            while True:
                try:
                    connection, reader, returned_at = self._pool.get_nowait()
                except queue.Empty:
                    connection = socket.create_connection(self.address, timeout=self.timeout)
                    connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    reader = connection.makefile('rb')
                    break
                # The server idles out after 30 seconds. Retire at ten seconds,
                # and reject EOF/unsolicited data before submitting a mutation.
                if time.monotonic() - returned_at < 10 and not _socket_readable(connection):
                    fresh = False
                    break
                reader.close()
                connection.close()
                connection = reader = None
            if fresh:
                connection.sendall(header)
                if _response(reader.readline(MAX_FRAME + 1)) != 'ready':
                    raise CoordinationConnectionError('Invalid request acknowledgement')
                connection.sendall(body)
            else:
                # An authenticated connection has no early auth/body race. One
                # write avoids a second send for small requests. Above 64 KiB,
                # avoid another payload copy just to combine the header and body.
                if len(header) + len(body) < 65536:
                    connection.sendall(header + body)
                else:
                    connection.sendall(header)
                    connection.sendall(body)
            result = _response(reader.readline(MAX_FRAME + 1))
            if op == 'get' and result is not None:
                length = result.get('payload_bytes') if isinstance(result, dict) else None
                if type(length) is not int or not 0 <= length <= MAX_PAYLOAD:
                    raise CoordinationConnectionError('Invalid binary response length')
                result = reader.read(length)
                if len(result) != length:
                    raise CoordinationConnectionError('Incomplete binary response')
            reusable = True
            return result
        except CoordinationConnectionError:
            raise
        except OSError as exc:
            raise CoordinationConnectionError('Coordinator request failed; mutation outcome may be unknown') from exc
        finally:
            if connection is not None:
                if reusable:
                    self._pool.put_nowait((connection, reader, time.monotonic()))
                else:
                    if reader is not None:
                        reader.close()
                    connection.close()
            self._slots.release()

    def connect(self) -> str:
        """Negotiate once; the lock only protects simultaneous first-use handshakes."""
        if self._pid != os.getpid():
            # Reusing inherited Python I/O locks after a threaded fork can
            # deadlock. Jesse uses spawned workers with freshly imported clients.
            raise CoordinationConnectionError('Create a fresh coordinator client after fork')
        if self.generation is not None:
            return self.generation
        with self._handshake_lock:
            if self.generation is None:
                response = self._exchange('hello', {})
                if not isinstance(response, dict) or response.get('protocol') != 2 or not isinstance(response.get('generation'), str):
                    raise CoordinationConnectionError('Coordinator protocol negotiation failed')
                self.generation = response['generation']
        assert self.generation is not None
        return self.generation

    def request(self, op: str, **args: Any) -> Any:
        # Three attempts absorb short capacity spikes (10/20 ms backoff). Only
        # an explicit busy rejection guarantees the operation was not applied.
        for attempt in range(3):
            try:
                self.connect()
                return self._exchange(op, args)
            except CoordinationBusyError:
                if attempt == 2:
                    raise
                time.sleep(0.01 * (attempt + 1))

    def get(self, key: str) -> bytes | None:
        return self.request('get', key=key)

    def set(self, key: str, value: str | bytes | int | float, ex: float | None = None) -> bool:
        return bool(self.request('put', key=key, _payload=_bytes(value), ttl_ms=_ttl_ms(ex) if ex is not None else None))

    def setex(self, key: str, time: float, value: str | bytes | int | float) -> bool:
        return self.set(key, value, ex=time)

    def delete(self, key: str) -> int:
        return int(self.request('delete', key=key))

    def incrby(self, key: str, amount: int = 1) -> int:
        return int(self.request('increment', key=key, amount=amount))

    def expire(self, key: str, seconds: float) -> bool:
        return bool(self.request('expire', key=key, ttl_ms=_ttl_ms(seconds)))

    def ttl(self, key: str) -> int:
        return int(self.request('ttl', key=key))

    def sadd(self, key: str, *members: str | bytes) -> int:
        return int(self.request('add_members', key=key, members=[_bytes(m).hex() for m in members]))

    def srem(self, key: str, *members: str | bytes) -> int:
        return int(self.request('remove_members', key=key, members=[_bytes(m).hex() for m in members]))

    def smembers(self, key: str) -> set[bytes]:
        return {bytes.fromhex(m) for m in self.request('members', key=key)}

    def sismember(self, key: str, member: str | bytes) -> bool:
        return bool(self.request('contains', key=key, member=_bytes(member).hex()))

    def publish(self, channel: str, message: str | bytes) -> int:
        return int(self.request('publish', channel=channel, _payload=_bytes(message)))

    def lock(self, name: str, timeout: float, blocking_timeout: float = 0) -> 'Lock':
        return Lock(self, name, timeout, blocking_timeout)


class Lock:
    """Expiring lock with atomic owner-checked release, without server-side Lua."""

    def __init__(self, client: Client, name: str, timeout: float, blocking_timeout: float):
        self.client = client
        self.name = name
        self.ttl_ms = _ttl_ms(timeout)
        if not math.isfinite(blocking_timeout) or blocking_timeout < 0:
            raise ValueError('Lock wait must be finite and nonnegative')
        self.wait = blocking_timeout
        self._local = threading.local()

    def acquire(self) -> bool:
        if getattr(self._local, 'owner', None) is not None:
            raise LockError('Lock is not reentrant')
        owner = uuid.uuid4().hex
        deadline = time.monotonic() + self.wait
        while True:
            try:
                acquired = self.client.request('acquire_lock', key=self.name, owner=owner, ttl_ms=self.ttl_ms)
            except CoordinationBusyError:
                # Only this explicit rejection is known not to have acquired a
                # lease. Retry within the caller's wait, never after ambiguity.
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise
                time.sleep(min(0.05, remaining))
                continue
            except CoordinationConnectionError:
                # A lost reply may follow a successful acquire. Owner-checked
                # cleanup cannot release another caller's lease; never retry acquire.
                try:
                    self.client.request('release_lock', key=self.name, owner=owner)
                except (CoordinationConnectionError, CoordinationError):
                    pass
                raise
            if acquired:
                self._local.owner = owner
                return True
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            # Fifty milliseconds bounds lock polling without busy-waiting.
            time.sleep(min(0.05, remaining))

    def release(self) -> None:
        owner = getattr(self._local, 'owner', None)
        if owner is None:
            raise LockError('Lock is not owned by this caller')
        try:
            released = self.client.request('release_lock', key=self.name, owner=owner)
        except CoordinationBusyError:
            # All bounded attempts were rejected before execution. Retain the
            # token so an explicit caller retry can still release its own lease.
            raise
        except BaseException:
            self._local.owner = None
            raise
        self._local.owner = None
        if not released:
            raise LockError('Lock expired or ownership changed')

    def __enter__(self) -> 'Lock':
        if not self.acquire():
            raise LockError('Timed out waiting for shared lock')
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        try:
            self.release()
        except (CoordinationError, CoordinationConnectionError) as release_error:
            if exc_value is None:
                raise
            # Preserve the actual provider/body error if lease release also fails.
            if hasattr(exc_value, 'add_note'):
                exc_value.add_note(str(release_error))


class Subscription:
    """One event stream; disconnects are explicit and never imply event replay."""

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self.reader = reader
        self.writer = writer

    async def iter(self) -> AsyncIterator[tuple[bytes, bytes]]:
        try:
            while True:
                frame = await asyncio.wait_for(self.reader.readline(), SUBSCRIPTION_TIMEOUT)
                if not frame or len(frame) > MAX_FRAME:
                    raise CoordinationConnectionError('Event subscription disconnected')
                try:
                    event = json.loads(frame)
                except ValueError as exc:
                    raise CoordinationConnectionError('Invalid event frame') from exc
                if not isinstance(event, dict):
                    raise CoordinationConnectionError('Invalid event frame')
                if event.get('heartbeat'):
                    continue
                if 'ok' in event:
                    _response(frame)
                    continue
                try:
                    channel, length = event['channel'].encode(), event['payload_bytes']
                    if type(length) is not int or not 0 <= length <= MAX_PAYLOAD:
                        raise ValueError('Invalid event payload length')
                    value = await asyncio.wait_for(self.reader.readexactly(length), SUBSCRIPTION_TIMEOUT)
                except (KeyError, AttributeError, TypeError, ValueError, asyncio.IncompleteReadError) as exc:
                    raise CoordinationConnectionError('Invalid or incomplete event payload') from exc
                yield channel, value
        finally:
            await self.close()

    async def close(self) -> None:
        self.writer.close()
        try:
            await self.writer.wait_closed()
        except OSError:
            pass


class AsyncClient:
    """Async facade with dedicated streams for subscriptions and bounded RPC timeouts."""

    def __init__(self, client: Client):
        self.client = client
        self._subscriptions: dict[str, Subscription] = {}

    async def publish(self, channel: str, message: str | bytes) -> int:
        return await asyncio.to_thread(self.client.publish, channel, message)

    async def psubscribe(self, pattern: str) -> tuple[Subscription]:
        # Jesse subscribes to APP_PORT:channel:*. Full Redis glob semantics are
        # deliberately outside this custom protocol, so unsupported patterns fail.
        if not pattern.endswith('*') or any(c in pattern[:-1] for c in '*?[]'):
            raise ValueError('Only literal prefixes followed by * are supported')
        await self.punsubscribe(pattern)
        await asyncio.to_thread(self.client.connect)
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(*self.client.address, limit=MAX_FRAME + 1), self.client.timeout,
        )
        try:
            header, body = self.client._parts('subscribe', {'prefix': pattern[:-1]})
            writer.write(header)
            await asyncio.wait_for(writer.drain(), self.client.timeout)
            if _response(await asyncio.wait_for(reader.readline(), self.client.timeout)) != 'ready':
                raise CoordinationConnectionError('Invalid subscription acknowledgement')
            writer.write(body)
            await asyncio.wait_for(writer.drain(), self.client.timeout)
            _response(await asyncio.wait_for(reader.readline(), self.client.timeout))
        except BaseException:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass
            raise
        subscription = Subscription(reader, writer)
        self._subscriptions[pattern] = subscription
        return (subscription,)

    async def punsubscribe(self, pattern: str) -> None:
        subscription = self._subscriptions.pop(pattern, None)
        if subscription is not None:
            await subscription.close()
