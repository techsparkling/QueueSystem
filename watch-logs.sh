#!/bin/bash

# Watch CallQueueSystem Logs
# Usage: ./watch-logs.sh [--follow] [--limit=N]

source deploy.config

FOLLOW=false
LIMIT=50

# Parse arguments
for arg in "$@"; do
    case $arg in
        --follow)
            FOLLOW=true
            shift
            ;;
        --limit=*)
            LIMIT="${arg#*=}"
            shift
            ;;
    esac
done

echo "📋 CallQueueSystem Logs"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Service: ${SERVICE_NAME}"
echo "Project: ${PROJECT_ID}"
echo "Region: ${REGION}"
echo ""

if [ "$FOLLOW" = true ]; then
    echo "📡 Following logs (Ctrl+C to stop)..."
    gcloud run services logs tail ${SERVICE_NAME} --region=${REGION}
else
    echo "📄 Recent ${LIMIT} log entries:"
    echo ""
    gcloud run services logs read ${SERVICE_NAME} --region=${REGION} --limit=${LIMIT}
fi 