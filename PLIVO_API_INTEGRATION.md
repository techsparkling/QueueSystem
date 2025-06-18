# Plivo API Integration - Ground Truth Call Status

## Overview

The queue system now uses **direct Plivo API checking** like the Temporal system did, providing ground truth call status from the telecom carrier instead of relying only on agent server tracking.

## Why This is Better

### **Before: Agent Server Only** ❌
```python
# Only checked agent server
GET /call-status/{call_id}
# Problems:
# - Agent server might crash/restart
# - Call state could be lost
# - No ground truth from carrier
# - Manual hangups not detected
```

### **After: Plivo API Primary** ✅
```python
# Direct Plivo API check (like Temporal)
plivo_client.calls.get(call_uuid)
# Benefits:
# - Ground truth from telecom carrier
# - Never loses call state
# - Accurate duration & hangup cause
# - Detects all call endings
```

## Architecture

### **Triple Priority System**
```
1. 🚀 Redis Callbacks (Fastest - agent notifications)
2. 📞 Plivo API (Ground Truth - telecom carrier)  
3. 🤖 Agent Server (Fallback - transcript/recording)
```

### **Data Combination**
```python
# Plivo provides: Call status, duration, hangup cause (PRIMARY)
# Agent provides: Transcript, recording URL (SECONDARY)
# Combined: Complete call result with both telecom + AI data
```

## Call Status Flow

### **1. Call Initiation**
```python
# Store Plivo UUID for later API checking
result = await initiate_call(...)
plivo_uuid = result.get("plivo_call_uuid")
await redis_client.hset(f"call_job:{call_id}", "plivo_uuid", plivo_uuid)
```

### **2. Status Checking Loop**
```python
while not_completed:
    # Priority 1: Check Redis for agent callbacks
    if callback_data_in_redis:
        return callback_data
    
    # Priority 2: Check Plivo API (GROUND TRUTH)
    if plivo_uuid:
        plivo_status = await check_plivo_call_status(plivo_uuid)
        if plivo_status in ["completed", "failed", "missed"]:
            agent_data = await check_call_status(call_id)  # Get transcript
            return combine_plivo_agent_data(plivo_status, agent_data)
    
    # Priority 3: Agent server fallback
    agent_status = await check_call_status(call_id)
    # Continue or complete based on agent status
```

### **3. Status Mapping**
```python
# Plivo → Our System
"queued" → "initiated"
"ringing" → "ringing" 
"in-progress" → "in_progress"
"completed" + duration>5s → "completed"
"completed" + duration<5s → "missed"
"failed" → "failed"
"busy" → "busy" 
"no-answer" → "missed"
```

## Benefits

### **✅ Reliability**
- **Never loses call state** - Plivo keeps records permanently
- **Ground truth status** - From actual telecom carrier
- **Accurate duration** - Billing-grade precision from carrier

### **✅ Completeness** 
- **All call endings detected** - Manual hangups, network drops, etc.
- **Proper hangup causes** - busy, no-answer, rejected, completed
- **Complete data** - Telecom status + AI transcript/recording

### **✅ Production Ready**
- **Same as Temporal** - Proven approach from working system
- **Carrier-grade** - Uses telecom industry standard APIs
- **Monitoring** - Clear logging of all status sources

## Usage Examples

### **Manual Hangup Detection**
```python
# Before: Queue stuck polling forever
# After: Plivo API detects "completed" with hangup_cause="user_hangup"
```

### **Network Issues**
```python
# Before: Agent server unreachable = stuck
# After: Plivo API still accessible = completion detected
```

### **Missed Calls**
```python
# Before: Hard to distinguish missed vs completed
# After: Plivo provides exact hangup_cause="no_answer"
```

## Implementation Details

### **Key Methods**
- `check_plivo_call_status()` - Direct Plivo API call
- `_map_plivo_status()` - Status mapping logic
- `_combine_plivo_agent_data()` - Merge telecom + AI data

### **Data Structure**
```python
{
    "call_id": "backend_call_id",
    "status": "completed",           # Our mapped status
    "call_outcome": "completed",     # Final outcome
    "duration": 45,                  # From Plivo (billing accurate)
    "hangup_cause": "normal_call",   # From Plivo
    "transcript": [...],             # From agent server
    "recording_file": "gcs://...",   # From agent server
    "plivo_data": {...},             # Complete Plivo response
    "data_source": "plivo_api_primary"
}
```

## Monitoring

### **Logs to Watch**
```bash
📞 QUEUE: Checking Plivo API for call status: call_uuid
📋 PLIVO: Call uuid - Status: completed, Duration: 45s, Cause: normal_call
✅ QUEUE: Call confirmed completed via Plivo API: completed
📋 QUEUE: Combined data: Plivo(completed, 45s) + Agent(12 transcript, uploaded recording)
```

### **Error Handling**
- **Plivo API error** → Falls back to agent server
- **Agent server error** → Uses Plivo data only
- **Both fail** → Creates timeout result

## Result

The queue system now has the **same reliability as the Temporal system** with ground truth call status from Plivo API, combined with rich AI data from the agent server. No more stuck polling or missed call completions! 🎉 