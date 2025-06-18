# Standalone Call Queue System

A **completely independent** Redis-based queue system that replaces Temporal for handling voice call campaigns. Built for 100+ concurrent calls with Cloud Run deployment.

## 🎯 **Key Features**

- **🔄 Standalone Service**: No dependencies on external systems
- **📞 Integrated Plivo**: Built-in Plivo integration for real calls
- **⚡ Redis-based Queue**: Reliable, fast, and scalable
- **🚀 100+ Concurrent Calls**: Horizontal scaling with multiple workers
- **📊 Rate Limiting**: Configurable call rate limits
- **🔄 Retry Logic**: Exponential backoff with configurable max retries
- **⏰ Scheduling**: Support for immediate and scheduled calls
- **📈 Priority Queues**: Low, Normal, High, Urgent priorities
- **☁️ Cloud Run Ready**: Optimized for serverless deployment
- **📡 Real-time Monitoring**: Queue metrics and call status tracking
- **📦 Bulk Operations**: Batch call queuing for campaigns

## 🏗️ **Architecture**

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Backend API   │───▶│  Queue API      │───▶│   Redis Queue   │
│   (Node.js)     │    │  (FastAPI)      │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                │                       │
                                ▼                       ▼
                       ┌─────────────────┐    ┌─────────────────┐
                       │ Queue Workers   │◀───│ Scheduled Calls │
                       │ (10+ workers)   │    │                 │
                       └─────────────────┘    └─────────────────┘
                                │
                                ▼
                       ┌─────────────────┐    ┌─────────────────┐
                       │ Plivo Manager   │───▶│  Agent System   │
                       │ (Built-in)      │    │  (Voice Bot)    │
                       └─────────────────┘    └─────────────────┘
```

## 🚀 **Quick Start**

### Prerequisites

- Python 3.11+
- Redis 7+
- Plivo Account
- Voice Bot Server (running on port 8765)

### 1. Setup Environment

```bash
# Clone/copy the queue system
cp -r CallQueueSystem /path/to/your/services/

cd CallQueueSystem

# Install dependencies
pip install -r requirements.txt

# Setup environment
cp env.example .env
# Edit .env with your Plivo credentials
```

### 2. Configure Environment Variables

```bash
# .env file
REDIS_URL=redis://localhost:6379
QUEUE_WORKERS=10
MAX_CONCURRENT_CALLS=100
RATE_LIMIT_PER_SECOND=10

# Plivo Configuration
PLIVO_AUTH_ID=your_plivo_auth_id
PLIVO_AUTH_TOKEN=your_plivo_auth_token
PLIVO_NUMBER=your_plivo_number

# Agent Server Configuration
AGENT_SERVER_URL=http://localhost:8765

# API Configuration
HOST=0.0.0.0
PORT=8000
```

### 3. Start Services

```bash
# Start Redis
redis-server

# Start the complete queue system
python start_queue_system.py
```

### 4. Verify Setup

```bash
# Run tests
python test_queue_agent_connection.py

# Check health
curl http://localhost:8000/api/health
```

## 📡 **API Endpoints**

### Core Operations

#### Queue a Call
```bash
POST /api/calls/queue
Content-Type: application/json

{
  "phone_number": "+919123456789",
  "campaign_id": "campaign-123",
  "call_config": {
    "voice": "en-US",
    "max_duration": 1800,
    "recording_enabled": true,
    "flow_name": "wishfin-test",
    "answer_url": "https://your-domain.com/outbound-answer",
    "variables": {
      "name": "John Doe",
      "email": "john@example.com"
    }
  },
  "custom_call_id": "call-456",
  "scheduled_at": "2025-01-15T14:30:00Z",
  "priority": "normal",
  "max_retries": 3
}
```

#### Bulk Queue Calls
```bash
POST /api/calls/bulk-queue
Content-Type: application/json

{
  "batch_id": "campaign-batch-123",
  "calls": [
    {
      "phone_number": "+919123456789",
      "campaign_id": "campaign-123",
      "call_config": {...}
    }
  ]
}
```

#### Check Call Status
```bash
GET /api/calls/{call_id}/status
```

#### Get Queue Status
```bash
GET /api/queue/status
```

## 🔄 **Migration from Temporal**

### Before (Temporal)
```python
# Old Temporal approach
from outbound_call_workflow import trigger_outbound_call

result = await trigger_outbound_call(
    phone_number="+919123456789",
    campaign_id="campaign-123",
    call_config=config
)
```

### After (Standalone Queue)
```python
# New Standalone Queue approach
import aiohttp

async with aiohttp.ClientSession() as session:
    async with session.post("http://localhost:8000/api/calls/queue", json={
        "phone_number": "+919123456789",
        "campaign_id": "campaign-123",
        "call_config": config
    }) as response:
        result = await response.json()
```

### Backend Integration

Replace your Temporal calls with simple HTTP requests:

```typescript
// In your campaign service
async executeCampaign(campaignId: string) {
  const calls = await this.getCampaignCalls(campaignId);
  
  const response = await fetch('http://queue-service:8000/api/calls/bulk-queue', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      batch_id: `campaign-${campaignId}`,
      calls: calls.map(call => ({
        phone_number: call.phoneNumber,
        campaign_id: campaignId,
        call_config: {
          flow_name: call.flowName,
          variables: call.variables,
          answer_url: "https://your-domain.com/outbound-answer"
        }
      }))
    })
  });
  
  return await response.json();
}
```

## 🚀 **Cloud Run Deployment**

### 1. Build Container

```bash
# Build image
docker build -t gcr.io/your-project/call-queue:latest .

