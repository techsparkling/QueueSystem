# Migration Guide: From PipecatPlivoOutbound/queue-system to Standalone CallQueueSystem

## 🎯 Overview

This guide helps you migrate from the embedded queue system inside `PipecatPlivoOutbound` to the **completely standalone** `CallQueueSystem`.

## 🔄 Key Changes

### Before (Embedded System)
- ❌ Located inside `PipecatPlivoOutbound/queue-system/`
- ❌ Dependent on `peregrine_temporal_workers 3/plivo_integration.py`
- ❌ Complex import paths and dependencies
- ❌ Mixed with other project files

### After (Standalone System)
- ✅ Completely independent in `CallQueueSystem/`
- ✅ Built-in Plivo integration (`plivo_integration.py`)
- ✅ No external dependencies
- ✅ Clean, self-contained service

## 🚀 Migration Steps

### 1. **Backup Current System**
```bash
# Backup your current queue system (if you have one)
cp -r PipecatPlivoOutbound/queue-system/ backup-queue-system/
```

### 2. **Deploy Standalone System**
```bash
# Copy the new standalone system
cp -r CallQueueSystem/ /path/to/your/services/

cd CallQueueSystem

# Setup the system
./setup.sh
```

### 3. **Configure Environment**
```bash
# Copy your existing configuration
cp ../PipecatPlivoOutbound/queue-system/.env .env

# Or create new configuration
cp env.example .env
```

Edit `.env` with your settings:
```bash
# Redis Configuration
REDIS_URL=redis://localhost:6379

# Plivo Configuration (REQUIRED)
PLIVO_AUTH_ID=your_plivo_auth_id
PLIVO_AUTH_TOKEN=your_plivo_auth_token
PLIVO_NUMBER=your_plivo_number

# Agent Server Configuration (REQUIRED)
AGENT_SERVER_URL=http://localhost:8765

# Queue Configuration
QUEUE_WORKERS=10
MAX_CONCURRENT_CALLS=100
RATE_LIMIT_PER_SECOND=10
```

### 4. **Update Backend Integration**

#### Before (Old System)
```typescript
// Old way - complex Temporal integration
import { temporalClient } from './temporal-client';

await temporalClient.startWorkflow('outbound-call-workflow', {
  phone_number: "+919123456789",
  campaign_id: "campaign-123"
});
```

#### After (Standalone System)
```typescript
// New way - simple HTTP API
const response = await fetch('http://localhost:8000/api/calls/queue', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    phone_number: "+919123456789",
    campaign_id: "campaign-123",
    call_config: {
      flow_name: "wishfin-test",
      variables: { name: "John Doe" },
      answer_url: "https://your-domain.com/outbound-answer"
    }
  })
});
```

### 5. **Start the New System**
```bash
# Start the standalone queue system
python start_queue_system.py
```

### 6. **Verify Migration**
```bash
# Run comprehensive tests
python test_queue_agent_connection.py

# Check health
curl http://localhost:8000/api/health

# Test a call
curl -X POST http://localhost:8000/api/calls/queue \
  -H "Content-Type: application/json" \
  -d '{
    "phone_number": "+919123456789",
    "campaign_id": "test-migration",
    "call_config": {
      "flow_name": "wishfin-test",
      "answer_url": "https://your-domain.com/outbound-answer"
    }
  }'
```

## 🔧 Configuration Migration

### Environment Variables Mapping

| Old Variable | New Variable | Notes |
|--------------|--------------|-------|
| `REDIS_URL` | `REDIS_URL` | Same |
| `QUEUE_WORKERS` | `QUEUE_WORKERS` | Same |
| `PLIVO_AUTH_ID` | `PLIVO_AUTH_ID` | **Required in new system** |
| `PLIVO_AUTH_TOKEN` | `PLIVO_AUTH_TOKEN` | **Required in new system** |
| `AGENT_SERVER_URL` | `AGENT_SERVER_URL` | **Required in new system** |

### New Required Variables
```bash
# These are now required (were optional before)
PLIVO_NUMBER=your_plivo_number
AGENT_SERVER_URL=http://localhost:8765
```

## 📡 API Changes

### Endpoint URLs
- **Before**: Varied based on setup
- **After**: Standardized `http://localhost:8000/api/*`

### Request Format
The request format is **mostly the same**, with some improvements:

#### Enhanced Call Config
```json
{
  "phone_number": "+919123456789",
  "campaign_id": "campaign-123",
  "call_config": {
    "flow_name": "wishfin-test",
    "answer_url": "https://your-domain.com/outbound-answer",  // NEW: Required
    "variables": {
      "name": "John Doe",
      "email": "john@example.com"
    },
    "voice": "en-US",
    "max_duration": 1800,
    "recording_enabled": true
  },
  "priority": "normal",
  "max_retries": 3
}
```

