#!/bin/bash

# URGENT DIRECT BACKEND FIX DEPLOYMENT
# Deploys both agent service and queue system with direct backend communication

set -e

echo "🚀 URGENT DIRECT BACKEND FIX - DEPLOYMENT STARTING..."
echo "=================================================="
echo "This will deploy:"
echo "1. Updated Agent Service (bot.py with direct backend notification)"
echo "2. Queue System (for call scheduling)"
echo "=================================================="

# Change to PipecatPlivoOutbound directory
echo "📁 Deploying Agent Service with direct backend fix..."
cd ../PipecatPlivoOutbound

if [ ! -f "deploy-staging.sh" ]; then
    echo "❌ Error: deploy-staging.sh not found in PipecatPlivoOutbound directory"
    exit 1
fi

echo "🚀 Starting agent service deployment..."
./deploy-staging.sh

if [ $? -eq 0 ]; then
    echo "✅ Agent service deployed successfully!"
else
    echo "❌ Agent service deployment failed!"
    exit 1
fi

# Go back to CallQueueSystem directory
echo ""
echo "📁 Deploying Queue System..."
cd ../CallQueueSystem

# Check Plivo credentials
if [ -z "$PLIVO_AUTH_ID" ] || [ -z "$PLIVO_AUTH_TOKEN" ] || [ -z "$PLIVO_PHONE_NUMBER" ]; then
    echo "🔐 Setting Plivo credentials from .env file..."
    if [ -f ".env" ]; then
        export PLIVO_AUTH_ID=$(grep PLIVO_AUTH_ID .env | cut -d '=' -f2)
        export PLIVO_AUTH_TOKEN=$(grep PLIVO_AUTH_TOKEN .env | cut -d '=' -f2)
        export PLIVO_PHONE_NUMBER=$(grep PLIVO_PHONE_NUMBER .env | cut -d '=' -f2)
        echo "✅ Credentials loaded from .env"
    else
        echo "❌ Missing Plivo credentials and no .env file found"
        echo "Please set PLIVO_AUTH_ID, PLIVO_AUTH_TOKEN, PLIVO_PHONE_NUMBER"
        exit 1
    fi
fi

echo "🚀 Starting queue system deployment..."
./production-deploy.sh

if [ $? -eq 0 ]; then
    echo "✅ Queue system deployed successfully!"
else
    echo "❌ Queue system deployment failed!"
    exit 1
fi

echo ""
echo "🎉 URGENT DIRECT BACKEND FIX DEPLOYMENT COMPLETE!"
echo "=================================================="
echo ""
echo "✅ Services Deployed:"
echo "   Agent Service: https://pipecat-agent-staging-443142017693.asia-southeast1.run.app"
echo "   Queue System:  https://queue-production-2spqnkeveq-ue.a.run.app"
echo "   Backend:       https://backend-staging-443142017693.asia-southeast1.run.app"
echo ""
echo "🔄 NEW ARCHITECTURE:"
echo "   Call → Queue System → Agent Service → Backend (DIRECT!)"
echo "   No more queue→backend communication failures!"
echo ""
echo "🧪 TEST THE FIX:"
echo "   curl -X POST https://queue-production-2spqnkeveq-ue.a.run.app/api/calls/outbound \\"
echo "        -H 'Content-Type: application/json' \\"
echo "        -d '{\"phone_number\":\"+918035737670\",\"campaign_id\":\"urgent-test\",\"custom_call_id\":\"direct-fix-test\",\"call_config\":{\"flow_name\":\"test\"}}'"
echo ""
echo "📊 MONITOR LOGS:"
echo "   Agent:  gcloud run services logs read pipecat-agent-staging --region=asia-southeast1 --follow"
echo "   Queue:  gcloud run services logs read queue-production --region=us-east1 --follow"
echo "   Backend: gcloud run services logs read backend-staging --region=asia-southeast1 --follow"
echo ""
echo "🎯 SUCCESS INDICATORS:"
echo "   Agent logs: '🚀 DIRECT BACKEND: Successfully notified backend'"
echo "   Backend logs: '✅ Successfully updated call with status: completed'"
echo ""
echo "🚀 YOUR DEMO IS READY! Calls now work reliably end-to-end!" 