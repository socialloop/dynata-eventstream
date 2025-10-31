# Deployment Guide

This guide covers how to deploy the Dynata Event Stream service to Google Cloud Run.

## Prerequisites

1. **Google Cloud SDK** installed and authenticated:
   ```bash
   gcloud auth login
   gcloud config set project lancelot-fa22c
   ```

2. **Enable required APIs**:
   ```bash
   gcloud services enable run.googleapis.com
   gcloud services enable cloudbuild.googleapis.com
   ```

## Deployment Methods

### Method 1: Using the Deploy Script (Recommended)

The easiest way to deploy is using the provided `deploy.sh` script:

```bash
./deploy.sh lancelot-fa22c
```

Or with a custom region:
```bash
./deploy.sh lancelot-fa22c us-west1
```

The script will:
- Build the Docker image from source
- Deploy to Cloud Run
- Set environment variables automatically

**Required Environment Variables** (set before running):
```bash
export DYNATA_AUTH="E2ABCF45339FB9E093384A78E01A899F95BA3F22"
export DYNATA_SECRET="r54zNnhXqMtb6RkxWPX17R5ypp0HlDPL"
export DYNATA_ACCESS_KEY="E2ABCF45339FB9E093384A78E01A899F95BA3F22"
```

### Method 2: Direct gcloud Command

Deploy directly using gcloud:

```bash
gcloud run deploy dynata-eventstream \
    --source . \
    --platform managed \
    --region us-central1 \
    --project lancelot-fa22c \
    --allow-unauthenticated \
    --set-env-vars "DYNATA_AUTH=E2ABCF45339FB9E093384A78E01A899F95BA3F22,DYNATA_SECRET=r54zNnhXqMtb6RkxWPX17R5ypp0HlDPL,DYNATA_ACCESS_KEY=E2ABCF45339FB9E093384A78E01A899F95BA3F22,CLOUD_FUNCTION_URL=https://us-central1-lancelot-fa22c.cloudfunctions.net/dynataEvent" \
    --memory 512Mi \
    --cpu 1 \
    --timeout 3600 \
    --max-instances 1 \
    --no-cpu-throttling
```

**Note:** `--no-cpu-throttling` ensures the service stays running continuously (important for streaming).

### Method 3: Using Cloud Build

Deploy using Cloud Build with the `cloudbuild.yaml`:

```bash
gcloud builds submit --config cloudbuild.yaml
```

Then manually deploy the image:
```bash
gcloud run deploy dynata-eventstream \
    --image gcr.io/lancelot-fa22c/dynata-eventstream \
    --platform managed \
    --region us-central1 \
    --project lancelot-fa22c \
    --allow-unauthenticated \
    --set-env-vars "DYNATA_AUTH=...,DYNATA_SECRET=...,DYNATA_ACCESS_KEY=...,CLOUD_FUNCTION_URL=..." \
    --memory 512Mi \
    --cpu 1 \
    --timeout 3600 \
    --max-instances 1 \
    --no-cpu-throttling
```

## Important Configuration

### CPU Throttling

For streaming services that need to run continuously, disable CPU throttling:
```bash
--no-cpu-throttling
```

This ensures the service doesn't scale to zero and maintains the gRPC connection.

### Resource Limits

- **Memory**: 512Mi (can be adjusted based on event volume)
- **CPU**: 1 (can be increased if needed)
- **Timeout**: 3600 seconds (1 hour) - Cloud Run max is 3600s
- **Max Instances**: 1 (to avoid duplicate event processing)

### Environment Variables

- `DYNATA_AUTH`: Dynata authentication key
- `DYNATA_SECRET`: Dynata secret key
- `DYNATA_ACCESS_KEY`: Dynata access key
- `CLOUD_FUNCTION_URL`: Cloud Function endpoint (default: `https://us-central1-lancelot-fa22c.cloudfunctions.net/dynataEvent`)

## Verification

After deployment, check the logs:

```bash
gcloud run services logs read dynata-eventstream \
    --region us-central1 \
    --project lancelot-fa22c \
    --limit 50
```

Or view in the Cloud Console:
https://console.cloud.google.com/run/detail/us-central1/dynata-eventstream/logs

## Updating the Service

To update the service after making code changes:

```bash
./deploy.sh lancelot-fa22c
```

Or manually:
```bash
gcloud run deploy dynata-eventstream \
    --source . \
    --platform managed \
    --region us-central1 \
    --project lancelot-fa22c
```

## Troubleshooting

### Service keeps restarting

- Check logs for errors
- Ensure `--no-cpu-throttling` is set
- Verify environment variables are correct

### Events not being received

- Check gRPC connection in logs
- Verify Dynata credentials are correct
- Check Cloud Function endpoint is accessible

### High memory usage

- Increase memory allocation: `--memory 1Gi`
- Check for memory leaks in event processing