## 🚨 Breaking Changes

### 1. **Plivo Integration**
- **Before**: Used external `peregrine_temporal_workers 3/plivo_integration.py`
- **After**: Built-in `plivo_integration.py`
- **Action**: No code changes needed, but verify Plivo credentials

### 2. **Answer URL**
- **Before**: Hardcoded in plivo_integration.py
- **After**: Must be provided in `call_config.answer_url`
- **Action**: Update all calls to include `answer_url`

### 3. **Import Paths**
- **Before**: Complex relative imports
- **After**: Self-contained, no imports needed
- **Action**: Remove old import statements

## 🔄 Deployment Changes

### Docker Deployment

#### Before (Complex)
```yaml
# Old docker-compose.yml had many dependencies
services:
  queue-api:
    depends_on:
      - redis
      - temporal
      - agent-service
```

#### After (Simple)
```yaml
# New docker-compose.yml is self-contained
services:
  call-queue:
    build: .
    depends_on:
      - redis  # Only Redis needed!
```

### Cloud Run Deployment

#### Before
```bash
# Old deployment required multiple services
gcloud run deploy queue-api --image=... 
gcloud run deploy temporal-worker --image=...
gcloud run deploy agent-service --image=...
```

#### After
```bash
# New deployment is single service
gcloud run deploy call-queue \
  --image=gcr.io/your-project/call-queue:latest \
  --set-env-vars="PLIVO_AUTH_ID=..." \
  --set-env-vars="AGENT_SERVER_URL=..."
```

## 🧪 Testing Migration

### 1. **Parallel Testing**
Run both systems in parallel during migration:

```bash
# Old system (if still running)
curl http://localhost:8000/old-api/health

# New system
curl http://localhost:8000/api/health
```

### 2. **Gradual Migration**
Migrate campaigns one by one:

```bash
# Test with a small campaign first
curl -X POST http://localhost:8000/api/calls/bulk-queue \
  -H "Content-Type: application/json" \
  -d '{
    "batch_id": "migration-test-1",
    "calls": [
      {
        "phone_number": "+919123456789",
        "campaign_id": "test-campaign",
        "call_config": {
          "flow_name": "wishfin-test",
          "answer_url": "https://your-domain.com/outbound-answer"
        }
      }
    ]
  }'
```

## 📊 Monitoring Migration

### Health Checks
```bash
# Check system health
curl http://localhost:8000/api/health

# Check queue status
curl http://localhost:8000/api/queue/status

# Monitor active calls
curl http://localhost:8000/api/calls/active
```

### Logs
```bash
# Monitor system logs
tail -f queue_system.log

# Monitor Redis
redis-cli monitor
```

## 🚀 Benefits After Migration

### ✅ **Simplified Architecture**
- Single service instead of multiple components
- No complex dependencies
- Easier to deploy and maintain

### ✅ **Better Performance**
- Direct Plivo integration (no proxy calls)
- Optimized Redis usage
- Faster call processing

### ✅ **Improved Reliability**
- Self-contained service
- No external service dependencies
- Better error handling

### ✅ **Easier Development**
- Standard REST APIs
- Clear documentation
- Simple testing

## 🆘 Troubleshooting Migration

### Common Issues

#### 1. **"Plivo credentials not found"**
```bash
# Solution: Set required environment variables
export PLIVO_AUTH_ID=your_auth_id
export PLIVO_AUTH_TOKEN=your_auth_token
```

#### 2. **"Agent server unreachable"**
```bash
# Solution: Verify agent server URL
curl http://localhost:8765/health
export AGENT_SERVER_URL=http://localhost:8765
```

#### 3. **"Redis connection failed"**
```bash
# Solution: Start Redis
redis-server
# Or on macOS with Homebrew
brew services start redis
```

#### 4. **"Import errors"**
```bash
# Solution: The new system is self-contained, no imports needed
# Remove any old import statements from your code
```

### Getting Help

1. **Run diagnostics**: `python test_queue_agent_connection.py`
2. **Check logs**: `tail -f queue_system.log`
3. **Verify setup**: `curl http://localhost:8000/api/health`
4. **Test Redis**: `redis-cli ping`

## 📋 Migration Checklist

- [ ] Backup current system
- [ ] Deploy standalone CallQueueSystem
- [ ] Configure environment variables
- [ ] Update backend integration code
- [ ] Test with small campaign
- [ ] Verify all health checks pass
- [ ] Monitor system performance
- [ ] Update deployment scripts
- [ ] Train team on new APIs
- [ ] Remove old system dependencies

---

**🎉 Congratulations!** You now have a **completely standalone** call queue system that's easier to deploy, maintain, and scale! 