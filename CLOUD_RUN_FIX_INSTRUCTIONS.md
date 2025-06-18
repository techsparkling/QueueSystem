# Cloud Run Call Tracking Fix Instructions

## 🚨 **Problem Summary**

Your queue system works locally but immediately marks calls as **failed** in Cloud Run because:

1. **Service Communication Delays**: Cloud Run services take longer to communicate than local deployment
2. **Aggressive Status Polling**: Queue checks call status too quickly (every 10s) before agent registers call  
3. **Short Timeouts**: 10-second timeouts are too short for Cloud Run networking
4. **No Retry Logic**: Single failures immediately mark calls as failed
5. **Missing Cloud Run Optimizations**: Code doesn't account for Cloud Run startup delays

## 🔧 **Fixes Applied**

### **1. Enhanced Status Polling Logic**
- Added **20-second initial delay** before first status check
- Increased status check **interval to 15 seconds**
- Added **retry logic with exponential backoff**
- Increased **request timeouts to 30 seconds**

### **2. Cloud Run Mode Detection**
- Added `CLOUD_RUN_OPTIMIZED` environment variable
- Conditional timing based on deployment environment
- Cloud Run specific headers and error handling

### **3. Improved Error Tolerance**
- Allow up to **6 consecutive errors** (vs 3 previously)
- Better distinction between "call not ready" vs "call failed"
- Enhanced logging for debugging

### **4. Multiple Status Sources**
- Primary: Plivo API (most reliable)
- Secondary: Redis callbacks 
- Fallback: Agent server polling

## 📋 **Step-by-Step Fix Instructions**

### **Step 1: Run Diagnostic (Optional)**
```bash
cd CallQueueSystem
python diagnose-cloud-run-issues.py
```
This will identify the specific issues in your current deployment.

### **Step 2: Apply Code Fixes**
The following files have been updated with Cloud Run optimizations:

- ✅ `plivo_integration.py` - Enhanced with Cloud Run polling logic
- ✅ `deploy-to-cloudrun-fixed.sh` - Updated deployment script
- ✅ `deploy.config` - Fixed service URLs

### **Step 3: Deploy Fixed Version**
```bash
# Make the deployment script executable
chmod +x deploy-to-cloudrun-fixed.sh

# Deploy with Cloud Run optimizations
./deploy-to-cloudrun-fixed.sh
```

### **Step 4: Verify Environment Variables**
The fixed deployment sets these critical environment variables:

```bash
CLOUD_RUN_OPTIMIZED=true
STATUS_CHECK_INTERVAL=15
INITIAL_STATUS_DELAY=20
REQUEST_TIMEOUT=30
MAX_STATUS_RETRIES=3
SERVICE_TIMEOUT=300
```

### **Step 5: Test the Fix**
```bash
# Check service health
curl https://your-queue-service-url/api/health

# Check queue status  
curl https://your-queue-service-url/api/queue/status

# Test a call (replace with your test data)
curl -X POST https://your-queue-service-url/api/calls/queue \
  -H "Content-Type: application/json" \
  -d '{
    "phone_number": "+919123456789",
    "campaign_id": "test-campaign",
    "call_config": {
      "flow_name": "test-flow"
    }
  }'
```

## 🌩️ **What's Different in Cloud Run Mode**

| Setting | Local Mode | Cloud Run Mode |
|---------|------------|----------------|
| Initial Delay | 5 seconds | **20 seconds** |
| Status Check Interval | 10 seconds | **15 seconds** |
| Request Timeout | 10 seconds | **30 seconds** |
| Max Retries | 2 | **3** |
| Error Tolerance | 3 consecutive | **6 consecutive** |
| Auto-Miss Detection | 45 seconds | **60 seconds** |

## 🔍 **Monitoring the Fix**

### **Check Logs for Success Indicators**
```bash
# View deployment logs
./deploy-to-cloudrun-fixed.sh --logs

# Look for these success messages:
# ✅ "🌩️ CLOUD RUN MODE: Delays=20s, Interval=15s, Timeout=30s"
# ✅ "📞 QUEUE: Initial delay of 20s for agent service to register call..."
# ✅ "✅ QUEUE: Call started successfully with status: ringing"
```

### **Monitor Call Status Changes**
Look for proper status progression:
```
📋 QUEUE: Call status changed: unknown → ringing
📋 QUEUE: Call status changed: ringing → in_progress  
📋 QUEUE: Call status changed: in_progress → completed
```

## ❌ **If Issues Persist**

### **1. Check Service URLs**
Verify these URLs are correct in your deployment:
```bash
AGENT_SERVER_URL=https://pipecat-agent-staging-443142017693.us-east1.run.app
BACKEND_URL=https://backend-staging-443142017693.asia-southeast1.run.app
```

### **2. Verify Service Health**
```bash
# Check all services are healthy
curl https://your-agent-service-url/health
curl https://your-backend-service-url/health
curl https://your-queue-service-url/api/health
```

### **3. Check Network Connectivity**
```bash
# Test service-to-service communication
python fix-cloud-run-communication.py
```

### **4. Review Environment Variables**
```bash
# Check Cloud Run service configuration
gcloud run services describe queue-system-fixed --region=us-east1
```

## 📊 **Expected Results After Fix**

### **Before (Broken)**
```
📞 QUEUE: Call initiated
📞 QUEUE: Checking status immediately... 
❌ QUEUE: Call not found - marking as FAILED
```

### **After (Fixed)**
```
📞 QUEUE: Call initiated
⏳ QUEUE: Initial delay of 20s for agent service to register call...
📞 QUEUE: Call starting/initializing... 
✅ QUEUE: Call started successfully with status: ringing
⏳ QUEUE: Waiting for completion...
✅ QUEUE: Call completed successfully
```

## 🎯 **Key Success Metrics**

- ✅ Calls no longer immediately marked as failed
- ✅ Status changes properly tracked: `unknown → ringing → in_progress → completed`
- ✅ Proper handling of missed/failed calls vs. successful calls
- ✅ Recording URLs properly forwarded to backend
- ✅ No premature timeout failures

## 🔄 **Rollback Plan**

If the fix causes issues, you can rollback:

```bash
# Deploy original version
gcloud run deploy queue-system \
  --image gcr.io/posibldashboard/queue-system:previous \
  --region us-east1

# Or remove Cloud Run optimizations
gcloud run services update queue-system \
  --remove-env-vars CLOUD_RUN_OPTIMIZED \
  --region us-east1
```

## 📞 **Support**

If you continue experiencing issues:

1. Run the diagnostic tool: `python diagnose-cloud-run-issues.py`
2. Check the logs with: `./deploy-to-cloudrun-fixed.sh --logs`
3. Verify all services are in the same region
4. Ensure both queue and agent services are properly deployed

The fix addresses the core timing and networking issues that cause call tracking failures in Cloud Run environments. 