#!/bin/bash

# CallQueueSystem - Google Cloud Run Deployment Script
# Usage: ./deploy-to-cloudrun.sh

set -e  # Exit on any error

# Configuration
PROJECT_ID="posibldashboard"
SERVICE_NAME="queue-system"
REGION="us-east1"
IMAGE_NAME="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
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

# Function to check if required tools are installed
check_dependencies() {
    print_status "Checking dependencies..."
    
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed or not in PATH"
        exit 1
    fi
    
    if ! command -v gcloud &> /dev/null; then
        print_error "Google Cloud CLI is not installed or not in PATH"
        exit 1
    fi
    
    print_success "All dependencies are available"
}

# Function to check if Docker is running
check_docker() {
    print_status "Checking Docker daemon..."
    
    if ! docker info &> /dev/null; then
        print_error "Docker daemon is not running. Please start Docker."
        print_status "For macOS with Colima: run 'colima start'"
        exit 1
    fi
    
    print_success "Docker is running"
}

# Function to set Google Cloud project
set_project() {
    print_status "Setting Google Cloud project to ${PROJECT_ID}..."
    
    gcloud config set project ${PROJECT_ID}
    
    print_success "Project set to ${PROJECT_ID}"
}

# Function to build Docker image
build_image() {
    print_status "Building Docker image..."
    
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
    print_status "Deploying to Cloud Run..."
    
    # Environment variables from env.txt
    ENV_VARS="REDIS_URL=redis://10.206.109.83:6379,QUEUE_WORKERS=10,MAX_CONCURRENT_CALLS=100,RATE_LIMIT_PER_SECOND=10,PLIVO_AUTH_ID=MAOTU3NGIYZDA2NDA5YT,PLIVO_AUTH_TOKEN=YTJkNGFlYjBiNzMxMDY0YTkyODU5YmQ2YjllODY2,PLIVO_PHONE_NUMBER=918035737670,AGENT_SERVER_URL=https://pipecat-agent-staging-443142017693.us-east1.run.app,SERVER_URL=https://pipecat-agent-staging-443142017693.us-east1.run.app,BACKEND_URL=https://backend-staging-443142017693.asia-southeast1.run.app,BACKEND_API_URL=https://backend-staging-443142017693.asia-southeast1.run.app,BACKEND_API_KEY=your_backend_api_key,ENVIRONMENT=production,LOG_LEVEL=INFO"
    
    gcloud run deploy ${SERVICE_NAME} \
        --image ${IMAGE_NAME}:latest \
        --region ${REGION} \
        --platform managed \
        --allow-unauthenticated \
        --port 8000 \
        --memory 2Gi \
        --cpu 2 \
        --min-instances 0 \
        --max-instances 10 \
        --vpc-connector=queue-system-connector \
        --vpc-egress=private-ranges-only \
        --set-env-vars "${ENV_VARS}" \
        --quiet
    
    print_success "Service deployed successfully"
}

# Function to get service URL
get_service_url() {
    print_status "Getting service URL..."
    
    SERVICE_URL=$(gcloud run services describe ${SERVICE_NAME} --region=${REGION} --format="value(status.url)")
    
    print_success "Service URL: ${SERVICE_URL}"
}

# Function to test the deployment
test_deployment() {
    print_status "Testing deployment..."
    
    # Wait a bit for the service to be ready
    sleep 5
    
    # Test health endpoint
    if curl -s "${SERVICE_URL}/api/health" | grep -q "healthy"; then
        print_success "Health check passed"
    else
        print_warning "Health check failed or service not ready yet"
    fi
    
    # Test queue status
    if curl -s "${SERVICE_URL}/api/queue/status" | grep -q "queue_size"; then
        print_success "Queue status endpoint working"
    else
        print_warning "Queue status endpoint not responding"
    fi
}

# Function to show logs
show_logs() {
    if [[ "${1}" == "--logs" ]]; then
        print_status "Showing recent logs..."
        gcloud run services logs read ${SERVICE_NAME} --region=${REGION} --limit=50
    fi
}

# Main deployment function
main() {
    print_status "🚀 Starting CallQueueSystem deployment to Google Cloud Run"
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
    print_status "Available endpoints:"
    echo "  • Health:      ${SERVICE_URL}/api/health"
    echo "  • Queue Status: ${SERVICE_URL}/api/queue/status"
    echo "  • Queue Call:   ${SERVICE_URL}/api/calls/outbound"
    echo ""
    print_status "To view logs: ./deploy-to-cloudrun.sh --logs"
    
    # Show logs if requested
    show_logs $1
}

# Run main function with all arguments
main "$@" 