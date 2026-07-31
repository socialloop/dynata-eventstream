FROM python:3.11-slim

WORKDIR /app

# Log immediately instead of buffering (Cloud Run reads stdout/stderr)
ENV PYTHONUNBUFFERED=1

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ ./src/
COPY protos/ ./protos/

# Generate protobuf files
RUN python3 -m grpc_tools.protoc \
        --proto_path=./protos \
        --python_out=./src \
        --grpc_python_out=./src \
        ./protos/*.proto

# Set Python path
ENV PYTHONPATH=/app/src:${PYTHONPATH}

# Run as non-root
RUN useradd --create-home appuser
USER appuser

# Run the service
CMD ["python3", "src/main.py"]
