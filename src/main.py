import hashlib
import hmac
import os
import time
import threading
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
import grpc
import requests

# These modules are generated via grpcio-tools from protos/event_stream.proto
try:
    import event_stream_pb2
    import event_stream_pb2_grpc
except ImportError:
    print("Warning: event_stream_pb2 modules not found. Make sure to generate them from proto files.")
    print("Run: python -m grpc_tools.protoc --proto_path=./protos --python_out=./src --grpc_python_out=./src ./protos/event_stream.proto")
    event_stream_pb2 = None
    event_stream_pb2_grpc = None

# Dynata authentication constants
DYNATA_AUTH = os.environ.get('DYNATA_AUTH', 'E2ABCF45339FB9E093384A78E01A899F95BA3F22')
DYNATA_SECRET = os.environ.get('DYNATA_SECRET', 'r54zNnhXqMtb6RkxWPX17R5ypp0HlDPL')
DYNATA_ACCESS_KEY = os.environ.get('DYNATA_ACCESS_KEY', 'E2ABCF45339FB9E093384A78E01A899F95BA3F22')

# Cloud Function endpoint
CLOUD_FUNCTION_URL = os.environ.get('CLOUD_FUNCTION_URL', 'https://us-central1-lancelot-fa22c.cloudfunctions.net/dynataEvent')

# Cloud Run port
PORT = int(os.environ.get('PORT', '8080'))


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


def protobuf_to_dict(message):
    """
    Convert a protobuf message to a dictionary.
    
    Args:
        message: Protobuf message object
        
    Returns:
        Dictionary representation of the message
    """
    try:
        # Try using MessageToDict if available (from google.protobuf.json_format)
        from google.protobuf.json_format import MessageToDict
        return MessageToDict(message, preserving_proto_field_name=True)
    except ImportError:
        pass
    
    # Fallback: manual conversion
    result = {}
    if hasattr(message, 'DESCRIPTOR'):
        for field in message.DESCRIPTOR.fields:
            field_name = field.name
            value = getattr(message, field_name, None)
            if value is not None:
                # Handle nested messages
                if hasattr(value, 'DESCRIPTOR'):
                    result[field_name] = protobuf_to_dict(value)
                # Handle repeated fields
                elif isinstance(value, (list, tuple)):
                    result[field_name] = [
                        protobuf_to_dict(item) if hasattr(item, 'DESCRIPTOR') else item
                        for item in value
                    ]
                else:
                    result[field_name] = value
    return result


def send_event_to_cloud_function(event):
    """
    Send event to Cloud Function via POST request.
    
    Args:
        event: The event protobuf message (Event type)
    """
    try:
        # Convert event to dictionary
        event_dict = protobuf_to_dict(event)
        
        # Determine event subtype from oneof data field
        event_subtype = None
        if hasattr(event, 'start') and event.HasField('start'):
            event_subtype = 'Start'
            event_dict['data_type'] = 'start'
        elif hasattr(event, 'end') and event.HasField('end'):
            event_subtype = 'End'
            event_dict['data_type'] = 'end'
        
        # Add metadata
        event_dict['event_type'] = 'Event'
        event_dict['event_subtype'] = event_subtype
        event_dict['session'] = event.session if hasattr(event, 'session') else None
        event_dict['event_timestamp'] = event.timestamp if hasattr(event, 'timestamp') else None
        event_dict['received_at'] = datetime.utcnow().isoformat()
        
        # Send POST request to Cloud Function
        response = requests.post(
            CLOUD_FUNCTION_URL,
            json=event_dict,
            headers={'Content-Type': 'application/json'},
            timeout=10
        )
        
        response.raise_for_status()
        
        print(f"Sent {event_subtype or 'Event'} event to Cloud Function (session: {event.session}, status: {response.status_code})")
        return response
        
    except requests.exceptions.RequestException as e:
        print(f"Error sending event to Cloud Function: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response status: {e.response.status_code}")
            print(f"Response body: {e.response.text}")
        import traceback
        traceback.print_exc()
        raise
    except Exception as e:
        print(f"Unexpected error sending event: {e}")
        import traceback
        traceback.print_exc()
        raise


