#!/bin/bash

# Development Deploy Script for CallQueueSystem
# Usage: ./dev-deploy.sh [--skip-build] [--logs]

set -e

# Source configuration
source deploy.config

# Parse arguments
SKIP_BUILD=false
SHOW_LOGS=false

for arg in "$@"; do
    case $arg in
        --skip-build)
            SKIP_BUILD=true
            shift
            ;;
        --logs)
            SHOW_LOGS=true
            shift
            ;;
    esac
done

echo "🛠️  Dev Deploy: ${SERVICE_NAME}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Set project
gcloud config set project ${PROJECT_ID} > /dev/null

# Build and push (unless skipped)
if [ "$SKIP_BUILD" = false ]; then
    echo "📦 Building Docker image..."
    docker build -f Dockerfile.cloudrun -t gcr.io/${PROJECT_ID}/${SERVICE_NAME}:latest . > /dev/null
    echo "📤 Pushing to registry..."
    docker push gcr.io/${PROJECT_ID}/${SERVICE_NAME}:latest > /dev/null
else
    echo "⏭️  Skipping build (using existing image)"
fi

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
    --quiet > /dev/null

# Get URL and test
SERVICE_URL=$(gcloud run services describe ${SERVICE_NAME} --region=${REGION} --format="value(status.url)")
echo "✅ Deployed! URL: ${SERVICE_URL}"

# Wait for deployment and test
echo "⏳ Waiting for service to be ready..."
sleep 5

# Test health
echo "🏥 Testing health endpoint..."
if curl -s "${SERVICE_URL}/api/health" | jq -r '.overall' | grep -q "healthy"; then
    echo "✅ Health check passed!"
    
    # Test queue status
    echo "📊 Testing queue status..."
    QUEUE_SIZE=$(curl -s "${SERVICE_URL}/api/queue/status" | jq -r '.queue_size')
    echo "   Queue size: ${QUEUE_SIZE}"
    echo "✅ Queue system operational!"
    
else
    echo "❌ Health check failed!"
    echo "🔍 Checking logs..."
    gcloud run services logs read ${SERVICE_NAME} --region=${REGION} --limit=10
fi

# Show logs if requested
if [ "$SHOW_LOGS" = true ]; then
    echo ""
    echo "📋 Recent logs:"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    gcloud run services logs read ${SERVICE_NAME} --region=${REGION} --limit=20
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🎯 Dev deployment complete!"
echo "   URL: ${SERVICE_URL}"
echo "   Use --skip-build to deploy without rebuilding"
echo "   Use --logs to see recent logs" 