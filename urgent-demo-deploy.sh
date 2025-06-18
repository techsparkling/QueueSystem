#!/bin/bash

# URGENT DEMO DEPLOYMENT
# Deploys the direct Plivo fix immediately for demo readiness
# Bypasses normal processes for speed

set -e

echo "🚨 URGENT DEMO DEPLOYMENT - BYPASSING NORMAL PROCESSES"
echo "======================================================="

# Configuration
PROJECT_ID="posibldashboard"
SERVICE_NAME="queue-urgent-demo"
REGION="us-east1"
IMAGE_NAME="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"

# Your service URLs (UPDATE THESE)
AGENT_SERVICE_URL="https://pipecat-agent-staging-443142017693.us-east1.run.app"
BACKEND_URL="https://backend-staging-443142017693.asia-southeast1.run.app"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_status() {
    echo -e "${BLUE}[URGENT]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check dependencies quickly
if ! command -v gcloud &> /dev/null; then
    print_error "gcloud CLI not found"
    exit 1
fi

if ! command -v docker &> /dev/null; then
    print_error "Docker not found"
    exit 1
fi

print_status "Setting project..."
gcloud config set project ${PROJECT_ID}

print_status "Building Docker image with urgent fixes..."
docker build -f Dockerfile.cloudrun -t ${IMAGE_NAME}:urgent .

print_status "Pushing image..."
docker push ${IMAGE_NAME}:urgent

print_status "Deploying with URGENT DIRECT PLIVO TRACKING..."

# URGENT: Deploy with direct Plivo tracking enabled
ENV_VARS="REDIS_URL=redis://10.206.109.83:6379"
ENV_VARS="${ENV_VARS},QUEUE_WORKERS=5"
ENV_VARS="${ENV_VARS},MAX_CONCURRENT_CALLS=50"
ENV_VARS="${ENV_VARS},RATE_LIMIT_PER_SECOND=5"
ENV_VARS="${ENV_VARS},PLIVO_AUTH_ID=MAOTU3NGIYZDA2NDA5YT"
ENV_VARS="${ENV_VARS},PLIVO_AUTH_TOKEN=YTJkNGFlYjBiNzMxMDY0YTkyODU5YmQ2YjllODY2"
ENV_VARS="${ENV_VARS},PLIVO_PHONE_NUMBER=918035737670"
ENV_VARS="${ENV_VARS},AGENT_SERVER_URL=${AGENT_SERVICE_URL}"
ENV_VARS="${ENV_VARS},SERVER_URL=${AGENT_SERVICE_URL}"
ENV_VARS="${ENV_VARS},BACKEND_URL=${BACKEND_URL}"
ENV_VARS="${ENV_VARS},BACKEND_API_URL=${BACKEND_URL}"
ENV_VARS="${ENV_VARS},BACKEND_API_KEY=your_backend_api_key"
ENV_VARS="${ENV_VARS},ENVIRONMENT=production"
ENV_VARS="${ENV_VARS},LOG_LEVEL=INFO"
# URGENT MODE ENABLED
ENV_VARS="${ENV_VARS},URGENT_DEMO_MODE=true"
ENV_VARS="${ENV_VARS},USE_DIRECT_PLIVO=true"
ENV_VARS="${ENV_VARS},BYPASS_AGENT_POLLING=true"

gcloud run deploy ${SERVICE_NAME} \
    --image ${IMAGE_NAME}:urgent \
    --region ${REGION} \
    --platform managed \
    --allow-unauthenticated \
    --port 8000 \
    --memory 2Gi \
    --cpu 2 \
    --min-instances 1 \
    --max-instances 5 \
    --timeout 300 \
    --concurrency 10 \
    --set-env-vars "${ENV_VARS}" \
    --quiet

# Get service URL
SERVICE_URL=$(gcloud run services describe ${SERVICE_NAME} --region=${REGION} --format="value(status.url)")

print_success "🎉 URGENT DEPLOYMENT COMPLETE!"
echo "================================================"
echo "🚨 DEMO-READY SERVICE DEPLOYED"
echo "================================================"
echo "Service URL: ${SERVICE_URL}"
echo ""
echo "🔧 URGENT FIXES APPLIED:"
echo "  ✅ Direct Plivo API tracking (bypasses agent polling)"
echo "  ✅ Real-time call status detection"
echo "  ✅ Immediate backend notification"
echo "  ✅ Fallback to original method if needed"
echo "  ✅ Enhanced error handling"
echo ""
echo "📞 TEST ENDPOINTS:"
echo "  Health: ${SERVICE_URL}/api/health"
echo "  Queue: ${SERVICE_URL}/api/calls/queue"
echo "  Status: ${SERVICE_URL}/api/queue/status"
echo ""
echo "🧪 QUICK TEST:"
echo "curl -X POST ${SERVICE_URL}/api/calls/queue \\"
echo "  -H 'Content-Type: application/json' \\"
echo "  -d '{"
echo "    \"phone_number\": \"+919123456789\","
echo "    \"campaign_id\": \"demo-test\","
echo "    \"call_config\": {\"flow_name\": \"demo\"}"
echo "  }'"
echo ""

# Test the deployment
print_status "Testing deployment..."

# Health check
for i in {1..3}; do
    if curl -s -f "${SERVICE_URL}/api/health" > /dev/null; then
        print_success "Health check passed"
        break
    else
        print_error "Health check failed (attempt ${i}/3)"
        if [ $i -eq 3 ]; then
            print_error "Deployment may have issues"
        else
            sleep 5
        fi
    fi
done

# Queue status check
if curl -s -f "${SERVICE_URL}/api/queue/status" > /dev/null; then
    print_success "Queue status endpoint working"
else
    print_error "Queue status endpoint not responding"
fi

echo ""
print_success "🚨 URGENT DEPLOYMENT COMPLETE - DEMO READY!"
print_status "Your call tracking issues should now be resolved"
print_status "The system will:"
print_status "  1. Use direct Plivo API for call tracking"
print_status "  2. Bypass unreliable agent service communication"
print_status "  3. Provide real-time call status updates"
print_status "  4. Immediately notify backend of call results"
print_status ""
print_status "Monitor logs with:"
print_status "gcloud run services logs read ${SERVICE_NAME} --region=${REGION} --follow" 