# Push to registry
docker push gcr.io/your-project/call-queue:latest
```

### 2. Deploy to Cloud Run

```bash
gcloud run deploy call-queue \
  --image gcr.io/your-project/call-queue:latest \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars="REDIS_URL=redis://your-redis-instance:6379" \
  --set-env-vars="QUEUE_WORKERS=20" \
  --set-env-vars="MAX_CONCURRENT_CALLS=200" \
  --set-env-vars="PLIVO_AUTH_ID=your_auth_id" \
  --set-env-vars="PLIVO_AUTH_TOKEN=your_auth_token" \
  --set-env-vars="AGENT_SERVER_URL=https://your-agent-service" \
  --memory=2Gi \
  --cpu=2 \
  --concurrency=1000 \
  --max-instances=10
```

### 3. Setup Redis (Cloud Memorystore)

```bash
gcloud redis instances create call-queue-redis \
  --size=5 \
  --region=us-central1 \
  --redis-version=redis_7_0
```

## 📊 **Monitoring & Metrics**

### Health Checks
```bash
# Service health
curl http://localhost:8000/api/health

# Queue status
curl http://localhost:8000/api/queue/status

# Active calls
curl http://localhost:8000/api/calls/active
```

### Queue Metrics
- Queue size (pending calls)
- Scheduled calls count
- Processing rate
- Success/failure rates
- Average call duration

## 🔧 **Configuration**

### Scaling for High Volume

```bash
# Environment variables for 100+ concurrent calls
QUEUE_WORKERS=20
MAX_CONCURRENT_CALLS=200
RATE_LIMIT_PER_SECOND=20
```

### Docker Compose (Production)

```yaml
version: '3.8'

services:
  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data
    command: redis-server --appendonly yes --maxmemory 1gb

  call-queue:
    build: .
    environment:
      - REDIS_URL=redis://redis:6379
      - QUEUE_WORKERS=20
      - MAX_CONCURRENT_CALLS=200
      - PLIVO_AUTH_ID=${PLIVO_AUTH_ID}
      - PLIVO_AUTH_TOKEN=${PLIVO_AUTH_TOKEN}
      - AGENT_SERVER_URL=${AGENT_SERVER_URL}
    depends_on:
      - redis
    ports:
      - "8000:8000"

volumes:
  redis_data:
```

## 🛠️ **Development**

### Running Tests
```bash
python test_queue_agent_connection.py
```

### Local Development
```bash
# Start with hot reload
uvicorn queue_api_service:app --reload --host 0.0.0.0 --port 8000
```

### Adding New Features
1. **Call Prioritization**: Modify `CallPriority` enum
2. **Custom Retry Logic**: Update `handle_failed_call` method
3. **New Endpoints**: Add to `queue_api_service.py`
4. **Monitoring**: Extend metrics in `_update_queue_metrics`

## 🚨 **Troubleshooting**

### Common Issues

1. **Redis Connection Failed**
   ```bash
   # Check Redis status
   redis-cli ping
   
   # Start Redis
   redis-server
   ```

2. **Queue Workers Not Processing**
   ```bash
   # Check logs
   tail -f queue_system.log
   
   # Restart workers
   python call_queue_manager.py
   ```

3. **Plivo Authentication Failed**
   ```bash
   # Verify credentials in .env
   echo $PLIVO_AUTH_ID
   echo $PLIVO_AUTH_TOKEN
   ```

4. **Agent Server Unreachable**
   ```bash
   # Test agent server
   curl http://localhost:8765/health
   
   # Update AGENT_SERVER_URL in .env
   ```

### Performance Tuning

1. **Increase Workers**: Scale `QUEUE_WORKERS` based on CPU cores
2. **Redis Memory**: Adjust `maxmemory` for queue size
3. **Connection Pooling**: Use Redis connection pools for high throughput
4. **Rate Limiting**: Adjust `RATE_LIMIT_PER_SECOND` based on Plivo limits

## 🔄 **Advantages over Temporal**

| Feature | Temporal | Standalone Queue |
|---------|----------|------------------|
| **Simplicity** | Complex workflows | Simple queue operations |
| **Dependencies** | External service | Self-contained |
| **Scaling** | Resource intensive | Lightweight, horizontal scaling |
| **Reliability** | Single point of failure | Redis clustering support |
| **Monitoring** | Complex setup | Built-in metrics |
| **Development** | Steep learning curve | Standard REST APIs |
| **Deployment** | Multiple components | Single service |
| **Cost** | High resource usage | Cost-effective |
| **Maintenance** | Complex upgrades | Simple updates |

## 📞 **Support**

For issues and questions:

1. **Check Logs**: `tail -f queue_system.log`
2. **Verify Redis**: `redis-cli ping`
3. **Test API**: `curl http://localhost:8000/api/health`
4. **Monitor Queue**: `curl http://localhost:8000/api/queue/status`
5. **Run Tests**: `python test_queue_agent_connection.py`

## 🎯 **Production Checklist**

- [ ] Redis configured with persistence
- [ ] Environment variables set
- [ ] Plivo credentials verified
- [ ] Agent server accessible
- [ ] Health checks passing
- [ ] Monitoring configured
- [ ] Backup strategy in place
- [ ] Rate limits configured
- [ ] SSL/TLS enabled
- [ ] Logging configured

---

**🚀 Ready for production with 100+ concurrent calls!**

**🔧 Completely standalone - no external dependencies!**

**📞 Built-in Plivo integration - no complex setup!** # QueueSystem
