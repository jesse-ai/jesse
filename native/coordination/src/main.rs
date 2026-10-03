//! Authenticated, local-only coordination. State is intentionally in-memory;
//! a server generation identifies restarts so existing clients cannot silently
//! resume mutations after losing their locks and shared state.

use serde::Deserialize;
use serde_json::{json, Value};
use std::collections::{HashMap, HashSet};
use std::io::{self, BufRead, BufReader, Read, Write};
use std::net::{SocketAddr, TcpListener, TcpStream};
use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
use std::sync::{mpsc, Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

// Chart snapshots can be several MiB. Other bounds independently cap concurrent
// connections, resident state, and queued event bytes; there is no silent eviction.
const MAX_FRAME: usize = 16 * 1024 * 1024;
const MAX_STATE: usize = 128 * 1024 * 1024;
const MAX_KEYS: usize = 100_000;
// Persistent pools retain idle sockets. Allow high-core-count worker processes
// plus the API pool and subscribers; the idle deadline eventually reclaims them.
const MAX_CLIENTS: usize = 256;
// Long-lived subscriptions must leave connection slots for publishers and RPCs.
const MAX_SUBSCRIBERS: usize = 32;
const MAX_HEADER: usize = 4096;
const MAX_PAYLOAD: usize = 8 * 1024 * 1024;
const MAX_EVENT: usize = MAX_FRAME - MAX_HEADER;
// Shared frames count once globally, irrespective of subscriber fan-out.
const MAX_QUEUED: usize = 64 * 1024 * 1024;
// A single slow consumer cannot retain the entire global frame budget.
const MAX_SUBSCRIBER_QUEUED: usize = 16 * 1024 * 1024;
// Charge queue-node overhead as well as encoded payload bytes.
const EVENT_OVERHEAD: usize = 128;
// Idle subscription writes detect dead peers without retaining them forever.
const HEARTBEAT: Duration = Duration::from_secs(2);
// Only a small loopback header is read during rejection; keep the accept loop responsive.
const REJECTION_TIMEOUT: Duration = Duration::from_millis(20);
// Repeated OS failures share one diagnostic per ten seconds to bound log growth.
// The supervisor must still drain stderr or redirect it to a file.
const ERROR_LOG_INTERVAL: Duration = Duration::from_secs(10);

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Request {
    version: u8,
    token: String,
    namespace: String,
    op: String,
    #[serde(default)]
    generation: Option<String>,
    #[serde(skip)]
    args: Value,
    #[serde(default)]
    payload_bytes: usize,
    #[serde(skip)]
    payload: Arc<Vec<u8>>,
}

#[derive(Clone)]
enum Data {
    Bytes(Arc<Vec<u8>>),
    Set(HashSet<String>),
    Lock(String),
}

#[derive(Clone)]
struct Entry {
    data: Data,
    expires: Option<Instant>,
}

impl Entry {
    fn size(&self) -> usize {
        // Include conservative per-entry/member overhead, not only payload bytes.
        128 + match &self.data {
            Data::Bytes(s) => s.len(),
            Data::Lock(s) => s.len(),
            Data::Set(values) => values.iter().map(|s| s.len() + 64).sum(),
        }
    }
}

struct SharedFrame {
    bytes: Vec<u8>,
    queued: Arc<AtomicUsize>,
}
impl Drop for SharedFrame {
    fn drop(&mut self) {
        self.queued.fetch_sub(self.bytes.len(), Ordering::SeqCst);
    }
}

struct Event {
    frame: Arc<SharedFrame>,
    queued: Arc<AtomicUsize>,
}
impl Drop for Event {
    fn drop(&mut self) {
        self.queued
            .fetch_sub(self.frame.bytes.len() + EVENT_OVERHEAD, Ordering::SeqCst);
    }
}

struct Subscriber {
    namespace: String,
    prefix: String,
    tx: mpsc::Sender<Event>,
    alive: Arc<AtomicBool>,
    queued: Arc<AtomicUsize>,
}

#[derive(Default)]
struct State {
    entries: HashMap<(String, String), Entry>,
    bytes: usize,
    subscribers: Vec<Subscriber>,
}

impl State {
    fn remove(&mut self, key: &(String, String)) -> bool {
        if let Some(old) = self.entries.remove(key) {
            self.bytes -= old.size() + key.0.len() + key.1.len();
            true
        } else {
            false
        }
    }

    fn purge(&mut self) {
        let now = Instant::now();
        self.entries
            .retain(|_, e| e.expires.is_none_or(|until| until > now));
        self.bytes = self
            .entries
            .iter()
            .map(|(k, e)| k.0.len() + k.1.len() + e.size())
            .sum();
        self.subscribers.retain(|s| s.alive.load(Ordering::SeqCst));
    }

    fn insert(&mut self, key: (String, String), entry: Entry) -> Result<(), String> {
        let old_size = self
            .entries
            .get(&key)
            .map_or(0, |e| e.size() + key.0.len() + key.1.len());
        let new_size = entry.size() + key.0.len() + key.1.len();
        // Every stored value/set must remain retrievable in one bounded reply.
        if entry.size() > MAX_FRAME - 1024
            || self.bytes - old_size + new_size > MAX_STATE
            || (!self.entries.contains_key(&key) && self.entries.len() >= MAX_KEYS)
        {
            return Err("capacity: shared-state budget exceeded".into());
        }
        self.bytes = self.bytes - old_size + new_size;
        self.entries.insert(key, entry);
        Ok(())
    }
}

struct Server {
    state: Mutex<State>,
    token: String,
    generation: String,
    clients: AtomicUsize,
    max_clients: usize,
    queued: Arc<AtomicUsize>,
}

fn text<'a>(args: &'a Value, name: &str) -> Result<&'a str, String> {
    args.get(name)
        .and_then(Value::as_str)
        .ok_or_else(|| format!("invalid: missing string {name}"))
}

