# Dynata Event Stream to Firestore

This service connects to the Dynata event stream via gRPC and writes events to Firestore.

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Set up environment variables (defaults are set but can be overridden):
   - `DYNATA_AUTH`: Dynata authentication key (default: `E2ABCF45339FB9E093384A78E01A899F95BA3F22`)
   - `DYNATA_SECRET`: Dynata secret key (default: `r54zNnhXqMtb6RkxWPX17R5ypp0HlDPL`)
   - `DYNATA_ACCESS_KEY`: Your Dynata access key (default: `E2ABCF45339FB9E093384A78E01A899F95BA3F22`)
   - `GOOGLE_CLOUD_PROJECT`: Your GCP project ID (default: `lancelot-fa22c`)
   - `FIRESTORE_COLLECTION`: Firestore collection name (default: `dynata_events`)

3. Generate protobuf files (the proto file is already in `protos/event_stream.proto`):
```bash
./generate_protos.sh
```

Or manually:
```bash
python3 -m grpc_tools.protoc \
    --proto_path=./protos \
    --python_out=./src \
    --grpc_python_out=./src \
    ./protos/event_stream.proto
```

Note: The Dockerfile will automatically generate these during the build process.

## Local Development

Run the service locally:
```bash
python src/main.py
```

## Deployment to Cloud Run

1. Build and push the Docker image:
```bash
gcloud builds submit --tag gcr.io/[PROJECT-ID]/dynata-eventstream
```

2. Deploy to Cloud Run:
```bash
gcloud run deploy dynata-eventstream \
    --image gcr.io/[PROJECT-ID]/dynata-eventstream \
    --platform managed \
    --region us-central1 \
    --set-env-vars DYNATA_AUTH=[value],DYNATA_SECRET=[value],DYNATA_ACCESS_KEY=[value],GOOGLE_CLOUD_PROJECT=[value] \
    --allow-unauthenticated
```

Or use the Cloud Run service account with Firestore permissions:
```bash
gcloud run deploy dynata-eventstream \
    --image gcr.io/[PROJECT-ID]/dynata-eventstream \
    --platform managed \
    --region us-central1 \
    --set-env-vars DYNATA_AUTH=[value],DYNATA_SECRET=[value],DYNATA_ACCESS_KEY=[value] \
    --service-account [SERVICE-ACCOUNT-EMAIL]
```
