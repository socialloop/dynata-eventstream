#!/bin/bash

# Generate Python gRPC code from proto files

if [ ! -d "protos" ]; then
    echo "Error: protos directory not found"
    exit 1
fi

if [ -z "$(ls -A protos/*.proto 2>/dev/null)" ]; then
    echo "Warning: No .proto files found in protos directory"
    exit 0
fi

echo "Generating Python code from proto files..."
python3 -m grpc_tools.protoc \
    --proto_path=./protos \
    --python_out=./src \
    --grpc_python_out=./src \
    ./protos/*.proto

echo "Proto generation complete!"