fn key_text<'a>(args: &'a Value, name: &str) -> Result<&'a str, String> {
    let value = text(args, name)?;
    if value.len() > 1024 {
        return Err("invalid: key/channel/prefix exceeds 1024 bytes".into());
    }
    Ok(value)
}

fn bytes_text<'a>(args: &'a Value, name: &str) -> Result<&'a str, String> {
    let value = text(args, name)?;
    if value.len() % 2 != 0 || !value.bytes().all(|b| b.is_ascii_hexdigit()) {
        return Err("invalid: payload must be hexadecimal bytes".into());
    }
    Ok(value)
}

fn expiry(args: &Value) -> Result<Option<Instant>, String> {
    match args.get("ttl_ms") {
        None | Some(Value::Null) => Ok(None),
        Some(v) => {
            let ms = v
                .as_u64()
                .filter(|v| *v > 0)
                .ok_or("invalid: ttl_ms must be a positive integer")?;
            Instant::now()
                .checked_add(Duration::from_millis(ms))
                .map(Some)
                .ok_or("invalid: TTL too large".into())
        }
    }
}

fn decode_integer(bytes: &[u8]) -> Result<i64, String> {
    std::str::from_utf8(bytes)
        .map_err(|_| "invalid: value is not an integer")?
        .parse()
        .map_err(|_| "invalid: value is not an integer".into())
}

fn encode_integer(value: i64) -> Arc<Vec<u8>> {
    Arc::new(value.to_string().into_bytes())
}

impl Server {
    fn authenticate(&self, req: &Request) -> Result<(), String> {
        // Compare all equal-length token bytes rather than leaking matching prefixes.
        if req.token.len() != self.token.len()
            || req
                .token
                .bytes()
                .zip(self.token.bytes())
                .fold(0u8, |a, (b, c)| a | (b ^ c))
                != 0
        {
            return Err("auth: invalid credentials".into());
        }
        if req.version != 2 || req.namespace.is_empty() || req.namespace.len() > 128 {
            return Err("invalid: unsupported protocol or namespace".into());
        }
        if req.payload_bytes > MAX_PAYLOAD {
            return Err("capacity: binary payload exceeds 8 MiB".into());
        }
        if req.op != "hello" && req.generation.as_deref() != Some(self.generation.as_str()) {
            return Err(
                "restart: coordinator generation changed; restart the Jesse instance".into(),
            );
        }
        Ok(())
    }

