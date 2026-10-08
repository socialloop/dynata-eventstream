import hashlib
import hmac
import json
import logging
import os
import queue
import signal
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler

import grpc
import requests
from google.protobuf.json_format import MessageToDict
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# These modules are generated via grpcio-tools from protos/event_stream.proto
try:
    import event_stream_pb2
    import event_stream_pb2_grpc
except ImportError:
    print("Warning: event_stream_pb2 modules not found. Make sure to generate them from proto files.")
    print("Run: python -m grpc_tools.protoc --proto_path=./protos --python_out=./src --grpc_python_out=./src ./protos/event_stream.proto")
    event_stream_pb2 = None
    event_stream_pb2_grpc = None

class _CloudRunFormatter(logging.Formatter):
    """Structured JSON logs on stdout so Cloud Logging parses severity.

    Plain text on stderr is ingested as ERROR by Cloud Run, which made every
    routine log line show up (and get billed) as an error.
    """

    def format(self, record):
        message = record.getMessage()
        if record.exc_info:
            message += "\n" + self.formatException(record.exc_info)
        return json.dumps({"severity": record.levelname, "message": message})


_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(_CloudRunFormatter())
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    handlers=[_handler],
)
logger = logging.getLogger("dynata-eventstream")


def _require_env(name: str) -> str:
    """Read a required environment variable, failing fast if missing/empty."""
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Required environment variable {name} is not set")
    return value


# Dynata authentication credentials (no defaults — fail fast if unset)
DYNATA_AUTH = _require_env('DYNATA_AUTH')
DYNATA_SECRET = _require_env('DYNATA_SECRET')

# Cloud Function endpoint (required — no production default so local runs
# can't silently forward to prod)
CLOUD_FUNCTION_URL = _require_env('CLOUD_FUNCTION_URL')

# Cloud Run port
PORT = int(os.environ.get('PORT', '8080'))

# Consider the service unhealthy if the stream has been down this long
UNHEALTHY_AFTER_SECONDS = int(os.environ.get('UNHEALTHY_AFTER_SECONDS', '300'))

# Forwarding workers. Each worker owns a queue and an HTTP session and posts
# sequentially; events are sharded by session so a session's end is always
# posted after its start (the backend drops an end whose start it never saw).
# A single sequential poster (~130ms/post) fell to half the daytime arrival
# rate, built 60+ minutes of lag, and lost the whole backlog on every stream
# reconnect.
WORKER_COUNT = int(os.environ.get('WORKER_COUNT', '16'))
QUEUE_MAXSIZE = int(os.environ.get('QUEUE_MAXSIZE', '1000'))
QUEUE_DEPTH_LOG_SECONDS = 60
# Cloud Run allows 10s after SIGTERM; spend most of it posting queued events
SHUTDOWN_DRAIN_SECONDS = 8

# Stream health state, shared with the health check server.
# Simple attribute assignments are atomic under the GIL.
class _StreamState:
    connected = False
    disconnected_since = time.monotonic()


_stream_state = _StreamState()


