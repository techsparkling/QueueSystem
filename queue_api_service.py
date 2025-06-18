#!/usr/bin/env python3
"""
Queue API Service - FastAPI service to replace Temporal endpoints
Provides REST API for call queuing and management
"""

import asyncio
import os
from datetime import datetime
from typing import Dict, Any, Optional, List
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv
import logging

from call_queue_manager import CallQueueManager, CallJob, CallPriority, CallStatus

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global queue manager instance
queue_manager: Optional[CallQueueManager] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management"""
    global queue_manager
    
    # Startup
    logger.info("🚀 Starting Queue API Service...")
    queue_manager = CallQueueManager(
        redis_url=os.getenv("REDIS_URL", "redis://localhost:6379")
    )
    await queue_manager.initialize()
    
    # Start workers in background
    asyncio.create_task(queue_manager.start_workers(num_workers=int(os.getenv("QUEUE_WORKERS", "10"))))
    
    logger.info("✅ Queue API Service ready!")
    
    yield
    
    # Shutdown
    logger.info("🛑 Shutting down Queue API Service...")
    if queue_manager:
        await queue_manager.close()

# Create FastAPI app
app = FastAPI(
    title="Call Queue API",
    description="Redis-based call queue system replacing Temporal",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== PYDANTIC MODELS ====================

class CallRequest(BaseModel):
    """Request model for queuing a call"""
    phone_number: str = Field(..., description="Phone number to call")
    campaign_id: str = Field(..., description="Campaign identifier")
    call_config: Dict[str, Any] = Field(default_factory=dict, description="Call configuration")
    custom_call_id: Optional[str] = Field(None, description="Custom call ID")
    scheduled_at: Optional[str] = Field(None, description="ISO timestamp for scheduled execution")
    priority: str = Field("normal", description="Call priority: low, normal, high, urgent")
    max_retries: int = Field(3, description="Maximum retry attempts")
    
    class Config:
        schema_extra = {
            "example": {
                "phone_number": "+919123456789",
                "campaign_id": "campaign-123",
                "call_config": {
                    "voice": "en-US",
                    "max_duration": 1800,
                    "recording_enabled": True,
                    "flow_name": "wishfin-test",
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
        }

class CallResponse(BaseModel):
    """Response model for call operations"""
    success: bool
    message: str
    call_id: str
    queue_position: Optional[int] = None
    estimated_execution: Optional[str] = None

class BulkCallRequest(BaseModel):
    """Request model for bulk call operations"""
    calls: List[CallRequest]
    batch_id: Optional[str] = None

class QueueStatus(BaseModel):
    """Queue status response"""
    queue_size: int
    scheduled_size: int
    processing_count: int
    completed_today: int
    failed_today: int
    updated_at: str

# ==================== API ENDPOINTS ====================

@app.get("/", response_model=Dict[str, str])
async def root():
    """Health check endpoint"""
    return {
        "service": "Call Queue API",
        "status": "running",
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat()
    }

@app.post("/api/calls/outbound", response_model=CallResponse)
async def queue_call(request: CallRequest):
    """
    Queue a single outbound call
    This replaces Temporal's trigger_outbound_call function
    """
    try:
        if not queue_manager:
            raise HTTPException(status_code=503, detail="Queue manager not initialized")
        
        # Convert priority string to enum
        priority_map = {
            "low": CallPriority.LOW,
            "normal": CallPriority.NORMAL,
            "high": CallPriority.HIGH,
            "urgent": CallPriority.URGENT
        }
        priority = priority_map.get(request.priority.lower(), CallPriority.NORMAL)
        
        # CRITICAL FIX: Use backend call_id as primary ID - NO MORE RANDOM QUEUE IDs!
        backend_call_id = request.custom_call_id
        
        if not backend_call_id:
            raise HTTPException(status_code=400, detail="custom_call_id (backend call_id) is required for proper tracking")
        
        # Enhanced call_config with backend call_id for proper tracking
        enhanced_call_config = {
            **request.call_config,
            "backend_call_id": backend_call_id,  # Store backend call_id in config
            "flow_name": request.call_config.get("flow_name", "wishfin-test"),
            "variables": request.call_config.get("variables", {}),
            "data_source": "call_queue_api"
        }
        
        # Create call job using backend call_id as primary ID - CONSISTENT TRACKING!
        call_job = CallJob(
            id=backend_call_id,  # Use backend call_id as primary ID
            phone_number=request.phone_number,
            campaign_id=request.campaign_id,
            call_config=enhanced_call_config,
            custom_call_id=backend_call_id,  # Same as primary ID for consistency
            scheduled_at=request.scheduled_at,
            priority=priority,
            max_retries=request.max_retries
        )
        
        # Queue the call
        job_id = await queue_manager.enqueue_call(call_job)
        
        # Get queue status for position estimate
        queue_status = await queue_manager.get_queue_status()
        
        logger.info(f"✅ Call queued: ID: {job_id}, Phone: {request.phone_number}")
        logger.info(f"📋 Variables: {len(enhanced_call_config.get('variables', {}))}, Flow: {enhanced_call_config.get('flow_name')}")
        
        return CallResponse(
            success=True,
            message="Call queued successfully",
            call_id=job_id,  # Return the backend call_id (which is now the primary ID)
            queue_position=queue_status.get("queue_size", 0),
            estimated_execution=request.scheduled_at or "immediate"
        )
        
    except Exception as e:
        logger.error(f"❌ Failed to queue call: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to queue call: {str(e)}")

@app.post("/api/calls/bulk-queue", response_model=Dict[str, Any])
async def bulk_queue_calls(request: BulkCallRequest):
    """
    Queue multiple calls in bulk
    Useful for campaign execution
    """
    try:
        if not queue_manager:
            raise HTTPException(status_code=503, detail="Queue manager not initialized")
        
        results = []
        batch_id = request.batch_id or f"batch-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"
        
        for i, call_request in enumerate(request.calls):
            try:
                # Convert priority
                priority_map = {
                    "low": CallPriority.LOW,
                    "normal": CallPriority.NORMAL,
                    "high": CallPriority.HIGH,
                    "urgent": CallPriority.URGENT
                }
                priority = priority_map.get(call_request.priority.lower(), CallPriority.NORMAL)
                
                # CRITICAL FIX: Require backend call_id for all calls
                if not call_request.custom_call_id:
                    raise ValueError(f"custom_call_id is required for call {i+1} - backend call_id needed for tracking")
                
                # Create call job using backend call_id as primary ID
                call_job = CallJob(
                    id=call_request.custom_call_id,  # Use backend call_id as primary ID
                    phone_number=call_request.phone_number,
                    campaign_id=call_request.campaign_id,
                    call_config={**call_request.call_config, "batch_id": batch_id},
                    custom_call_id=call_request.custom_call_id,
                    scheduled_at=call_request.scheduled_at,
                    priority=priority,
                    max_retries=call_request.max_retries
                )
                
                job_id = await queue_manager.enqueue_call(call_job)
                results.append({
                    "phone_number": call_request.phone_number,
                    "call_id": job_id,
                    "status": "queued"
                })
                
            except Exception as e:
                logger.error(f"❌ Failed to queue call {i+1}: {e}")
                results.append({
                    "phone_number": call_request.phone_number,
                    "call_id": None,
                    "status": "failed",
                    "error": str(e)
                })
        
        successful = len([r for r in results if r["status"] == "queued"])
        
        logger.info(f"✅ Bulk queue completed: {successful}/{len(request.calls)} calls queued")
        
        return {
            "success": True,
            "message": f"Queued {successful} out of {len(request.calls)} calls",
            "batch_id": batch_id,
            "total_calls": len(request.calls),
            "successful": successful,
            "failed": len(request.calls) - successful,
            "results": results
        }
        
    except Exception as e:
        logger.error(f"❌ Bulk queue failed: {e}")
        raise HTTPException(status_code=500, detail=f"Bulk queue failed: {str(e)}")

@app.get("/api/calls/{call_id}/status")
async def get_call_status(call_id: str):
    """Get status of a specific call"""
    try:
        if not queue_manager:
            raise HTTPException(status_code=503, detail="Queue manager not initialized")
        
        # Get job data from Redis
        job_key = f"call_job:{call_id}"
        job_data = await queue_manager.redis_client.hget(job_key, "data")
        
        if not job_data:
            raise HTTPException(status_code=404, detail="Call not found")
        
        import json
        job_dict = json.loads(job_data)
        
        return {
            "call_id": call_id,
            "status": job_dict.get("status"),
            "phone_number": job_dict.get("phone_number"),
            "campaign_id": job_dict.get("campaign_id"),
            "created_at": job_dict.get("created_at"),
            "started_at": job_dict.get("started_at"),
            "completed_at": job_dict.get("completed_at"),
            "retry_count": job_dict.get("retry_count", 0),
            "max_retries": job_dict.get("max_retries", 3),
            "error": job_dict.get("error"),
            "result": job_dict.get("result")
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to get call status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get call status: {str(e)}")

@app.delete("/api/calls/{call_id}")
async def cancel_call(call_id: str):
    """Cancel a queued call"""
    try:
        if not queue_manager:
            raise HTTPException(status_code=503, detail="Queue manager not initialized")
        
        # Remove from queues
        removed_from_main = await queue_manager.redis_client.zrem("call_queue", call_id)
        removed_from_scheduled = await queue_manager.redis_client.zrem("scheduled_calls", call_id)
        
        if removed_from_main or removed_from_scheduled:
            # Update job status
            job_key = f"call_job:{call_id}"
            await queue_manager.redis_client.hset(job_key, "status", CallStatus.CANCELLED.value)
            
            logger.info(f"✅ Call {call_id} cancelled")
            return {"success": True, "message": "Call cancelled successfully"}
        else:
            raise HTTPException(status_code=404, detail="Call not found or already processed")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to cancel call: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to cancel call: {str(e)}")

@app.get("/api/queue/status", response_model=Dict[str, Any])
async def get_queue_status():
    """Get current queue status and metrics"""
    try:
        if not queue_manager:
            raise HTTPException(status_code=503, detail="Queue manager not initialized")
        
        status = await queue_manager.get_queue_status()
        
        # Add additional metrics
        current_time = datetime.utcnow()
        today_start = current_time.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Count today's completed/failed calls (simplified - in production use proper time-based queries)
        status.update({
            "processing_count": 0,  # This would need tracking of active workers
            "completed_today": 0,   # This would need time-based Redis queries
            "failed_today": 0,      # This would need time-based Redis queries
            "service_status": "healthy",
            "last_updated": current_time.isoformat()
        })
        
        return status
        
    except Exception as e:
        logger.error(f"❌ Failed to get queue status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get queue status: {str(e)}")

@app.get("/api/campaigns/{campaign_id}/calls")
async def get_campaign_calls(campaign_id: str, status: Optional[str] = None):
    """Get all calls for a specific campaign"""
    try:
        if not queue_manager:
            raise HTTPException(status_code=503, detail="Queue manager not initialized")
        
        # In a production system, you'd want to index calls by campaign_id
        # For now, we'll scan all jobs (not efficient for large datasets)
        
        # Get all job keys
        job_keys = await queue_manager.redis_client.keys("call_job:*")
        campaign_calls = []
        
        for job_key in job_keys:
            job_data = await queue_manager.redis_client.hget(job_key, "data")
            if job_data:
                import json
                job_dict = json.loads(job_data)
                
                if job_dict.get("campaign_id") == campaign_id:
                    if not status or job_dict.get("status") == status:
                        campaign_calls.append({
                            "call_id": job_dict.get("id"),
                            "phone_number": job_dict.get("phone_number"),
                            "status": job_dict.get("status"),
                            "created_at": job_dict.get("created_at"),
                            "completed_at": job_dict.get("completed_at"),
                            "retry_count": job_dict.get("retry_count", 0)
                        })
        
        return {
            "campaign_id": campaign_id,
            "total_calls": len(campaign_calls),
            "status_filter": status,
            "calls": campaign_calls
        }
        
    except Exception as e:
        logger.error(f"❌ Failed to get campaign calls: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get campaign calls: {str(e)}")

# ==================== WEBHOOK ENDPOINTS ====================

@app.post("/api/calls/results")
async def receive_call_results(request: Request):
    """
    Receive call results from agent server and forward to backend
    This completes the agent -> queue -> backend flow
    """
    try:
        data = await request.json()
        call_id = data.get("call_id") or data.get("custom_call_id")
        
        logger.info(f"📥 Received call completion from agent for {call_id}")
        logger.info(f"   Status: {data.get('call_outcome', 'unknown')}")
        logger.info(f"   Duration: {data.get('duration_seconds', 0)}s")
        logger.info(f"   Transcript entries: {len(data.get('transcript', []))}")
        logger.info(f"   Recording: {data.get('public_recording_url', 'No recording')}")
        
        # 🚀 DISABLED: Backend notification now handled DIRECTLY by bot.py
        # backend_url = os.getenv("BACKEND_API_URL", "http://localhost:3000")
        # notify_url = f"{backend_url}/api/calls/external-updates"
        
        logger.info(f"📤 QUEUE API: Backend notification skipped - bot.py handles this directly now")
        logger.info(f"📤 QUEUE API: Call data received but NOT forwarded to backend (avoiding duplicates)")
        
        # Just update call job status in Redis (no backend forwarding)
        if queue_manager:
            import json
            job_key = f"call_job:{call_id}"
            await queue_manager.redis_client.hset(
                job_key, 
                "status", 
                "completed" if data.get("call_outcome") not in ["missed", "failed", "error"] else "failed"
            )
            await queue_manager.redis_client.hset(job_key, "completed_at", datetime.utcnow().isoformat())
            await queue_manager.redis_client.hset(job_key, "result", json.dumps(data))
            logger.info(f"✅ QUEUE API: Updated Redis status for call {call_id} (no backend forwarding)")
        
        return {"success": True, "message": "Call data received and stored (backend notified directly by bot)"}
        
    except Exception as e:
        logger.error(f"❌ Failed to process call results: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to process results: {str(e)}")

# ==================== UTILITY ENDPOINTS ====================

@app.post("/api/queue/clear")
async def clear_queue(queue_type: str = "all"):
    """Clear queue (for testing/maintenance)"""
    try:
        if not queue_manager:
            raise HTTPException(status_code=503, detail="Queue manager not initialized")
        
        if queue_type in ["all", "main"]:
            await queue_manager.redis_client.delete("call_queue")
        
        if queue_type in ["all", "scheduled"]:
            await queue_manager.redis_client.delete("scheduled_calls")
        
        logger.info(f"✅ Queue cleared: {queue_type}")
        return {"success": True, "message": f"Queue cleared: {queue_type}"}
        
    except Exception as e:
        logger.error(f"❌ Failed to clear queue: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to clear queue: {str(e)}")

@app.get("/api/health")
async def health_check():
    """Comprehensive health check"""
    try:
        health_status = {
            "service": "healthy",
            "redis": "unknown",
            "queue_manager": "unknown",
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Check Redis connection
        if queue_manager and queue_manager.redis_client:
            try:
                await queue_manager.redis_client.ping()
                health_status["redis"] = "healthy"
            except:
                health_status["redis"] = "unhealthy"
        
        # Check queue manager
        if queue_manager:
            health_status["queue_manager"] = "healthy"
        
        # Overall health
        if all(status == "healthy" for key, status in health_status.items() if key != "timestamp"):
            health_status["overall"] = "healthy"
        else:
            health_status["overall"] = "degraded"
        
        return health_status
        
    except Exception as e:
        logger.error(f"❌ Health check failed: {e}")
        return {
            "overall": "unhealthy",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }

# ==================== MAIN ====================

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    host = os.getenv("HOST", "0.0.0.0")
    
    logger.info(f"🚀 Starting Queue API Service on {host}:{port}")
    
    uvicorn.run(
        "queue_api_service:app",
        host=host,
        port=port,
        reload=os.getenv("ENVIRONMENT") == "development",
        log_level="info"
    ) 