    fn execute(&self, req: &Request) -> Result<Value, String> {
        self.authenticate(req)?;
        if req.op == "hello" {
            return Ok(json!({"generation": self.generation, "protocol": 2}));
        }
        if req.op == "publish" {
            return self.publish(req);
        }
        let mut state = self
            .state
            .lock()
            .map_err(|_| "internal: state unavailable")?;
        let key = (
            req.namespace.clone(),
            key_text(&req.args, "key")?.to_owned(),
        );
        if state
            .entries
            .get(&key)
            .is_some_and(|e| e.expires.is_some_and(|t| t <= Instant::now()))
        {
            state.remove(&key);
        }
        // Active-worker checks are read-only and frequent. Borrow the set rather
        // than cloning every member for a single membership lookup.
        if req.op == "contains" {
            let member = bytes_text(&req.args, "member")?.to_ascii_lowercase();
            return match state.entries.get(&key) {
                None => Ok(json!(false)),
                Some(Entry {
                    data: Data::Set(values),
                    ..
                }) => Ok(json!(values.contains(&member))),
                _ => Err("type: expected a set".into()),
            };
        }
        let current = state.entries.get(&key).cloned();
        match req.op.as_str() {
            "put" => {
                if req.args.get("value").is_some() {
                    return Err("invalid: byte values must use the binary payload".into());
                }
                let value = req.payload.clone();
                let expires = expiry(&req.args)?;
                state.insert(
                    key,
                    Entry {
                        data: Data::Bytes(value),
                        expires,
                    },
                )?;
                Ok(json!(true))
            }
            "delete" => Ok(json!(state.remove(&key) as u8)),
            "increment" => {
                let amount = req
                    .args
                    .get("amount")
                    .and_then(Value::as_i64)
                    .ok_or("invalid: amount must be an integer")?;
                let (old, expires) = match current {
                    None => (0, None),
                    Some(Entry {
                        data: Data::Bytes(s),
                        expires,
                    }) => (decode_integer(&s)?, expires),
                    _ => return Err("type: expected a byte value".into()),
                };
                let new = old.checked_add(amount).ok_or("invalid: integer overflow")?;
                state.insert(
                    key,
                    Entry {
                        data: Data::Bytes(encode_integer(new)),
                        expires,
                    },
                )?;
                Ok(json!(new))
            }
            "expire" => {
                let expires = expiry(&req.args)?.ok_or("invalid: expiry is required")?;
                if let Some(entry) = state.entries.get_mut(&key) {
                    entry.expires = Some(expires);
                    Ok(json!(true))
                } else {
                    Ok(json!(false))
                }
            }
            "ttl" => Ok(json!(match current {
                None => -2,
                Some(Entry { expires: None, .. }) => -1,
                Some(Entry {
                    expires: Some(t), ..
                }) => t.saturating_duration_since(Instant::now()).as_secs() as i64,
            })),
            "members" | "add_members" | "remove_members" => {
                let (mut values, expires) = match current {
                    None => (HashSet::new(), None),
                    Some(Entry {
                        data: Data::Set(values),
                        expires,
                    }) => (values, expires),
                    _ => return Err("type: expected a set".into()),
                };
                if req.op == "members" {
                    return Ok(json!(values));
                }
                let members = req
                    .args
                    .get("members")
                    .and_then(Value::as_array)
                    .ok_or("invalid: members must be an array")?;
                let mut changed = 0;
                for member in members {
                    let member = member.as_str().ok_or("invalid: member must be a string")?;
                    if member.len() % 2 != 0 || !member.bytes().all(|b| b.is_ascii_hexdigit()) {
                        return Err("invalid: member must be hexadecimal bytes".into());
                    }
                    let member = member.to_ascii_lowercase();
                    changed += if req.op == "add_members" {
                        values.insert(member)
                    } else {
                        values.remove(&member)
                    } as usize;
                }
                if values.is_empty() {
                    state.remove(&key);
                } else {
                    state.insert(
                        key,
                        Entry {
                            data: Data::Set(values),
                            expires,
                        },
                    )?;
                }
                Ok(json!(changed))
            }
            "acquire_lock" => {
                let owner = text(&req.args, "owner")?;
                if owner.is_empty() || owner.len() > 128 {
                    return Err("invalid: invalid lock owner".into());
                }
                let expires = expiry(&req.args)?.ok_or("invalid: locks require a TTL")?;
                if current.is_some() {
                    return Ok(json!(false));
                }
                state.insert(
                    key,
                    Entry {
                        data: Data::Lock(owner.into()),
                        expires: Some(expires),
                    },
                )?;
                Ok(json!(true))
            }
            "release_lock" => {
                let owner = text(&req.args, "owner")?;
                let owned = matches!(current, Some(Entry { data: Data::Lock(ref token), .. }) if token == owner);
                if owned {
                    state.remove(&key);
                }
                Ok(json!(owned))
            }
            _ => Err("unsupported: unknown operation".into()),
        }
    }

