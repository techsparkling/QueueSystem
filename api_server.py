#!/usr/bin/env python3
"""
API Server for Call Queue System
Provides REST endpoints for queue management and call status updates
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
import redis.asyncio as redis
import os

from call_queue_manager import CallQueueManager, CallJob, CallPriority, queue_outbound_call

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Call Queue API", version="1.0.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global queue manager
queue_manager: Optional[CallQueueManager] = None

@app.on_event("startup")
async def startup_event():
    """Initialize the queue manager"""
    global queue_manager
    queue_manager = CallQueueManager(
        redis_url=os.getenv("REDIS_URL", "redis://localhost:6379")
    )
    await queue_manager.initialize()
    
    # Start workers (don't await - run in background)
    asyncio.create_task(queue_manager.start_workers(num_workers=5))
    
    logger.info("🚀 Call Queue API Server started")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    global queue_manager
    if queue_manager:
        await queue_manager.close()

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

@app.post("/api/calls/queue")
async def queue_call(request: Request):
    """Queue a new outbound call"""
    try:
        data = await request.json()
        
        phone_number = data["phone_number"]
        campaign_id = data["campaign_id"]
        call_config = data.get("call_config", {})
        custom_call_id = data.get("custom_call_id")
        scheduled_at = data.get("scheduled_at")
        priority = CallPriority(data.get("priority", 2))  # Default NORMAL
        
        call_id = await queue_outbound_call(
            phone_number=phone_number,
            campaign_id=campaign_id,
            call_config=call_config,
            custom_call_id=custom_call_id,
            scheduled_at=scheduled_at,
            priority=priority
        )
        
        return {
            "call_id": call_id,
            "status": "queued",
            "message": "Call queued successfully"
        }
        
    except Exception as e:
        logger.error(f"❌ Failed to queue call: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/calls/status")
async def get_queue_status():
    """Get queue status"""
    if not queue_manager:
        raise HTTPException(status_code=503, detail="Queue manager not initialized")
    
    return await queue_manager.get_queue_status()

@app.get("/api/calls/{call_id}/status")
async def get_call_status(call_id: str):
    """Get status of a specific call"""
    if not queue_manager:
        raise HTTPException(status_code=503, detail="Queue manager not initialized")
    
    try:
        redis_client = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))
        job_key = f"call_job:{call_id}"
        
        # Get job data
        job_data = await redis_client.hget(job_key, "job")
        if not job_data:
            raise HTTPException(status_code=404, detail="Call not found")
        
        # Parse job data
        import json
        job_dict = json.loads(job_data)
        
        return {
            "call_id": call_id,
            "status": job_dict.get("status", "unknown"),
            "phone_number": job_dict.get("phone_number"),
            "campaign_id": job_dict.get("campaign_id"),
            "created_at": job_dict.get("created_at"),
            "started_at": job_dict.get("started_at"),
            "completed_at": job_dict.get("completed_at"),
            "error": job_dict.get("error")
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to get call status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/calls/results")
async def receive_call_completion(request: Request):
    """
    Receive call completion results from agent server
    This is the endpoint that replaces the Temporal callback system
    """
    try:
        data = await request.json()
        call_id = data.get("call_id")
        
        if not call_id:
            raise HTTPException(status_code=400, detail="call_id is required")
        
        logger.info(f"📥 QUEUE: Received completion callback for call {call_id}")
        logger.info(f"   Status: {data.get('call_outcome', 'unknown')}")
        logger.info(f"   Duration: {data.get('duration_seconds', 0)}s")
        logger.info(f"   Recording: {data.get('public_recording_url', 'No recording')}")
        logger.info(f"   Transcript: {len(data.get('transcript', []))} entries")
        
        # Store completion result in Redis for the waiting queue worker
        redis_client = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))
        job_key = f"call_job:{call_id}"
        
        # Store the complete result data
        await redis_client.hset(job_key, "result", json.dumps(data))
        await redis_client.hset(job_key, "status", "completed")
        await redis_client.hset(job_key, "completed_at", datetime.utcnow().isoformat())
        
        # Set expiration for cleanup (keep for 24 hours)
        await redis_client.expire(job_key, 86400)
        
        logger.info(f"✅ QUEUE: Stored completion data for call {call_id}")
        
        return {
            "status": "success",
            "message": f"Completion data received for call {call_id}",
            "call_id": call_id
        }
        
    except Exception as e:
        logger.error(f"❌ QUEUE: Failed to process completion callback: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 