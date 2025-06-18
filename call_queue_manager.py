#!/usr/bin/env python3
"""
Call Queue Manager - Replaces Temporal for Call Execution
Handles call scheduling, queuing, rate limiting, and execution
"""

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
from enum import Enum
import redis.asyncio as redis
import aiohttp
from contextlib import asynccontextmanager

# Import our local Plivo integration
from plivo_integration import initiate_call, wait_for_completion, check_call_status
import os

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Custom JSON encoder for Enum types
class EnumJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Enum):
            return obj.value
        return super().default(obj)

class CallStatus(Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRY = "retry"
    CANCELLED = "cancelled"

class CallPriority(Enum):
    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4

@dataclass
class CallJob:
    """Represents a call job in the queue"""
    id: str
    phone_number: str
    campaign_id: str
    call_config: Dict[str, Any]
    custom_call_id: Optional[str] = None
    scheduled_at: Optional[str] = None
    priority: CallPriority = CallPriority.NORMAL
    max_retries: int = 3
    retry_count: int = 0
    status: CallStatus = CallStatus.QUEUED
    created_at: str = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None
    result: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow().isoformat()

def serialize_call_job(call_job: CallJob) -> str:
    """Serialize CallJob to JSON string with proper enum handling"""
    job_dict = asdict(call_job)
    # Convert enums to their values
    job_dict['priority'] = call_job.priority.value
    job_dict['status'] = call_job.status.value
    return json.dumps(job_dict)

class CallQueueManager:
    """
    Redis-based queue manager for handling voice calls
    Replaces Temporal workflows with simpler queue-based approach
    """
    
    def __init__(self, redis_url: str = None):
        if redis_url is None:
            redis_url = os.getenv("REDIS_URL", "redis://10.206.109.83:6379")
        self.redis_url = redis_url
        self.redis_client = None
        self.max_concurrent_calls = 100  # Configurable
        self.rate_limit_per_second = 10  # Max calls per second
        self.running = False
        
    async def initialize(self):
        """Initialize Redis connection"""
        self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
        logger.info("✅ Call Queue Manager initialized")
        
    async def close(self):
        """Clean shutdown"""
        self.running = False
        if self.redis_client:
            await self.redis_client.aclose()  # Use aclose() instead of deprecated close()
        logger.info("🔒 Call Queue Manager closed")

    # ==================== QUEUE OPERATIONS ====================
    
    async def enqueue_call(self, call_job: CallJob) -> str:
        """Add a call to the queue with duplicate prevention"""
        try:
            # CRITICAL DUPLICATE PREVENTION: Since we now use backend call_id as primary ID,
            # check if this exact call_id already exists in queue
            existing_call = await self._check_existing_call(call_job.id)
            if existing_call:
                logger.warning(f"⚠️ DUPLICATE PREVENTION: Call {call_job.id} already exists in queue - skipping duplicate")
                return existing_call  # Return existing job ID
            
            # Store job data with backend call_id as primary key
            job_key = f"call_job:{call_job.id}"
            await self.redis_client.hset(job_key, mapping={
                "data": serialize_call_job(call_job),
                "status": call_job.status.value,
                "priority": call_job.priority.value,
                "created_at": call_job.created_at,
                "backend_call_id": call_job.id,  # Primary ID is backend call_id
                "phone_number": call_job.phone_number,
                "campaign_id": call_job.campaign_id
            })
            
            # Add to priority queue (sorted set by priority and timestamp)
            priority_score = call_job.priority.value * 1000000 + int(time.time())
            
            if call_job.scheduled_at:
                # Scheduled calls go to scheduled queue
                scheduled_timestamp = datetime.fromisoformat(call_job.scheduled_at.replace('Z', '+00:00')).timestamp()
                await self.redis_client.zadd("scheduled_calls", {call_job.id: scheduled_timestamp})
                logger.info(f"📅 Call {call_job.id} scheduled for {call_job.scheduled_at}")
            else:
                # Immediate calls go to main queue
                await self.redis_client.zadd("call_queue", {call_job.id: priority_score})
                logger.info(f"⚡ Call {call_job.id} queued immediately")
            
            # Update metrics
            await self._update_queue_metrics()
            
            return call_job.id
            
        except Exception as e:
            logger.error(f"❌ Failed to enqueue call {call_job.id}: {e}")
            raise
    
    async def _check_existing_call(self, call_id: str) -> Optional[str]:
        """Check if a call_id already exists in the queue system"""
        try:
            # Check if job exists and is not completed
            job_key = f"call_job:{call_id}"
            job_status = await self.redis_client.hget(job_key, "status")
            if job_status and job_status not in ["completed", "failed", "cancelled"]:
                return call_id
            return None
        except Exception as e:
            logger.error(f"❌ Error checking existing call {call_id}: {e}")
            return None
    
    async def dequeue_call(self) -> Optional[CallJob]:
        """Get the next call from the queue"""
        try:
            # First, move any scheduled calls that are ready
            await self._move_ready_scheduled_calls()
            
            # Get highest priority call
            result = await self.redis_client.zpopmax("call_queue", 1)
            
            if not result:
                return None
                
            call_id, _ = result[0]
            
            # Get job data
            job_key = f"call_job:{call_id}"
            job_data = await self.redis_client.hget(job_key, "data")
            
            if not job_data:
                logger.warning(f"⚠️ Job data not found for {call_id}")
                return None
                
            # Parse job data
            job_dict = json.loads(job_data)
            # Convert enum values back to enums
            if 'priority' in job_dict:
                job_dict['priority'] = CallPriority(job_dict['priority'])
            if 'status' in job_dict:
                job_dict['status'] = CallStatus(job_dict['status'])
            call_job = CallJob(**job_dict)
            
            # Update status to processing
            call_job.status = CallStatus.PROCESSING
            call_job.started_at = datetime.utcnow().isoformat()
            
            await self._update_job_status(call_job)
            
            return call_job
            
        except Exception as e:
            logger.error(f"❌ Failed to dequeue call: {e}")
            return None
    
    async def _move_ready_scheduled_calls(self):
        """Move scheduled calls that are ready to execute to main queue"""
        try:
            current_time = time.time()
            
            # Get calls that are ready (score <= current_time)
            ready_calls = await self.redis_client.zrangebyscore(
                "scheduled_calls", 0, current_time, withscores=True
            )
            
            for call_id, scheduled_time in ready_calls:
                # Remove from scheduled queue
                await self.redis_client.zrem("scheduled_calls", call_id)
                
                # Add to main queue with normal priority
                priority_score = CallPriority.NORMAL.value * 1000000 + int(time.time())
                await self.redis_client.zadd("call_queue", {call_id: priority_score})
                
                logger.info(f"📅➡️⚡ Moved scheduled call {call_id} to main queue")
                
        except Exception as e:
            logger.error(f"❌ Failed to move scheduled calls: {e}")

    # ==================== CALL EXECUTION ====================
    
    async def execute_call(self, call_job: CallJob) -> Dict[str, Any]:
        """Execute a call job using PRODUCTION CLOUD RUN FIX - Handles local vs Cloud Run differences"""
        try:
            logger.info(f"🏭 PRODUCTION: Executing call {call_job.id} with environment-aware tracking")
            logger.info(f"   📋 Phone: {call_job.phone_number}")
            logger.info(f"   📋 Campaign: {call_job.campaign_id}")
            logger.info(f"   📋 Variables: {len(call_job.call_config.get('variables', {}))}")
            
            # Try to import production manager, fallback if not available
            try:
                import sys
                import os
                sys.path.append(os.path.dirname(__file__))
                
                # Import the production Cloud Run manager
                exec(open(os.path.join(os.path.dirname(__file__), 'production-cloudrun-fix.py')).read())
                production_manager = ProductionCloudRunManager()
            except Exception as import_error:
                logger.warning(f"⚠️ Could not import production manager: {import_error}")
                # Fallback to enhanced original method immediately
                raise Exception("Production manager import failed")
            
            # Enhanced call_config
            enhanced_config = {
                **call_job.call_config,
                "backend_call_id": call_job.id,
                "queue_job_id": call_job.id,
                "phone_number": call_job.phone_number,
                "campaign_id": call_job.campaign_id,
                "variables": call_job.call_config.get('variables', {})
            }
            
            # PRODUCTION: Environment-aware call initiation
            logger.info(f"🏭 PRODUCTION: Using environment-aware call initiation for {call_job.id}")
            
            initiation_result = await production_manager.initiate_call_production(
                phone_number=call_job.phone_number,
                campaign_id=call_job.campaign_id,
                config=enhanced_config,
                call_id=call_job.id
            )
            
            if not initiation_result["success"]:
                error_msg = initiation_result.get("error", "Production call initiation failed")
                logger.error(f"❌ PRODUCTION: Call initiation failed: {error_msg}")
                raise Exception(error_msg)
            
            plivo_uuid = initiation_result["plivo_uuid"]
            environment = initiation_result.get("environment", "unknown")
            agent_notified = initiation_result.get("agent_notified", False)
            
            logger.info(f"✅ PRODUCTION: Call initiated in {environment} environment")
            logger.info(f"   Plivo UUID: {plivo_uuid}")
            logger.info(f"   Agent notified: {agent_notified}")
            
            # Store Plivo UUID for reference
            await self.redis_client.hset(f"call_job:{call_job.id}", "plivo_uuid", plivo_uuid)
            await self.redis_client.hset(f"call_job:{call_job.id}", "environment", environment)
            
            # PRODUCTION: Environment-aware call tracking
            logger.info(f"🏭 PRODUCTION: Starting environment-aware tracking for {call_job.id}")
            
            completion_result = await production_manager.track_call_production(
                call_id=call_job.id,
                plivo_uuid=plivo_uuid,
                timeout_minutes=60  # 🎯 TRACK FOR 1 HOUR!
            )
            
            # Add campaign context to completion result
            completion_result.update({
                "phone_number": call_job.phone_number,
                "campaign_id": call_job.campaign_id,
                "variables": call_job.call_config.get('variables', {})
            })
            
            logger.info(f"✅ PRODUCTION: Call {call_job.id} tracking completed")
            logger.info(f"   📋 Environment: {completion_result.get('environment', 'unknown')}")
            logger.info(f"   📋 Outcome: {completion_result.get('call_outcome', 'unknown')}")
            logger.info(f"   📋 Duration: {completion_result.get('duration', 0)}s")
            logger.info(f"   📋 Method: {completion_result.get('method', 'unknown')}")
            logger.info(f"   📋 Recording: {completion_result.get('public_recording_url', 'No recording')}")
            logger.info(f"   📋 Transcript: {len(completion_result.get('transcript', []))} entries")
            
            # PRODUCTION: Prepare comprehensive result with proper data source marking
            final_result = {
                "call_id": call_job.id,
                "queue_job_id": call_job.id,
                "phone_number": call_job.phone_number,
                "campaign_id": call_job.campaign_id,
                "workflow_id": f"production-{call_job.id}",
                
                # Core status and outcome
                "status": completion_result.get("status", "completed"),
                "call_outcome": completion_result.get("call_outcome", "completed"),
                
                # Timing information
                "duration_seconds": completion_result.get("duration_seconds", 0),
                "start_time": call_job.started_at,
                "end_time": completion_result.get("end_time", datetime.utcnow().isoformat()),
                "processing_timestamp": datetime.utcnow().isoformat(),
                
                # Conversation data
                "transcript": completion_result.get("transcript", []),
                "main_transcript": completion_result.get("transcript", []),
                "agent_transcript": completion_result.get("transcript", []),
                
                # Recording information
                "recording_file": completion_result.get("recording_file"),
                "public_recording_url": completion_result.get("public_recording_url"),
                "recording_status": completion_result.get("recording_status", "unknown"),
                
                # Variables and configuration
                "variables": call_job.call_config.get('variables', {}),
                "agent_name": call_job.call_config.get('flow_name', 'unknown'),
                "flow_name": call_job.call_config.get('flow_name', 'unknown'),
                
                # PRODUCTION: Environment and tracking data
                "environment_data": {
                    "environment": completion_result.get("environment", "unknown"),
                    "method": completion_result.get("method", "production_tracking"),
                    "plivo_uuid": completion_result.get("plivo_uuid"),
                    "plivo_status": completion_result.get("plivo_status"),
                    "hangup_cause": completion_result.get("hangup_cause"),
                    "agent_notified": agent_notified
                },
                
                # PRODUCTION: Plivo API data (primary source)
                "plivo_data": {
                    "plivo_uuid": completion_result.get("plivo_uuid"),
                    "plivo_status": completion_result.get("plivo_status"),
                    "hangup_cause": completion_result.get("hangup_cause"),
                    "answer_time": completion_result.get("answer_time"),
                    "method": "production_plivo_api"
                },
                
                # Agent response data (for compatibility)
                "agent_response": {
                    "call_id": call_job.id,
                    "status": completion_result.get("call_outcome", "completed"),
                    "duration": completion_result.get("duration_seconds", 0),
                    "transcript": completion_result.get("transcript", []),
                    "workflow_id": f"production-{call_job.id}",
                    "recording_file": completion_result.get("recording_file"),
                    "recording_status": completion_result.get("recording_status", "unknown"),
                    "public_recording_url": completion_result.get("public_recording_url"),
                    "agent_response": {
                        "transcript": completion_result.get("transcript", []),
                        "call_outcome": completion_result.get("call_outcome", "completed"),
                        "workflow_id": f"production-{call_job.id}",
                        "error": completion_result.get("error")
                    }
                },
                
                # Metadata with proper data source identification
                "success": completion_result.get("status") != "failed",
                "next_action": completion_result.get("next_action", "none"),
                "data_source": "production_cloudrun_manager",  # This identifies the fix
                "warning": completion_result.get("warning"),
                
                # Error information if failed
                "error": completion_result.get("error") if completion_result.get("status") == "failed" else None
            }
            
            # Store result in Redis
            await self._store_completion_result(call_job.id, final_result)
            
            logger.info(f"🎉 PRODUCTION: Call {call_job.id} processing completed successfully")
            logger.info(f"   Data source: {final_result['data_source']}")
            logger.info(f"   Environment: {final_result['environment_data']['environment']}")
            
            return final_result
            
        except Exception as e:
            logger.error(f"❌ PRODUCTION: Call execution failed for {call_job.id}: {e}")
            
            # PRODUCTION FALLBACK: Try original method with better error handling
            logger.info(f"🔄 PRODUCTION: Falling back to enhanced original method for {call_job.id}")
            
            try:
                # Enhanced original method with better timeouts
                enhanced_config = {
                    **call_job.call_config,
                    "backend_call_id": call_job.id,
                    "queue_job_id": call_job.id,
                    "phone_number": call_job.phone_number,
                    "campaign_id": call_job.campaign_id
                }
                
                # Import with production settings
                import os
                os.environ["CLOUD_RUN_OPTIMIZED"] = "true"
                os.environ["STATUS_CHECK_INTERVAL"] = "20"
                os.environ["INITIAL_STATUS_DELAY"] = "30"
                os.environ["REQUEST_TIMEOUT"] = "45"
                os.environ["MAX_STATUS_RETRIES"] = "5"
                
                from plivo_integration import initiate_call, wait_for_completion
                
                result = await initiate_call(
                    call_job.phone_number,
                    call_job.campaign_id,
                    enhanced_config,
                    call_job.id
                )
                
                if result.get("status") == "failed":
                    raise Exception(result.get("error", "Unknown error in fallback"))
                
                plivo_uuid = result.get("plivo_call_uuid")
                if plivo_uuid:
                    await self.redis_client.hset(f"call_job:{call_job.id}", "plivo_uuid", plivo_uuid)
                
                completion_result = await wait_for_completion(call_job.id, timeout_minutes=60)  # 🎯 SAME 1-HOUR TIMEOUT FOR FALLBACK
                
                logger.info(f"✅ PRODUCTION FALLBACK: Call {call_job.id} completed via enhanced original method")
                
                # Production fallback result
                fallback_result = {
                    "call_id": call_job.id,
                    "queue_job_id": call_job.id,
                    "phone_number": call_job.phone_number,
                    "campaign_id": call_job.campaign_id,
                    "workflow_id": f"fallback-{call_job.id}",
                    "status": completion_result.get("status", "completed"),
                    "call_outcome": completion_result.get("call_outcome", "completed"),
                    "duration_seconds": completion_result.get("duration_seconds", 0),
                    "transcript": completion_result.get("transcript", []),
                    "recording_file": completion_result.get("recording_file"),
                    "public_recording_url": completion_result.get("public_recording_url"),
                    "variables": call_job.call_config.get('variables', {}),
                    "data_source": "production_fallback_method",
                    "environment_data": {
                        "environment": "cloud_run_fallback",
                        "method": "enhanced_original_with_timeouts",
                        "primary_method_error": str(e)
                    },
                    "success": completion_result.get("status") != "failed",
                    "start_time": call_job.started_at,
                    "end_time": completion_result.get("end_time", datetime.utcnow().isoformat()),
                    "processing_timestamp": datetime.utcnow().isoformat()
                }
                
                await self._store_completion_result(call_job.id, fallback_result)
                
                return fallback_result
                
            except Exception as fallback_error:
                logger.error(f"❌ PRODUCTION: Both production and fallback methods failed for {call_job.id}")
                logger.error(f"   Primary error: {str(e)}")
                logger.error(f"   Fallback error: {str(fallback_error)}")
                
                # Final comprehensive error result
                error_result = {
                    "call_id": call_job.id,
                    "queue_job_id": call_job.id,
                    "phone_number": call_job.phone_number,
                    "campaign_id": call_job.campaign_id,
                    "status": "failed",
                    "call_outcome": "system_failure",
                    "error": f"Production method failed: {str(e)}. Fallback failed: {str(fallback_error)}",
                    "workflow_id": f"failed-{call_job.id}",
                    "start_time": call_job.started_at,
                    "end_time": datetime.utcnow().isoformat(),
                    "variables": call_job.call_config.get('variables', {}),
                    "processing_timestamp": datetime.utcnow().isoformat(),
                    "data_source": "production_system_failure",
                    "environment_data": {
                        "environment": "unknown",
                        "primary_error": str(e),
                        "fallback_error": str(fallback_error),
                        "method": "complete_failure"
                    },
                    "success": False,
                    "next_action": "retry",
                    "duration_seconds": 0,
                    "transcript": [],
                    "recording_file": None,
                    "public_recording_url": None
                }
                
                await self._store_completion_result(call_job.id, error_result)
                
                return error_result
    
    async def _store_completion_result(self, call_id: str, result: Dict[str, Any]):
        """Store completion result in Redis for callback systems and debugging"""
        try:
            job_key = f"call_job:{call_id}"
            
            # Store the result
            await self.redis_client.hset(job_key, "result", json.dumps(result, cls=EnumJSONEncoder))
            await self.redis_client.hset(job_key, "completed_at", datetime.utcnow().isoformat())
            
            # Set expiration for cleanup (keep for 24 hours)
            await self.redis_client.expire(job_key, 86400)
            
            logger.info(f"📋 QUEUE: Stored completion result for call {call_id}")
            
        except Exception as e:
            logger.error(f"❌ QUEUE: Failed to store completion result for {call_id}: {e}")
    
    async def _store_call_result(self, call_job: CallJob, result: Dict[str, Any]):
        """Store call result and notify backend"""
        try:
            # Update job with result
            call_job.status = CallStatus.COMPLETED if result.get("status") != "failed" else CallStatus.FAILED
            call_job.completed_at = datetime.utcnow().isoformat()
            call_job.result = result
            
            await self._update_job_status(call_job)
            
            # 🚀 DISABLED: Backend notification now handled directly by bot.py
            # await self._notify_backend(call_job, result)
            logger.info(f"📤 BACKEND NOTIFICATION: Skipped - bot handles this directly now")
            
        except Exception as e:
            logger.error(f"❌ Failed to store call result for {call_job.id}: {e}")
    
    async def _notify_backend(self, call_job: CallJob, result: Dict[str, Any]):
        """Notify backend API about call completion with comprehensive data"""
        try:
            backend_url = os.getenv("BACKEND_API_URL", "http://localhost:3000")
            notify_url = f"{backend_url}/api/calls/external-updates"
            
            # Use backend call_id for tracking (primary ID)
            tracking_call_id = call_job.id
            
            logger.info(f"📤 QUEUE: Notifying backend about call completion: {tracking_call_id}")
            
            # Determine final status based on result
            final_status = "completed"
            if result.get("status") == "failed" or result.get("call_outcome") == "failed":
                final_status = "failed"
            elif result.get("status") == "missed" or result.get("call_outcome") == "no_answer":
                final_status = "missed"
            
            # CRITICAL FIX: Extract recording URL from multiple possible sources
            recording_url = (
                result.get("public_recording_url") or 
                result.get("recording_url") or 
                result.get("recordingUrl") or
                result.get("complete_call_result", {}).get("public_recording_url") or
                result.get("complete_call_result", {}).get("recording_url") or
                result.get("complete_call_result", {}).get("recordingUrl") or
                result.get("agent_response", {}).get("public_recording_url") or
                result.get("agent_response", {}).get("recording_url") or
                result.get("agent_response", {}).get("recordingUrl")
            )
            
            recording_file = (
                result.get("recording_file") or
                result.get("complete_call_result", {}).get("recording_file") or
                result.get("agent_response", {}).get("recording_file")
            )
            
            recording_status = (
                result.get("recording_status") or
                result.get("complete_call_result", {}).get("recording_status") or
                "unknown"
            )
            
            # Log recording extraction for debugging
            logger.info(f"🎵 QUEUE: Recording extraction results:")
            logger.info(f"   - recording_url: {recording_url}")
            logger.info(f"   - recording_file: {recording_file}")
            logger.info(f"   - recording_status: {recording_status}")
            
            # Format the notification payload to match backend expectations
            notification_payload = {
                "call_id": tracking_call_id,  # Backend call_id (primary ID)
                "campaign_id": call_job.campaign_id,
                "phone_number": call_job.phone_number,
                "status": final_status,  # completed/failed/missed
                "call_outcome": result.get("call_outcome", final_status),
                "duration_seconds": result.get("duration_seconds", result.get("duration", 0)),
                "start_time": result.get("start_time", call_job.started_at),
                "end_time": result.get("end_time"),
                "workflow_id": result.get("workflow_id", f"queue-{call_job.id}"),
                
                # CRITICAL FIX: Recording information with ALL possible field names for backend compatibility
                "recording_file": recording_file,
                "public_recording_url": recording_url,
                "recording_url": recording_url,        # Backend primary lookup field
                "recordingUrl": recording_url,         # Backend secondary lookup field
                "recording_status": recording_status,
                
                # Conversation data for AI processing
                "transcript": result.get("transcript", []),
                "conversation_summary": result.get("transcript", []),  # For backward compatibility
                
                # Variables and agent info
                "variables": result.get("variables", {}),
                "agent_name": result.get("agent_name", "unknown"),
                
                # Additional metadata
                "processing_timestamp": result.get("processing_timestamp", datetime.utcnow().isoformat()),
                "data_source": "call_queue_system",
                "queue_job_id": call_job.id,
                
                # ENHANCED: Include complete call result with recording data
                "complete_call_result": {
                    **result.get("complete_call_result", {}),
                    # Ensure recording fields are present in complete_call_result
                    "recording_file": recording_file,
                    "public_recording_url": recording_url,
                    "recording_url": recording_url,
                    "recordingUrl": recording_url,
                    "recording_status": recording_status
                },
                
                # Agent response data (matching expected format)
                "agent_data": result.get("agent_data", {}),
                
                # Error information if failed
                "error": result.get("error") if final_status == "failed" else None,
                
                # CRITICAL: Status progression tracking
                "status_progression": {
                    "queued_at": call_job.created_at,
                    "started_at": call_job.started_at or result.get("start_time"),
                    "completed_at": result.get("end_time", datetime.utcnow().isoformat()),
                    "queue_job_id": call_job.id,
                    "backend_call_id": call_job.id  # Same as primary ID
                }
            }
            
            logger.info(f"📋 QUEUE: Notification payload keys: {list(notification_payload.keys())}")
            logger.info(f"📋 QUEUE: Call outcome: {notification_payload['call_outcome']}")
            logger.info(f"📋 QUEUE: Final status: {final_status}")
            
            # CRITICAL: Log all recording fields being sent to backend
            if recording_url:
                logger.info(f"🎵 QUEUE: ✅ Recording URL found and will be sent to backend:")
                logger.info(f"   - public_recording_url: {recording_url}")
                logger.info(f"   - recording_url: {recording_url}")
                logger.info(f"   - recordingUrl: {recording_url}")
                logger.info(f"   - recording_file: {recording_file}")
                logger.info(f"   - recording_status: {recording_status}")
            else:
                logger.warning(f"🎵 QUEUE: ⚠️ NO recording URL found in call result - backend will not receive recording")
                logger.warning(f"   Available result keys: {list(result.keys())}")
                # Log the complete result structure for debugging
                logger.warning(f"   Complete result structure: {json.dumps(result, indent=2, default=str)}")
            
            # Send notification to backend (FIXED: Backend expects array format)
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120)) as session:  # Increased to 2 minutes for long call processing
                async with session.post(notify_url, json=[notification_payload]) as response:  # Backend expects array
                    if response.status in [200, 201]:
                        response_data = await response.json()
                        logger.info(f"✅ QUEUE: Backend notified successfully for call {tracking_call_id}")
                        logger.info(f"📋 QUEUE: Backend response: {response_data.get('message', 'Success')}")
                        if recording_url:
                            logger.info(f"✅ QUEUE: Recording URL successfully forwarded to backend: {recording_url}")
                    else:
                        error_text = await response.text()
                        logger.warning(f"⚠️ QUEUE: Backend notification failed ({response.status}): {error_text}")
                        
        except Exception as e:
            logger.error(f"❌ QUEUE: Failed to notify backend about call {call_job.id}: {e}")
            # Don't raise - this shouldn't fail the call processing
    


    # ==================== RETRY LOGIC ====================
    
    async def handle_failed_call(self, call_job: CallJob, error: str):
        """Handle failed calls with retry logic"""
        try:
            call_job.retry_count += 1
            call_job.error = error
            
            if call_job.retry_count < call_job.max_retries:
                # Calculate retry delay (exponential backoff)
                delay_minutes = min(2 ** call_job.retry_count, 30)  # Max 30 minutes
                retry_time = datetime.utcnow() + timedelta(minutes=delay_minutes)
                
                call_job.status = CallStatus.RETRY
                call_job.scheduled_at = retry_time.isoformat()
                
                # Re-queue for retry
                await self.enqueue_call(call_job)
                
                logger.info(f"🔄 Call {call_job.id} scheduled for retry {call_job.retry_count}/{call_job.max_retries} in {delay_minutes} minutes")
            else:
                # Max retries reached
                call_job.status = CallStatus.FAILED
                call_job.completed_at = datetime.utcnow().isoformat()
                
                await self._update_job_status(call_job)
                # 🚀 DISABLED: Backend notification for failures now handled by bot.py
                # await self._notify_backend(call_job, {"status": "failed", "error": error})
                logger.info(f"📤 BACKEND NOTIFICATION: Failure notification skipped - bot handles this directly")
                
                logger.error(f"❌ Call {call_job.id} failed permanently after {call_job.retry_count} retries")
                
        except Exception as e:
            logger.error(f"❌ Failed to handle retry for {call_job.id}: {e}")

    # ==================== WORKER MANAGEMENT ====================
    
    async def start_workers(self, num_workers: int = 10):
        """Start worker processes and monitoring tasks"""
        logger.info(f"👷 Starting {num_workers} queue workers...")
        
        # CRITICAL: Set running flag BEFORE starting workers
        self.running = True
        
        # Start workers
        for i in range(num_workers):
            worker_id = f"worker-{i+1}"
            asyncio.create_task(self._worker_loop(worker_id))
        
        # Start monitoring tasks
        asyncio.create_task(self._metrics_loop())
        asyncio.create_task(self._enforce_rate_limit())
        
        # CRITICAL: Start stuck call detection task
        asyncio.create_task(self._stuck_call_detection_loop())
        
        logger.info(f"✅ Started {num_workers} workers with monitoring and stuck call detection")

    async def _worker_loop(self, worker_id: str):
        """Main worker loop for processing calls"""
        logger.info(f"🔄 Worker {worker_id} started")
        
        while self.running:
            try:
                # Check rate limiting
                await self._enforce_rate_limit()
                
                # Get next call from queue
                call_job = await self.dequeue_call()
                
                if not call_job:
                    # No calls to process, wait briefly
                    await asyncio.sleep(5)
                    continue
                
                logger.info(f"👷 Worker {worker_id} processing call {call_job.id}")
                
                # Execute the call (backend already knows it's IN_PROGRESS)
                result = await self.execute_call(call_job)
                
                # Update job status based on result
                if result.get("status") == "failed":
                    call_job.status = CallStatus.FAILED
                    call_job.error = result.get("error")
                    await self.handle_failed_call(call_job, result.get("error", "Unknown error"))
                else:
                    call_job.status = CallStatus.COMPLETED
                    call_job.result = result
                
                call_job.completed_at = datetime.utcnow().isoformat()
                await self._update_job_status(call_job)
                
                # Store call result and notify backend of FINAL completion only
                await self._store_call_result(call_job, result)
                
                logger.info(f"✅ Worker {worker_id} completed call {call_job.id}")
                
            except Exception as e:
                logger.error(f"❌ Worker {worker_id} error: {e}")
                await asyncio.sleep(10)  # Wait before retrying
        
        logger.info(f"🛑 Worker {worker_id} stopped")
    
    async def _enforce_rate_limit(self):
        """Enforce rate limiting"""
        current_time = time.time()
        window_key = f"rate_limit:{int(current_time)}"
        
        # Count calls in current second
        current_count = await self.redis_client.incr(window_key)
        await self.redis_client.expire(window_key, 2)  # Clean up after 2 seconds
        
        if current_count > self.rate_limit_per_second:
            # Rate limit exceeded, wait
            sleep_time = 1.0 - (current_time % 1.0)
            await asyncio.sleep(sleep_time)

    # ==================== MONITORING & METRICS ====================
    
    async def _metrics_loop(self):
        """Update queue metrics periodically"""
        while self.running:
            try:
                await self._update_queue_metrics()
                await asyncio.sleep(30)  # Update every 30 seconds
            except Exception as e:
                logger.error(f"❌ Metrics update error: {e}")
                await asyncio.sleep(30)
    
    async def _update_queue_metrics(self):
        """Update queue metrics in Redis"""
        try:
            # Count calls by status
            queue_size = await self.redis_client.zcard("call_queue")
            scheduled_size = await self.redis_client.zcard("scheduled_calls")
            
            # Store metrics
            metrics = {
                "queue_size": queue_size,
                "scheduled_size": scheduled_size,
                "updated_at": datetime.utcnow().isoformat()
            }
            
            await self.redis_client.hset("queue_metrics", mapping=metrics)
            
        except Exception as e:
            logger.error(f"❌ Failed to update metrics: {e}")
    
    async def _update_job_status(self, call_job: CallJob):
        """Update job status in Redis"""
        job_key = f"call_job:{call_job.id}"
        await self.redis_client.hset(job_key, mapping={
            "data": serialize_call_job(call_job),
            "status": call_job.status.value,
            "updated_at": datetime.utcnow().isoformat()
        })
    
    async def get_queue_status(self) -> Dict[str, Any]:
        """Get current queue status"""
        try:
            metrics = await self.redis_client.hgetall("queue_metrics")
            
            return {
                "queue_size": int(metrics.get("queue_size", 0)),
                "scheduled_size": int(metrics.get("scheduled_size", 0)),
                "updated_at": metrics.get("updated_at"),
                "max_concurrent_calls": self.max_concurrent_calls,
                "rate_limit_per_second": self.rate_limit_per_second
            }
        except Exception as e:
            logger.error(f"❌ Failed to get queue status: {e}")
            return {"error": str(e)}

    async def _stuck_call_detection_loop(self):
        """Background task to detect and auto-mark stuck calls as missed"""
        while True:
            try:
                await asyncio.sleep(30)  # Check every 30 seconds
                
                current_time = datetime.utcnow()
                stuck_calls = []
                
                # Get all jobs from Redis
                job_keys = await self.redis_client.keys("call_job:*")
                
                for job_key in job_keys:
                    try:
                        job_data = await self.redis_client.hget(job_key, "job")
                        if not job_data:
                            continue
                        
                        job_dict = json.loads(job_data)
                        
                        # Skip if already completed
                        if job_dict.get("status") in ["completed", "failed"]:
                            continue
                        
                        # Check if stuck in processing
                        started_at = job_dict.get("started_at")
                        if started_at:
                            start_time = datetime.fromisoformat(started_at)
                            elapsed_seconds = (current_time - start_time).total_seconds()
                            
                            # If stuck for >60 seconds (extra buffer), mark as missed
                            if elapsed_seconds > 60:
                                call_id = job_dict.get("id")
                                stuck_calls.append({
                                    "call_id": call_id,
                                    "elapsed": elapsed_seconds,
                                    "status": job_dict.get("status")
                                })
                                
                                logger.warning(f"🕒 DETECTED: Stuck call {call_id} - {elapsed_seconds:.0f}s in processing")
                                
                                # Create missed result and store it
                                missed_result = {
                                    "call_id": call_id,
                                    "status": "completed",
                                    "call_outcome": "missed",
                                    "duration": 0,
                                    "duration_seconds": 0,
                                    "transcript": [],
                                    "recording_file": None,
                                    "public_recording_url": None,
                                    "recording_status": "not_started",
                                    "end_time": current_time.isoformat(),
                                    "hangup_cause": "stuck_call_timeout",
                                    "agent_response": {"transcript": [], "call_outcome": "missed"},
                                    "next_action": "retry",
                                    "data_source": "queue_stuck_call_detection",
                                    "auto_detected": True,
                                    "detection_reason": f"Stuck in processing for {elapsed_seconds:.0f}s",
                                    "background_detection": True
                                }
                                
                                # Store the result to trigger completion
                                await self.redis_client.hset(job_key, "result", json.dumps(missed_result, cls=EnumJSONEncoder))
                                await self.redis_client.hset(job_key, "status", "completed")
                                await self.redis_client.hset(job_key, "completed_at", current_time.isoformat())
                                
                                logger.info(f"📵 AUTO-MARKED: Call {call_id} as MISSED due to timeout - result stored for worker pickup")
                    
                    except Exception as e:
                        logger.error(f"❌ Error checking stuck call {job_key}: {e}")
                        continue
                
                if stuck_calls:
                    logger.info(f"🕒 STUCK CALL DETECTION: Found {len(stuck_calls)} stuck calls, auto-marked as missed")
                
            except Exception as e:
                logger.error(f"❌ Error in stuck call detection loop: {e}")
                await asyncio.sleep(60)  # Wait longer on errors