    fn get_value(&self, req: &Request) -> Result<Option<Arc<Vec<u8>>>, String> {
        self.authenticate(req)?;
        let key = (
            req.namespace.clone(),
            key_text(&req.args, "key")?.to_owned(),
        );
        let mut state = self
            .state
            .lock()
            .map_err(|_| "internal: state unavailable")?;
        if state
            .entries
            .get(&key)
            .is_some_and(|e| e.expires.is_some_and(|t| t <= Instant::now()))
        {
            state.remove(&key);
        }
        match state.entries.get(&key) {
            None => Ok(None),
            Some(Entry {
                data: Data::Bytes(value),
                ..
            }) => Ok(Some(value.clone())),
            _ => Err("type: expected a byte value".into()),
        }
    }

    fn publish(&self, req: &Request) -> Result<Value, String> {
        let channel = key_text(&req.args, "channel")?;
        if req.args.get("value").is_some() {
            return Err("invalid: events must use the binary payload".into());
        }
        let value = &req.payload;
        let mut frame =
            serde_json::to_vec(&json!({"channel": channel, "payload_bytes": value.len()}))
                .map_err(|_| "internal: serialization")?;
        frame.push(b'\n');
        frame.extend_from_slice(value);
        if frame.len() > MAX_EVENT {
            return Err("capacity: event exceeds the frame budget".into());
        }
        let mut state = self
            .state
            .lock()
            .map_err(|_| "internal: state unavailable")?;
        if !state.subscribers.iter().any(|sub| {
            sub.alive.load(Ordering::SeqCst)
                && sub.namespace == req.namespace
                && channel.starts_with(&sub.prefix)
        }) {
            return Ok(json!(0));
        }
        // Exhausting aggregate capacity rejects the publish explicitly. It must
        // never evict an unrelated healthy subscriber to make room.
        #[allow(deprecated, reason = "MSRV 1.82 predates try_update")]
        self.queued
            .fetch_update(Ordering::SeqCst, Ordering::SeqCst, |n| {
                (n + frame.len() <= MAX_QUEUED).then_some(n + frame.len())
            })
            .map_err(|_| "busy: global event queue budget exceeded")?;
        let frame = Arc::new(SharedFrame {
            bytes: frame,
            queued: self.queued.clone(),
        });
        let mut delivered = 0;
        // One state lock serializes delivery order to every subscriber. A lagging
        // subscriber is disconnected instead of silently losing arbitrary events.
        state.subscribers.retain(|sub| {
            if !sub.alive.load(Ordering::SeqCst) {
                return false;
            }
            if sub.namespace != req.namespace || !channel.starts_with(&sub.prefix) {
                return true;
            }
            #[allow(deprecated, reason = "MSRV 1.82 predates try_update")]
            let reserved = sub
                .queued
                .fetch_update(Ordering::SeqCst, Ordering::SeqCst, |n| {
                    (n + frame.bytes.len() + EVENT_OVERHEAD <= MAX_SUBSCRIBER_QUEUED)
                        .then_some(n + frame.bytes.len() + EVENT_OVERHEAD)
                })
                .is_ok();
            if !reserved {
                sub.alive.store(false, Ordering::SeqCst);
                return false;
            }
            let event = Event {
                frame: frame.clone(),
                queued: sub.queued.clone(),
            };
            match sub.tx.send(event) {
                Ok(()) => {
                    delivered += 1;
                    true
                }
                Err(_) => {
                    sub.alive.store(false, Ordering::SeqCst);
                    false
                }
            }
        });
        Ok(json!(delivered))
    }

    fn subscribe(&self, req: &Request, stream: &mut TcpStream) -> Result<(), String> {
        self.authenticate(req)?;
        let prefix = key_text(&req.args, "prefix")?.to_owned();
        let (tx, rx) = mpsc::channel();
        let alive = Arc::new(AtomicBool::new(true));
        let mut state = self
            .state
            .lock()
            .map_err(|_| "internal: state unavailable")?;
        state.subscribers.retain(|s| s.alive.load(Ordering::SeqCst));
        // Adaptive low-descriptor caps must still leave room for ordinary RPCs.
        let subscription_limit = MAX_SUBSCRIBERS.min(self.max_clients / 2);
        if state.subscribers.len() >= subscription_limit {
            return Err("capacity: subscription limit reached".into());
        }
        state.subscribers.push(Subscriber {
            namespace: req.namespace.clone(),
            prefix,
            tx,
            alive: alive.clone(),
            queued: Arc::new(AtomicUsize::new(0)),
        });
        drop(state);
        let result = (|| -> io::Result<()> {
            respond(stream, Ok(json!(true)))?;
            while alive.load(Ordering::SeqCst) {
                match rx.recv_timeout(HEARTBEAT) {
                    Ok(event) => write_event(stream, &event.frame.bytes, &alive)?,
                    Err(mpsc::RecvTimeoutError::Timeout) => {
                        stream.write_all(b"{\"heartbeat\":true}\n")?
                    }
                    Err(mpsc::RecvTimeoutError::Disconnected) => break,
                }
            }
            Ok(())
        })();
        alive.store(false, Ordering::SeqCst);
        result.map_err(|_| "connection: subscriber disconnected".into())
    }
}

