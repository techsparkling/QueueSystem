#!/bin/bash

# PRODUCTION CLOUD RUN DEPLOYMENT SCRIPT
# Deploys the queue system with proper Cloud Run optimizations

set -e

echo "🏭 PRODUCTION: Starting Cloud Run deployment with networking fixes..."

# Project configuration
PROJECT_ID="posibldashboard"
REGION="us-east1"
SERVICE_NAME="queue-production"

# Service URLs (production environment)
SERVER_URL="https://pipecat-agent-staging-443142017693.us-east1.run.app"
AGENT_SERVER_URL="https://pipecat-agent-staging-443142017693.us-east1.run.app"
BACKEND_API_URL="https://backend-staging-443142017693.asia-southeast1.run.app"

# Redis configuration
REDIS_HOST="10.206.109.83"
REDIS_PORT="6379"

# Plivo credentials (from environment)
if [ -z "$PLIVO_AUTH_ID" ] || [ -z "$PLIVO_AUTH_TOKEN" ] || [ -z "$PLIVO_PHONE_NUMBER" ]; then
    echo "❌ Missing Plivo credentials. Please set PLIVO_AUTH_ID, PLIVO_AUTH_TOKEN, PLIVO_PHONE_NUMBER"
    exit 1
fi

echo "📋 PRODUCTION: Configuration:"
echo "   Project: $PROJECT_ID"
echo "   Region: $REGION"
echo "   Service: $SERVICE_NAME"
echo "   Agent URL: $AGENT_SERVER_URL"
echo "   Backend URL: $BACKEND_API_URL"
echo "   Redis: $REDIS_HOST:$REDIS_PORT"
echo "   Plivo Number: $PLIVO_PHONE_NUMBER"

# Authenticate if needed
echo "🔐 PRODUCTION: Checking authentication..."
if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | grep -q .; then
    echo "❌ Not authenticated with gcloud. Please run: gcloud auth login"
    exit 1
fi

# Set project
gcloud config set project $PROJECT_ID

echo "🚀 PRODUCTION: Building and deploying to Cloud Run..."

# Deploy with production-optimized settings
gcloud run deploy $SERVICE_NAME \
    --source . \
    --region $REGION \
    --platform managed \
    --allow-unauthenticated \
    --memory 2Gi \
    --cpu 2 \
    --timeout 3600 \
    --concurrency 80 \
    --max-instances 10 \
    --set-env-vars "AGENT_SERVER_URL=$AGENT_SERVER_URL" \
    --set-env-vars "BACKEND_API_URL=$BACKEND_API_URL" \
    --set-env-vars "REDIS_HOST=$REDIS_HOST" \
    --set-env-vars "REDIS_PORT=$REDIS_PORT" \
    --set-env-vars "REDIS_URL=redis://$REDIS_HOST:$REDIS_PORT" \
    --set-env-vars "PLIVO_AUTH_ID=$PLIVO_AUTH_ID" \
    --set-env-vars "PLIVO_AUTH_TOKEN=$PLIVO_AUTH_TOKEN" \
    --set-env-vars "SERVER_URL=$SERVER_URL" \
    --set-env-vars "PLIVO_PHONE_NUMBER=$PLIVO_PHONE_NUMBER" \
    --set-env-vars "GOOGLE_CLOUD_PROJECT=$PROJECT_ID" \
    --set-env-vars "CLOUD_RUN_OPTIMIZED=true" \
    --set-env-vars "STATUS_CHECK_INTERVAL=20" \
    --set-env-vars "INITIAL_STATUS_DELAY=30" \
    --set-env-vars "REQUEST_TIMEOUT=45" \
    --set-env-vars "MAX_STATUS_RETRIES=5" \
    --set-env-vars "STARTUP_TIMEOUT=300" \
    --set-env-vars "PRODUCTION_MODE=true" \
    --port 8080

if [ $? -eq 0 ]; then
    echo "✅ PRODUCTION: Deployment successful!"
    
    # Get service URL
    SERVICE_URL=$(gcloud run services describe $SERVICE_NAME --region=$REGION --format='value(status.url)')
    echo "🌐 PRODUCTION: Service URL: $SERVICE_URL"
    
    echo ""
    echo "🔧 PRODUCTION: Testing deployment..."
    
    # Test health endpoint
    echo "📋 Testing health endpoint..."
    curl -f "$SERVICE_URL/health" || echo "❌ Health check failed"
    
    # Test queue status
    echo "📋 Testing queue status..."
    curl -f "$SERVICE_URL/queue-status" || echo "❌ Queue status failed"
    
    echo ""
    echo "🎉 PRODUCTION: Deployment completed successfully!"
    echo ""
    echo "📋 PRODUCTION: Service Details:"
    echo "   URL: $SERVICE_URL"
    echo "   Status: $(gcloud run services describe $SERVICE_NAME --region=$REGION --format='value(status.conditions[0].status)')"
    echo "   Environment: Production with Cloud Run optimizations"
    echo "   Data Source: production_cloudrun_manager"
    echo ""
    echo "🧪 PRODUCTION: To test calls:"
    echo "   curl -X POST $SERVICE_URL/queue-call \\"
    echo "        -H 'Content-Type: application/json' \\"
    echo "        -d '{\"phone_number\":\"+1234567890\",\"campaign_id\":\"test\"}'"
    echo ""
    echo "📊 PRODUCTION: To monitor:"
    echo "   gcloud run services logs read $SERVICE_NAME --region=$REGION --follow"
    echo ""
    echo "🛠️ PRODUCTION: Environment Variables Set:"
    echo "   - CLOUD_RUN_OPTIMIZED=true (extended timeouts)"
    echo "   - STATUS_CHECK_INTERVAL=20 (slower polling)"
    echo "   - INITIAL_STATUS_DELAY=30 (longer startup wait)"
    echo "   - REQUEST_TIMEOUT=45 (longer request timeout)"
    echo "   - STARTUP_TIMEOUT=300 (5 minute startup timeout)"
    echo "   - PRODUCTION_MODE=true (production optimizations)"
    
else
    echo "❌ PRODUCTION: Deployment failed!"
    exit 1
fi 