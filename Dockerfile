FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ ./src/
COPY protos/ ./protos/

# Generate protobuf files if proto files exist
RUN if [ -n "$(ls -A protos/*.proto 2>/dev/null)" ]; then \
        python3 -m grpc_tools.protoc \
            --proto_path=./protos \
            --python_out=./src \
            --grpc_python_out=./src \
            ./protos/*.proto; \
    fi

# Set Python path
ENV PYTHONPATH=/app/src:${PYTHONPATH}

# Run the service
CMD ["python", "src/main.py"]