/// Bound the whole event write, including a peer that reads only a trickle.
fn write_event(stream: &mut TcpStream, mut bytes: &[u8], alive: &AtomicBool) -> io::Result<()> {
    let deadline = Instant::now() + Duration::from_secs(2);
    while !bytes.is_empty() {
        let remaining = deadline.saturating_duration_since(Instant::now());
        if remaining.is_zero() || !alive.load(Ordering::SeqCst) {
            return Err(io::ErrorKind::TimedOut.into());
        }
        stream.set_write_timeout(Some(remaining))?;
        match stream.write(bytes) {
            Ok(0) => return Err(io::ErrorKind::WriteZero.into()),
            Ok(n) => bytes = &bytes[n..],
            Err(error) if error.kind() == io::ErrorKind::Interrupted => continue,
            Err(error) => return Err(error),
        }
    }
    // Heartbeats use the normal idle-write budget, not a nearly spent deadline.
    stream.set_write_timeout(Some(Duration::from_secs(2)))
}

fn respond(stream: &mut TcpStream, result: Result<Value, String>) -> io::Result<()> {
    let response = match result {
        Ok(value) => json!({"ok": true, "value": value}),
        Err(error) => json!({"ok": false, "error": error}),
    };
    let mut bytes = serde_json::to_vec(&response)?;
    bytes.push(b'\n');
    stream.write_all(&bytes)
}

fn read_frame(
    reader: &mut BufReader<TcpStream>,
    limit: usize,
    deadline: Instant,
) -> io::Result<Vec<u8>> {
    let mut frame = Vec::new();
    loop {
        // A single deadline bounds both authentication and body reads, including
        // peers that send one byte just before each individual read timeout.
        let remaining = deadline.saturating_duration_since(Instant::now());
        if remaining.is_zero() {
            return Err(io::ErrorKind::TimedOut.into());
        }
        reader.get_ref().set_read_timeout(Some(remaining))?;
        let bytes = reader.fill_buf()?;
        if bytes.is_empty() {
            return Err(io::ErrorKind::UnexpectedEof.into());
        }
        let end = bytes.iter().position(|b| *b == b'\n');
        let amount = end.map_or(bytes.len(), |i| i + 1);
        if frame.len() + amount > limit {
            return Err(io::ErrorKind::InvalidData.into());
        }
        frame.extend_from_slice(&bytes[..amount]);
        reader.consume(amount);
        if end.is_some() {
            return Ok(frame);
        }
    }
}

/// Read the declared binary body under one deadline, including trickle senders.
fn read_payload(reader: &mut BufReader<TcpStream>, size: usize) -> io::Result<Arc<Vec<u8>>> {
    let deadline = Instant::now() + Duration::from_secs(5);
    let mut bytes = vec![0; size];
    let mut offset = 0;
    while offset < size {
        let remaining = deadline.saturating_duration_since(Instant::now());
        if remaining.is_zero() {
            return Err(io::ErrorKind::TimedOut.into());
        }
        reader.get_ref().set_read_timeout(Some(remaining))?;
        match reader.read(&mut bytes[offset..])? {
            0 => return Err(io::ErrorKind::UnexpectedEof.into()),
            amount => offset += amount,
        }
    }
    Ok(Arc::new(bytes))
}

fn respond_value(
    stream: &mut TcpStream,
    result: Result<Option<Arc<Vec<u8>>>, String>,
) -> io::Result<()> {
    match result {
        Ok(Some(bytes)) => {
            let mut frame =
                serde_json::to_vec(&json!({"ok": true, "value": {"payload_bytes": bytes.len()}}))?;
            frame.push(b'\n');
            // Copy at most one page to save a second syscall for small replies.
            // Large values retain their shared storage and avoid a full copy.
            if bytes.len() <= 4096 {
                frame.extend_from_slice(&bytes);
                stream.write_all(&frame)
            } else {
                stream.write_all(&frame)?;
                stream.write_all(&bytes)
            }
        }
        Ok(None) => respond(stream, Ok(Value::Null)),
        Err(error) => respond(stream, Err(error)),
    }
}