class HealthCheckHandler(BaseHTTPRequestHandler):
    """Simple HTTP handler for Cloud Run health checks"""
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'OK')
    
    def log_message(self, format, *args):
        # Suppress default logging
        pass


def start_health_server():
    """Start HTTP server for Cloud Run health checks"""
    server = HTTPServer(('', PORT), HealthCheckHandler)
    print(f"Health check server listening on port {PORT}")
    server.serve_forever()


def run():
    """
    Main function to connect to Dynata event stream and process events.
    """
    if event_stream_pb2 is None or event_stream_pb2_grpc is None:
        raise ImportError("event_stream_pb2 modules are required. Generate them from proto files first.")
    
    print(f"Cloud Function endpoint: {CLOUD_FUNCTION_URL}")
    
    # Generate authentication
    # Match the Node.js implementation: expiration is ISO string (RFC 3339)
    # expiration = new Date((Timestamp.now().seconds + 1000) * 1000).toISOString()
    expiration_time = time.time() + 1000  # 1000 seconds from now (matching Node.js)
    expiration = datetime.fromtimestamp(expiration_time, tz=timezone.utc).isoformat()
    
    # According to broadcaster documentation: Use "respondent.events" as the signing string
    # Per security docs: For API requests, signing_string is SHA256 hash of the request body
    # For the event stream, we use "respondent.events" as the literal string
    signing_string = "respondent.events"
    
    # Per security documentation: sign(signing_string, access_key, secret_key, expiration)
    signature = get_dynata_signature(signing_string, DYNATA_AUTH, DYNATA_SECRET, expiration)
    
    # In Node.js, dynata-access-key uses DYNATA_AUTH
    # The access_key field should match what was used for signature creation
    access_key = DYNATA_AUTH
    
    if not access_key:
        raise ValueError("DYNATA_AUTH environment variable must be set")
    
    # Debug logging
    print(f"Generated signature for expiration: {expiration}")
    print(f"Using access_key: {access_key[:10]}...")
    print(f"Signature: {signature[:20]}...")
    print(f"Signing string: {signing_string}")
    
    # The service uses TLS, but does not require client-side certificate configuration
    credentials = grpc.ssl_channel_credentials(
        root_certificates=None,
        private_key=None,
        certificate_chain=None
    )
    
    # Connect to Dynata event stream
    with grpc.secure_channel(
        'events.rex.dynata.com',
        credentials,
        # Ensure that the channel uses client-side keepalives
        options=(('grpc.keepalive_time_ms', 1000),)
    ) as channel:
        client = event_stream_pb2_grpc.EventStreamStub(channel)
        
        # Create auth message
        auth = event_stream_pb2.Auth(
            expiration=expiration,
            access_key=access_key,
            signature=signature
        )
        
        print("Connecting to Dynata event stream...")
        
        try:
            # Listen to events
            events = client.Listen(auth)
            
            for event in events:
                # Process and send each event
                event_type = 'Start' if event.HasField('start') else ('End' if event.HasField('end') else 'Unknown')
                print(f"Received {event_type} event - Session: {event.session}, Timestamp: {event.timestamp}")
                send_event_to_cloud_function(event)
                
        except grpc.RpcError as e:
            print(f"gRPC error: {e.code()} - {e.details()}")
            raise
        except KeyboardInterrupt:
            print("Interrupted by user")
        except Exception as e:
            print(f"Unexpected error: {e}")
            raise


if __name__ == '__main__':
    # Start health check server in a separate thread
    health_thread = threading.Thread(target=start_health_server, daemon=True)
    health_thread.start()
    
    # Run the main event stream handler
    run()