# ==================== API FUNCTIONS ====================

async def queue_outbound_call(
    phone_number: str,
    campaign_id: str,
    call_config: Dict[str, Any] = None,
    custom_call_id: str = None,
    scheduled_at: str = None,
    priority: CallPriority = CallPriority.NORMAL
) -> str:
    """
    Queue an outbound call - replaces Temporal's trigger_outbound_call
    """
    if call_config is None:
        call_config = {
            "voice": "en-US",
            "max_duration": 1800,
            "recording_enabled": True
        }
    
    # CRITICAL FIX: Always use backend call_id as the primary ID
    if not custom_call_id:
        raise ValueError("Backend call_id (custom_call_id) is required - cannot process calls without proper tracking")
    
    # Create call job using backend call_id as primary ID
    call_job = CallJob(
        id=custom_call_id,  # Use backend call_id as primary ID
        phone_number=phone_number,
        campaign_id=campaign_id,
        call_config=call_config,
        custom_call_id=custom_call_id,  # Keep for reference  
        scheduled_at=scheduled_at,
        priority=priority
    )
    
    # Initialize queue manager (this would be a singleton in production)
    queue_manager = CallQueueManager(
        redis_url=os.getenv("REDIS_URL", "redis://localhost:6379")
    )
    await queue_manager.initialize()
    
    try:
        job_id = await queue_manager.enqueue_call(call_job)
        logger.info(f"✅ Call queued successfully: {job_id}")
        return job_id
    finally:
        await queue_manager.close()

# ==================== MAIN ENTRY POINT ====================

async def main():
    """Main entry point for the queue manager"""
    queue_manager = CallQueueManager(
        redis_url=os.getenv("REDIS_URL", "redis://localhost:6379")
    )
    
    try:
        await queue_manager.initialize()
        logger.info("🎯 Call Queue Manager ready for production!")
        
        # Start workers
        await queue_manager.start_workers(num_workers=10)
        
        # Keep running until interrupted
        logger.info("🔄 Workers running, press Ctrl+C to stop...")
        while queue_manager.running:
            await asyncio.sleep(1)
        
    except KeyboardInterrupt:
        logger.info("🛑 Shutting down...")
    finally:
        await queue_manager.close()

if __name__ == "__main__":
    asyncio.run(main()) 