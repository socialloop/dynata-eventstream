#!/bin/bash

# Deploy Dynata Event Stream service to Cloud Run
#
# Credentials come from Secret Manager (secrets: dynata-auth, dynata-secret).
# To rotate: gcloud secrets versions add dynata-auth --data-file=- <<< "NEW_VALUE"
# then redeploy (or restart the service).

set -e

PROJECT_ID=${1:-${GOOGLE_CLOUD_PROJECT:-lancelot-fa22c}}
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
    --no-allow-unauthenticated \
    --set-secrets "DYNATA_AUTH=dynata-auth:latest,DYNATA_SECRET=dynata-secret:latest" \
    --set-env-vars "CLOUD_FUNCTION_URL=${CLOUD_FUNCTION_URL:-https://api.eurekasurveys.com/dynataEvent}" \
    --memory 512Mi \
    --cpu 1 \
    --timeout 3600 \
    --max-instances 1 \
    --min-instances 1 \
    --no-cpu-throttling

echo "Deployment complete!"