fn handle(server: &Server, stream: TcpStream) -> io::Result<()> {
    // Accepted sockets can inherit nonblocking mode after listener recovery on
    // some Unix systems; request deadlines require blocking socket operations.
    stream.set_nonblocking(false)?;
    stream.set_write_timeout(Some(Duration::from_secs(2)))?;
    stream.set_nodelay(true)?;
    let mut reader = BufReader::new(stream);
    let mut fresh = true;
    loop {
        let deadline = Instant::now() + Duration::from_secs(if fresh { 5 } else { 30 });
        // Authenticate a small header before allocating or parsing a large body.
        let header = read_frame(&mut reader, MAX_HEADER, deadline)?;
        let mut req: Request = match serde_json::from_slice(&header) {
            Ok(req) => req,
            Err(_) => {
                return respond(
                    reader.get_mut(),
                    Err("invalid: malformed request header".into()),
                )
            }
        };
        if let Err(error) = server.authenticate(&req) {
            return respond(reader.get_mut(), Err(error));
        }
        // A fresh connection waits for authentication before sending its body.
        // Warm connections pipeline their frames and need only one round trip.
        if fresh {
            respond(reader.get_mut(), Ok(json!("ready")))?;
        }
        fresh = false;
        let body = match read_frame(&mut reader, MAX_FRAME, deadline) {
            Ok(body) => body,
            Err(_) => {
                return respond(
                    reader.get_mut(),
                    Err("invalid: incomplete or oversized body".into()),
                )
            }
        };
        req.args = match serde_json::from_slice(&body) {
            Ok(value) => value,
            Err(_) => {
                return respond(
                    reader.get_mut(),
                    Err("invalid: malformed request body".into()),
                )
            }
        };
        req.payload = read_payload(&mut reader, req.payload_bytes)?;
        if req.op == "subscribe" {
            if let Err(error) = server.subscribe(&req, reader.get_mut()) {
                // A streaming failure may leave a partial binary payload. Never
                // append JSON to it; only pre-stream validation gets an error reply.
                if !error.starts_with("connection:") {
                    let _ = respond(reader.get_mut(), Err(error));
                }
            }
            return Ok(());
        } else if req.op == "get" {
            respond_value(reader.get_mut(), server.get_value(&req))?;
        } else {
            respond(reader.get_mut(), server.execute(&req))?;
        }
    }
}

/// Release capacity even when a request handler unwinds unexpectedly.
struct ClientSlot(Arc<Server>);
impl Drop for ClientSlot {
    fn drop(&mut self) {
        self.0.clients.fetch_sub(1, Ordering::SeqCst);
    }
}

/// Reject a new connection before its body, consuming the small header so the
/// close does not reset an unread upload and hide the explicit busy response.
fn reject_busy(stream: TcpStream, reason: &str) {
    let _ = stream.set_nonblocking(false);
    let _ = stream.set_write_timeout(Some(REJECTION_TIMEOUT));
    let mut reader = BufReader::new(stream);
    let _ = read_frame(&mut reader, MAX_HEADER, Instant::now() + REJECTION_TIMEOUT);
    let _ = respond(reader.get_mut(), Err(format!("busy: {reason}")));
}

