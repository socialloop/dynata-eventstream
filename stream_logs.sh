#!/bin/bash

# Stream Cloud Run logs by polling
SERVICE_NAME="dynata-eventstream"
REGION="us-central1"
PROJECT="lancelot-fa22c"
LAST_TIMESTAMP=""

while true; do
    # Get recent logs
    LOGS=$(gcloud run services logs read "$SERVICE_NAME" \
        --region "$REGION" \
        --project "$PROJECT" \
        --limit 50 \
        --format="table(timestamp,severity,textPayload)" 2>/dev/null)
    
    if [ -n "$LOGS" ]; then
        # Only show new logs (simple approach - just show all recent logs)
        echo "$LOGS"
    fi
    
    sleep 2
done

