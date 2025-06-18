#!/bin/bash

# Deploy CallQueueSystem to Google Cloud Run with Cloud Run Optimizations
# This script fixes the call tracking issues in Cloud Run deployment

set -e

# Configuration
PROJECT_ID="posibldashboard"
SERVICE_NAME="queue-system-fixed"
REGION="us-east1"
IMAGE_NAME="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"

# Cloud Run Communication Fix
AGENT_SERVICE_URL="https://pipecat-agent-staging-443142017693.us-east1.run.app"
BACKEND_URL="https://backend-staging-443142017693.asia-southeast1.run.app"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check dependencies
check_dependencies() {
    print_status "Checking dependencies..."
    
    if ! command -v gcloud &> /dev/null; then
        print_error "gcloud CLI not found. Please install Google Cloud SDK."
        exit 1
    fi
    
    if ! command -v docker &> /dev/null; then
        print_error "Docker not found. Please install Docker."
        exit 1
    fi
    
    print_success "All dependencies found"
}

# Function to check Docker
check_docker() {
    print_status "Checking Docker daemon..."
    
    if ! docker info &> /dev/null; then
        print_error "Docker daemon is not running. Please start Docker."
        exit 1
    fi
    
    print_success "Docker daemon is running"
}

# Function to set project
set_project() {
    print_status "Setting Google Cloud project..."
    
    gcloud config set project ${PROJECT_ID}
    
    print_success "Project set to ${PROJECT_ID}"
}

# Function to build Docker image
build_image() {
    print_status "Building Docker image with Cloud Run optimizations..."
    
    # Get current timestamp for tagging
    TIMESTAMP=$(date +%Y%m%d-%H%M%S)
    
    # Build with both latest and timestamp tags
    docker build -f Dockerfile.cloudrun -t ${IMAGE_NAME}:latest -t ${IMAGE_NAME}:${TIMESTAMP} .
    
    print_success "Docker image built successfully"
    print_status "Tags: latest, ${TIMESTAMP}"
}

# Function to push Docker image
push_image() {
    print_status "Pushing Docker image to Google Container Registry..."
    
    docker push ${IMAGE_NAME}:latest
    
    print_success "Docker image pushed successfully"
}

# Function to deploy to Cloud Run
deploy_service() {
    print_status "Deploying to Cloud Run with Cloud Run optimizations..."
    
    # FIXED: Environment variables optimized for Cloud Run
    ENV_VARS="REDIS_URL=redis://10.206.109.83:6379"
    ENV_VARS="${ENV_VARS},QUEUE_WORKERS=10"
    ENV_VARS="${ENV_VARS},MAX_CONCURRENT_CALLS=100"
    ENV_VARS="${ENV_VARS},RATE_LIMIT_PER_SECOND=10"
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
    # CLOUD RUN OPTIMIZATIONS
    ENV_VARS="${ENV_VARS},CLOUD_RUN_OPTIMIZED=true"
    ENV_VARS="${ENV_VARS},SERVICE_TIMEOUT=300"
    ENV_VARS="${ENV_VARS},STATUS_CHECK_INTERVAL=15"
    ENV_VARS="${ENV_VARS},MAX_STATUS_RETRIES=3"
    ENV_VARS="${ENV_VARS},INITIAL_STATUS_DELAY=20"
    ENV_VARS="${ENV_VARS},REQUEST_TIMEOUT=30"
    
    print_status "🌩️ Cloud Run optimizations enabled:"
    print_status "   - Initial delay: 20 seconds"
    print_status "   - Status check interval: 15 seconds"
    print_status "   - Request timeout: 30 seconds"
    print_status "   - Max retries: 3"
    print_status "   - Service timeout: 5 minutes"
    
    gcloud run deploy ${SERVICE_NAME} \
        --image ${IMAGE_NAME}:latest \
        --region ${REGION} \
        --platform managed \
        --allow-unauthenticated \
        --port 8000 \
        --memory 4Gi \
        --cpu 2 \
        --min-instances 1 \
        --max-instances 10 \
        --timeout 300 \
        --concurrency 50 \
        --vpc-connector=queue-system-connector \
        --vpc-egress=private-ranges-only \
        --set-env-vars "${ENV_VARS}" \
        --quiet
    
    print_success "Service deployed successfully with Cloud Run optimizations"
}

# Function to get service URL
get_service_url() {
    print_status "Getting service URL..."
    
    SERVICE_URL=$(gcloud run services describe ${SERVICE_NAME} --region=${REGION} --format="value(status.url)")
    
    print_success "Service URL: ${SERVICE_URL}"
    export SERVICE_URL
}

# Function to test deployment
test_deployment() {
    print_status "Testing deployment..."
    
    # Test health endpoint
    HEALTH_URL="${SERVICE_URL}/api/health"
    
    print_status "Testing health endpoint: ${HEALTH_URL}"
    
    for i in {1..5}; do
        if curl -s -f "${HEALTH_URL}" > /dev/null; then
            print_success "Health check passed"
            break
        else
            print_warning "Health check failed (attempt ${i}/5). Retrying in 10 seconds..."
            sleep 10
        fi
        
        if [ $i -eq 5 ]; then
            print_error "Health check failed after 5 attempts"
            return 1
        fi
    done
    
    # Test queue status
    STATUS_URL="${SERVICE_URL}/api/queue/status"
    print_status "Testing queue status endpoint: ${STATUS_URL}"
    
    if curl -s -f "${STATUS_URL}" > /dev/null; then
        print_success "Queue status endpoint working"
    else
        print_warning "Queue status endpoint not responding"
    fi
}

# Function to show logs
show_logs() {
    if [ "$1" == "--logs" ]; then
        print_status "Showing recent logs..."
        gcloud run services logs read ${SERVICE_NAME} --region=${REGION} --limit=50
    fi
}

# Main function
main() {
    print_status "🚀 Starting CallQueueSystem deployment to Google Cloud Run with Cloud Run fixes"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    # Run all steps
    check_dependencies
    check_docker
    set_project
    build_image
    push_image
    deploy_service
    get_service_url
    test_deployment
    
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    print_success "🎉 Deployment completed successfully!"
    print_status "Service URL: ${SERVICE_URL}"
    print_status "Region: ${REGION}"
    print_status "Project: ${PROJECT_ID}"
    echo ""
    print_status "🌩️ Cloud Run optimizations applied:"
    echo "  ✅ Extended startup delays (20s initial delay)"
    echo "  ✅ Longer status check intervals (15s)"
    echo "  ✅ Increased request timeouts (30s)"
    echo "  ✅ Enhanced retry logic (3 retries with backoff)"
    echo "  ✅ Cloud Run specific headers and error handling"
    echo ""
    print_status "Available endpoints:"
    echo "  • Health:      ${SERVICE_URL}/api/health"
    echo "  • Queue Status: ${SERVICE_URL}/api/queue/status"
    echo "  • Queue Call:   ${SERVICE_URL}/api/calls/queue"
    echo ""
    print_status "🔧 The following issues have been fixed:"
    echo "  ✅ Premature call failure marking"
    echo "  ✅ Service-to-service communication timeouts"
    echo "  ✅ Call status polling too aggressive"
    echo "  ✅ Cloud Run networking issues"
    echo "  ✅ Agent service startup timing"
    echo ""
    print_status "To view logs: ./deploy-to-cloudrun-fixed.sh --logs"
    
    # Show logs if requested
    show_logs $1
}

# Run main function with all arguments
main "$@" 