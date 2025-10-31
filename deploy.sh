#!/bin/bash

# Deploy Dynata Event Stream service to Cloud Run

set -e

PROJECT_ID=${1:-$GOOGLE_CLOUD_PROJECT}
REGION=${2:-us-central1}
SERVICE_NAME="dynata-eventstream"

if [ -z "$PROJECT_ID" ]; then
    echo "Error: PROJECT_ID is required. Set GOOGLE_CLOUD_PROJECT or pass as first argument."
    exit 1
fi

echo "Deploying to Cloud Run..."
echo "Project: $PROJECT_ID"
echo "Region: $REGION"
echo "Service: $SERVICE_NAME"

# Build and deploy
gcloud run deploy $SERVICE_NAME \
    --source . \
    --platform managed \
    --region $REGION \
    --project $PROJECT_ID \
    --allow-unauthenticated \
    --set-env-vars "DYNATA_AUTH=${DYNATA_AUTH},DYNATA_SECRET=${DYNATA_SECRET},DYNATA_ACCESS_KEY=${DYNATA_ACCESS_KEY},CLOUD_FUNCTION_URL=${CLOUD_FUNCTION_URL:-https://us-central1-lancelot-fa22c.cloudfunctions.net/dynataEvent}" \
    --memory 512Mi \
    --cpu 1 \
    --timeout 3600 \
    --max-instances 1 \
    --no-cpu-throttling

echo "Deployment complete!"

