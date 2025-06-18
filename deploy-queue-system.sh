#!/bin/bash

echo "🚀 DEPLOYING QUEUE SYSTEM WITH DISABLED BACKEND NOTIFICATIONS"
echo "==========================================================="

# Set variables
PROJECT_ID="posibldashboard"
SERVICE_NAME="queue-system"
REGION="us-east1"

echo "📦 Building and deploying queue system with latest changes..."
echo "   ✅ Backend notifications DISABLED (bot.py handles them directly)"
echo "   ✅ Enhanced error handling and logging"
echo "   ✅ Production-ready architecture"

# Deploy to Cloud Run
gcloud run deploy $SERVICE_NAME \
    --source . \
    --project $PROJECT_ID \
    --region $REGION \
    --platform managed \
    --allow-unauthenticated \
    --memory 1Gi \
    --cpu 1 \
    --timeout 3600 \
    --max-instances 5 \
    --set-env-vars="ENVIRONMENT=production" \
    --set-env-vars="REDIS_URL=redis://10.156.0.3:6379" \
    --set-env-vars="AGENT_SERVER_URL=https://pipecat-agent-staging-443142017693.us-east1.run.app" \
    --set-env-vars="BACKEND_API_URL=https://backend-staging-443142017693.asia-southeast1.run.app"

if [ $? -eq 0 ]; then
    echo "✅ Queue system deployment successful!"
    echo ""
    echo "🔗 Service URL: https://queue-system-443142017693.us-east1.run.app"
    echo ""
    echo "🎯 KEY CHANGES DEPLOYED:"
    echo "   - Backend notifications DISABLED in queue system"
    echo "   - Bot.py now handles backend notifications directly"
    echo "   - No more duplicate data issues"
    echo "   - Enhanced logging and error handling"
    echo ""
    echo "🧪 TEST THE SERVICE:"
    echo "   curl https://queue-system-443142017693.us-east1.run.app"
    echo ""
    echo "🔍 VIEW LOGS:"
    echo "   gcloud logs read --project=$PROJECT_ID --filter='resource.labels.service_name=$SERVICE_NAME' --limit=50"
else
    echo "❌ Deployment failed"
    exit 1
fi 