def get_dynata_signature(signing_string: str, access_key: str, secret_key: str, expiration: str) -> str:
    """
    Generate Dynata signature for authentication.

    Per documentation: https://docs.rex.dynata.com/rex/security/
    Steps:
    1. HMAC-SHA256(expiration, signing_string)
    2. HMAC-SHA256(access_key, first)
    3. HMAC-SHA256(secret_key, second)

    Args:
        signing_string: The signing string (SHA256 hash of params for API requests)
        access_key: The access key
        secret_key: The secret key
        expiration: Expiration timestamp as string (RFC 3339)

    Returns:
        Hexadecimal signature string
    """
    # Step 1: HMAC-SHA256 with expiration as key and signing_string as message
    first = hmac.new(
        expiration.encode('utf-8'),
        signing_string.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

    # Step 2: HMAC-SHA256 with access_key as key and first as message
    second = hmac.new(
        access_key.encode('utf-8'),
        first.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

    # Step 3: HMAC-SHA256 with secret_key as key and second as message
    final = hmac.new(
        secret_key.encode('utf-8'),
        second.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

    return final


def _create_http_session():
    """Create a requests session with retry logic for transient errors."""
    session = requests.Session()
    retry_strategy = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        # Default allowed_methods excludes POST — include it explicitly so the
        # status_forcelist retries actually apply to our event forwarding.
        allowed_methods=frozenset({"POST"}),
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def send_event_to_cloud_function(session, event):
    """
    Send event to Cloud Function via POST request.
    Does NOT raise — failures are logged and skipped so the stream stays alive.

    Args:
        session: requests.Session owned by the calling worker
        event: The event protobuf message (Event type)
    """
    event_dict = MessageToDict(event, preserving_proto_field_name=True)
    try:
        # Send POST request to Cloud Function (session retries 429/5xx)
        response = session.post(
            CLOUD_FUNCTION_URL,
            json=event_dict,
            headers={'Content-Type': 'application/json'},
            timeout=10
        )
        response.raise_for_status()
        logger.debug("Forwarded event (session=%s, status=%s)", event.session, response.status_code)

    except requests.exceptions.RequestException as e:
        logger.error("Failed to forward event (session=%s): %s", event.session, e)
        if getattr(e, 'response', None) is not None:
            logger.error("Response status: %s, body: %.500s", e.response.status_code, e.response.text)
    except Exception:
        logger.exception("Unexpected error forwarding event (session=%s)", event.session)


# One bounded queue per worker; the listener blocks when a shard is full
_queues = [queue.Queue(maxsize=QUEUE_MAXSIZE) for _ in range(WORKER_COUNT)]


def _worker(q):
    """Drain one shard's queue forever, posting events in order."""
    session = _create_http_session()
    while True:
        event = q.get()
        send_event_to_cloud_function(session, event)
        q.task_done()


def _shard_for(session_id: str) -> int:
    """Map a Dynata session id to a worker so all its events post in order."""
    return hash(session_id) % WORKER_COUNT


def enqueue_event(event):
    """Hand an event to its shard's worker, blocking if that shard is full."""
    _queues[_shard_for(event.session)].put(event)


def _log_queue_depth():
    """Periodic queue-depth log so forwarding lag is visible in Cloud Logging."""
    while True:
        time.sleep(QUEUE_DEPTH_LOG_SECONDS)
        depths = [q.qsize() for q in _queues]
        logger.info("Forwarding queue depth: total=%s max_shard=%s", sum(depths), max(depths))


def drain_queues(timeout: float):
    """Wait up to `timeout` seconds for the workers to post what is queued."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        pending = sum(q.unfinished_tasks for q in _queues)
        if pending == 0:
            logger.info("Forwarding queues drained")
            return
        time.sleep(0.1)
    logger.warning("Shutdown with %s events still queued", sum(q.unfinished_tasks for q in _queues))


def start_workers():
    """Start the forwarding workers and the queue-depth logger."""
    for q in _queues:
        threading.Thread(target=_worker, args=(q,), daemon=True).start()
    threading.Thread(target=_log_queue_depth, daemon=True).start()
    logger.info("Started %s forwarding workers (queue maxsize %s)", WORKER_COUNT, QUEUE_MAXSIZE)


class HealthCheckHandler(BaseHTTPRequestHandler):
    """HTTP handler for Cloud Run health checks."""

    def do_GET(self):
        if self.path == '/healthz':
            # Liveness: unhealthy if the stream has been down too long
            down_for = 0 if _stream_state.connected else time.monotonic() - _stream_state.disconnected_since
            if down_for > UNHEALTHY_AFTER_SECONDS:
                self.send_response(503)
                body = f'stream down for {int(down_for)}s'.encode()
            else:
                self.send_response(200)
                body = b'OK'
        else:
            # Startup/readiness: process is up
            self.send_response(200)
            body = b'OK'
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        # Suppress default logging
        pass


def start_health_server():
    """Start HTTP server for Cloud Run health checks"""
    server = HTTPServer(('', PORT), HealthCheckHandler)
    logger.info("Health check server listening on port %s", PORT)
    server.serve_forever()


def generate_auth():
    """
    Generate authentication credentials for Dynata event stream.

    Returns:
        tuple: (expiration, access_key, signature)
    """
    # Expiration is an ISO string (RFC 3339), 1000 seconds from now
    expiration_time = time.time() + 1000
    expiration = datetime.fromtimestamp(expiration_time, tz=timezone.utc).isoformat()

    # Per broadcaster documentation: "respondent.events" is the signing string
    signing_string = "respondent.events"

    # Per security documentation: sign(signing_string, access_key, secret_key, expiration)
    signature = get_dynata_signature(signing_string, DYNATA_AUTH, DYNATA_SECRET, expiration)

    return expiration, DYNATA_AUTH, signature


def connect_and_listen():
    """
    Connect to Dynata event stream and listen for events.
    This function will run until the stream disconnects or an error occurs.
    """
    # Generate fresh authentication for each connection attempt
    expiration, access_key, signature = generate_auth()
    logger.info("Connecting to Dynata event stream (auth expiration: %s)", expiration)

    # The service uses TLS, but does not require client-side certificate configuration
    credentials = grpc.ssl_channel_credentials()

    # Connect to Dynata event stream
    with grpc.secure_channel(
        'events.rex.dynata.com',
        credentials,
        # Ensure that the channel uses client-side keepalives
        options=(('grpc.keepalive_time_ms', 30000),)
    ) as channel:
        client = event_stream_pb2_grpc.EventStreamStub(channel)

        auth = event_stream_pb2.Auth(
            expiration=expiration,
            access_key=access_key,
            signature=signature
        )

        # Wait for the channel to be ready so health state reflects actual
        # connectivity (a quiet stream is still a healthy stream)
        grpc.channel_ready_future(channel).result(timeout=30)
        _stream_state.connected = True
        logger.info("Channel ready, listening for events")

        events = client.Listen(auth)
        try:
            for event in events:
                event_type = "Start" if event.HasField("start") else "End" if event.HasField("end") else "Unknown"
                logger.debug("Received %s event (session=%s, timestamp=%s)", event_type, event.session, event.timestamp)
                enqueue_event(event)
        finally:
            _stream_state.connected = False
            _stream_state.disconnected_since = time.monotonic()


def run():
    """
    Main function to connect to Dynata event stream and process events.
    Includes retry logic with exponential backoff.
    """
    if event_stream_pb2 is None or event_stream_pb2_grpc is None:
        raise ImportError("event_stream_pb2 modules are required. Generate them from proto files first.")

    logger.info("Cloud Function endpoint: %s", CLOUD_FUNCTION_URL)

    # Retry configuration — the stream is not durable (events during
    # disconnection are lost forever), so reconnect as fast as possible.
    # Backoff only guards against tight failure loops (e.g. bad credentials).
    max_retry_delay = 30
    retry_count = 0
    # A connection that survived this long counts as healthy: reset backoff
    healthy_connection_seconds = 60

    while True:
        connected_at = time.monotonic()
        try:
            connect_and_listen()
            # Stream ended normally (server closed) — reconnect immediately
            logger.info("Stream ended normally, reconnecting...")
            retry_count = 0
            continue

        except (KeyboardInterrupt, SystemExit):
            logger.info("Shutting down")
            break

        except grpc.RpcError as e:
            logger.error("gRPC error: %s - %s", e.code(), e.details())
            if e.code() in (grpc.StatusCode.UNAUTHENTICATED, grpc.StatusCode.PERMISSION_DENIED):
                logger.error("Authentication/permission error - check credentials")

        except Exception:
            logger.exception("Unexpected error in stream loop")

        # A long-lived connection that later failed is not a retry storm —
        # reset the counter so transient blips reconnect quickly.
        if time.monotonic() - connected_at > healthy_connection_seconds:
            retry_count = 0

        # Every second disconnected loses events, so the first retry is immediate
        retry_count += 1
        delay = 0 if retry_count == 1 else min(2 ** (retry_count - 2), max_retry_delay)
        logger.info("Reconnecting in %ss (attempt %s)...", delay, retry_count)
        time.sleep(delay)


def _handle_sigterm(signum, frame):
    """Cloud Run sends SIGTERM before shutdown — exit cleanly."""
    logger.info("Received SIGTERM")
    raise SystemExit(0)


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, _handle_sigterm)

    # Start health check server in a separate thread
    health_thread = threading.Thread(target=start_health_server, daemon=True)
    health_thread.start()

    # Start the forwarding workers before any event can arrive
    start_workers()

    # Run the main event stream handler until SIGTERM
    try:
        run()
    finally:
        # The stream is closed, so nothing new arrives: post what is still queued
        drain_queues(SHUTDOWN_DRAIN_SECONDS)
