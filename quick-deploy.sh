#!/bin/bash

# Quick Deploy Script for CallQueueSystem
# Usage: ./quick-deploy.sh

set -e

# Source configuration
source deploy.config

echo "🚀 Quick Deploy: ${SERVICE_NAME} to ${PROJECT_ID}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Set project
gcloud config set project ${PROJECT_ID}

# Build and push
echo "📦 Building and pushing Docker image..."
docker build -f Dockerfile.cloudrun -t gcr.io/${PROJECT_ID}/${SERVICE_NAME}:latest .
docker push gcr.io/${PROJECT_ID}/${SERVICE_NAME}:latest

# Deploy
echo "🚀 Deploying to Cloud Run..."
ENV_VARS="REDIS_URL=redis://${REDIS_HOST}:${REDIS_PORT},QUEUE_WORKERS=${QUEUE_WORKERS},MAX_CONCURRENT_CALLS=${MAX_CONCURRENT_CALLS},RATE_LIMIT_PER_SECOND=${RATE_LIMIT_PER_SECOND},PLIVO_AUTH_ID=${PLIVO_AUTH_ID},PLIVO_AUTH_TOKEN=${PLIVO_AUTH_TOKEN},PLIVO_PHONE_NUMBER=${PLIVO_PHONE_NUMBER},AGENT_SERVER_URL=${AGENT_SERVER_URL},SERVER_URL=${SERVER_URL},BACKEND_URL=${BACKEND_URL},BACKEND_API_URL=${BACKEND_API_URL},BACKEND_API_KEY=${BACKEND_API_KEY},ENVIRONMENT=${ENVIRONMENT},LOG_LEVEL=${LOG_LEVEL}"

gcloud run deploy ${SERVICE_NAME} \
    --image gcr.io/${PROJECT_ID}/${SERVICE_NAME}:latest \
    --region ${REGION} \
    --allow-unauthenticated \
    --port 8000 \
    --memory ${MEMORY} \
    --cpu ${CPU} \
    --min-instances ${MIN_INSTANCES} \
    --max-instances ${MAX_INSTANCES} \
    --vpc-connector=${VPC_CONNECTOR} \
    --vpc-egress=private-ranges-only \
    --set-env-vars "${ENV_VARS}" \
    --quiet

# Get URL and test
SERVICE_URL=$(gcloud run services describe ${SERVICE_NAME} --region=${REGION} --format="value(status.url)")
echo "✅ Deployed! URL: ${SERVICE_URL}"

# Quick health test
sleep 3
if curl -s "${SERVICE_URL}/api/health" | grep -q "healthy"; then
    echo "✅ Health check passed!"
else
    echo "⚠️  Health check failed - check logs"
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" 