/// Leave descriptor headroom for stdio, the listener, the reserve and runtime use.
fn connection_limit() -> usize {
    #[cfg(all(
        any(target_os = "macos", target_os = "linux"),
        any(target_arch = "x86_64", target_arch = "aarch64")
    ))]
    {
        #[repr(C)]
        struct Limits {
            current: u64,
            maximum: u64,
        }
        unsafe extern "C" {
            fn getrlimit(resource: std::ffi::c_int, limits: *mut Limits) -> std::ffi::c_int;
        }
        // Darwin sys/resource.h defines NOFILE=8; Linux bits/resource.h uses 7.
        // The gated 64-bit ABIs both use two unsigned 64-bit rlim_t fields.
        let resource = if cfg!(target_os = "macos") { 8 } else { 7 };
        let mut limits = Limits {
            current: 0,
            maximum: 0,
        };
        // SAFETY: the C layout and function ABI are fixed for the gated targets;
        // the aligned output pointer remains valid for the entire synchronous call.
        if unsafe { getrlimit(resource, &mut limits) } == 0 {
            return limits
                .current
                .saturating_sub(16)
                .clamp(1, MAX_CLIENTS as u64) as usize;
        }
    }
    MAX_CLIENTS
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Secrets come from the environment rather than command arguments or logs.
    let token = std::env::var("JESSE_COORDINATION_TOKEN")?;
    if token.len() < 32 {
        return Err("JESSE_COORDINATION_TOKEN must contain at least 32 bytes".into());
    }
    let address: SocketAddr = std::env::var("JESSE_COORDINATION_BIND")
        .unwrap_or_else(|_| "127.0.0.1:6381".into())
        .parse()?;
    if !address.ip().is_loopback() {
        return Err("coordinator must bind to a loopback address".into());
    }
    let max_clients = connection_limit();
    // Two subscriptions and two RPCs are the minimum useful research instance.
    // Refuse smaller limits rather than starting an unusable dashboard backend.
    if max_clients < 4 {
        return Err("OS descriptor limit is too low: coordinator needs at least 4 client slots plus 16 reserved descriptors".into());
    }
    let listener = TcpListener::bind(address)?;
    // Unix descriptor exhaustion must still leave room to accept and reject one
    // pending client explicitly. This reserve belongs only to this process.
    #[cfg(unix)]
    let mut spare_descriptor = Some(std::fs::File::open("/dev/null")?);
    let mut last_error_log: Option<Instant> = None;
    let generation = format!(
        "{}-{}",
        std::process::id(),
        SystemTime::now().duration_since(UNIX_EPOCH)?.as_nanos()
    );
    let server = Arc::new(Server {
        state: Mutex::new(State::default()),
        token,
        generation,
        clients: AtomicUsize::new(0),
        max_clients,
        queued: Arc::new(AtomicUsize::new(0)),
    });
    if server.max_clients < MAX_CLIENTS {
        // A supervisor may close its error-log pipe. Diagnostics must not panic
        // and destroy shared state merely because their destination disappeared.
        let _ = writeln!(
            io::stderr(),
            "Coordinator connection limit reduced to {} by OS descriptor limits",
            server.max_clients
        );
    }
    let cleanup = server.clone();
    thread::spawn(move || loop {
        thread::sleep(Duration::from_secs(1));
        if let Ok(mut state) = cleanup.state.lock() {
            state.purge();
        }
    });
    println!("jesse-coordinator listening on {}", listener.local_addr()?);
    for stream in listener.incoming() {
        let stream = match stream {
            Ok(stream) => stream,
            Err(error) => {
                if last_error_log.is_none_or(|last| last.elapsed() >= ERROR_LOG_INTERVAL) {
                    let _ = writeln!(io::stderr(), "Coordinator accept failed: {error}");
                    last_error_log = Some(Instant::now());
                }
                #[cfg(unix)]
                if matches!(error.raw_os_error(), Some(23) | Some(24)) {
                    // ENFILE/EMFILE on supported Unix targets. A reset from one
                    // queued peer must not reject the next healthy connection.
                    drop(spare_descriptor.take());
                    // Nonblocking accept avoids getting stuck if the queued peer
                    // disconnected while the exhausted accept was being handled.
                    if listener.set_nonblocking(true).is_ok() {
                        if let Ok((pending, _)) = listener.accept() {
                            reject_busy(pending, "operating system connection capacity reached");
                        }
                        // Retain state if mode restoration fails; the existing
                        // backoff still bounds polling of a nonblocking listener.
                        let _ = listener.set_nonblocking(false);
                    }
                    spare_descriptor = std::fs::File::open("/dev/null").ok();
                }
                // Resource exhaustion must not spin or erase in-memory state.
                thread::sleep(Duration::from_millis(100));
                continue;
            }
        };
        #[allow(deprecated, reason = "MSRV 1.82 predates try_update")]
        let admitted = server
            .clients
            .fetch_update(Ordering::SeqCst, Ordering::SeqCst, |n| {
                (n < server.max_clients).then_some(n + 1)
            })
            .is_ok();
        if !admitted {
            // This request was not read or applied. A typed rejection lets the
            // client distinguish overload from an ambiguous failed mutation.
            let reason = if server.max_clients < MAX_CLIENTS {
                "operating system connection capacity reached"
            } else {
                "connection limit reached"
            };
            reject_busy(stream, reason);
            continue;
        }
        let shared = server.clone();
        let slot = ClientSlot(shared.clone());
        if let Err(error) = thread::Builder::new().spawn(move || {
            let _slot = slot;
            let _ = handle(&shared, stream);
        }) {
            // Dropping the failed spawn's closure releases its slot and socket.
            if last_error_log.is_none_or(|last| last.elapsed() >= ERROR_LOG_INTERVAL) {
                let _ = writeln!(io::stderr(), "Coordinator worker creation failed: {error}");
                last_error_log = Some(Instant::now());
            }
            thread::sleep(Duration::from_millis(100));
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn server() -> Server {
        Server {
            state: Mutex::new(State::default()),
            token: "test".into(),
            generation: "test-generation".into(),
            clients: AtomicUsize::new(0),
            max_clients: MAX_CLIENTS,
            queued: Arc::new(AtomicUsize::new(0)),
        }
    }

    fn publication() -> Request {
        Request {
            version: 2,
            token: "test".into(),
            namespace: "test".into(),
            generation: Some("test-generation".into()),
            op: "publish".into(),
            args: json!({"channel": "events:one"}),
            payload_bytes: 1,
            payload: Arc::new(vec![255]),
        }
    }

    fn subscription(server: &Server) -> (mpsc::Receiver<Event>, Arc<AtomicUsize>) {
        let (tx, rx) = mpsc::channel();
        let queued = Arc::new(AtomicUsize::new(0));
        server.state.lock().unwrap().subscribers.push(Subscriber {
            namespace: "test".into(),
            prefix: "events:".into(),
            tx,
            alive: Arc::new(AtomicBool::new(true)),
            queued: queued.clone(),
        });
        (rx, queued)
    }

    #[test]
    fn global_congestion_is_transient_and_unmatched_publish_needs_no_capacity() {
        let server = server();
        // Model a full budget held by unrelated in-flight frames, without
        // allocating 64 MiB merely to exercise error classification.
        server.queued.store(MAX_QUEUED, Ordering::SeqCst);
        assert_eq!(server.publish(&publication()).unwrap(), json!(0));
        let (_receiver, _) = subscription(&server);
        assert!(server
            .publish(&publication())
            .unwrap_err()
            .starts_with("busy:"));
        assert_eq!(server.state.lock().unwrap().subscribers.len(), 1);
    }

    #[test]
    fn fanout_counts_frame_once_and_releases_all_reservations() {
        let server = server();
        let (first, first_bytes) = subscription(&server);
        let (second, second_bytes) = subscription(&server);
        assert_eq!(server.publish(&publication()).unwrap(), json!(2));
        let one = first.try_recv().unwrap();
        let two = second.try_recv().unwrap();
        let size = one.frame.bytes.len();
        assert_eq!(server.queued.load(Ordering::SeqCst), size);
        assert_eq!(first_bytes.load(Ordering::SeqCst), size + EVENT_OVERHEAD);
        drop(one);
        assert_eq!(first_bytes.load(Ordering::SeqCst), 0);
        assert_eq!(server.queued.load(Ordering::SeqCst), size);
        drop(two);
        assert_eq!(second_bytes.load(Ordering::SeqCst), 0);
        assert_eq!(server.queued.load(Ordering::SeqCst), 0);
    }

    #[test]
    fn state_budgets_are_atomic_and_reclaim_after_removal() {
        let mut state = State::default();
        let entry = Entry {
            data: Data::Bytes(Arc::new(vec![0])),
            expires: None,
        };
        for index in 0..MAX_KEYS {
            state
                .insert(("n".into(), index.to_string()), entry.clone())
                .unwrap();
        }
        let size = state.bytes;
        assert!(state
            .insert(("n".into(), "overflow".into()), entry.clone())
            .is_err());
        assert_eq!(state.bytes, size);
        assert_eq!(state.entries.len(), MAX_KEYS);
        state.remove(&("n".into(), "0".into()));
        state
            .insert(("n".into(), "replacement".into()), entry)
            .unwrap();
        // Exercise actual resident byte accounting, including rejected insertion
        // and removal, using a bounded number of large entries.
        let mut state = State::default();
        let large = Entry {
            data: Data::Bytes(Arc::new(vec![0; 8 * 1024 * 1024])),
            expires: None,
        };
        for index in 0..15 {
            state
                .insert(("n".into(), index.to_string()), large.clone())
                .unwrap();
        }
        let size = state.bytes;
        assert!(state
            .insert(("n".into(), "overflow".into()), large.clone())
            .is_err());
        assert_eq!(state.bytes, size);
        state.remove(&("n".into(), "0".into()));
        state
            .insert(("n".into(), "replacement".into()), large)
            .unwrap();
        for entry in state.entries.values_mut() {
            entry.expires = Some(Instant::now());
        }
        state.purge();
        assert_eq!(state.bytes, 0);
        assert!(state.entries.is_empty());
    }
}
