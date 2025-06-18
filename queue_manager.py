#!/usr/bin/env python3
"""
Scalable Queue Management System - Temporal Replacement
Handles call scheduling, retries, rate limiting, and job management
"""

import asyncio
import json
import logging
import time
import os
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
from enum import Enum
import redis.asyncio as redis
import aiohttp
from google.cloud import tasks_v2
import uuid

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class JobStatus(Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRY = "retry"
    CANCELLED = "cancelled"

class JobPriority(Enum):
    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4

@dataclass
class CallJob:
    """Call job definition"""
    id: str
    phone_number: str
    campaign_id: str
    agent_name: str = "wishfin-test"
    variables: Dict[str, Any] = None
    scheduled_at: Optional[datetime] = None
    priority: JobPriority = JobPriority.NORMAL
    max_retries: int = 3
    retry_count: int = 0
    created_at: datetime = None
    status: JobStatus = JobStatus.PENDING
    error_message: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.variables is None:
            self.variables = {}
        if self.created_at is None:
            self.created_at = datetime.utcnow()

class ScalableQueueManager:
    """
    Redis-based queue system for handling call jobs at scale
    Supports: scheduling, retries, rate limiting, priorities, dead letter queues
    """
    
    def __init__(self, redis_url: str = "redis://localhost:6379", agent_base_url: str = "http://localhost:8765"):
        self.redis_url = redis_url
        self.agent_base_url = agent_base_url
        self.redis_client = None
        
        # Queue configuration
        self.queues = {
            "calls.high": "calls:high_priority",
            "calls.normal": "calls:normal_priority", 
            "calls.low": "calls:low_priority",
            "calls.retry": "calls:retry_queue",
            "calls.dlq": "calls:dead_letter_queue"  # Dead letter queue
        }
        
        # Rate limiting (calls per minute per priority)
        self.rate_limits = {
            JobPriority.URGENT: 100,
            JobPriority.HIGH: 50,
            JobPriority.NORMAL: 30,
            JobPriority.LOW: 10
        }
        
        # Processing status
        self.active_jobs = {}
        self.is_running = False
        
    async def connect(self):
        """Initialize Redis connection"""
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            await self.redis_client.ping()
            logger.info("✅ Connected to Redis successfully")
        except Exception as e:
            logger.error(f"❌ Failed to connect to Redis: {e}")
            raise

    async def disconnect(self):
        """Close Redis connection"""
        if self.redis_client:
            await self.redis_client.close()
            logger.info("🔌 Disconnected from Redis")

    async def enqueue_call(self, job: CallJob) -> str:
        """
        Add a call job to the appropriate queue
        """
        try:
            # Serialize job
            job_data = {
                **asdict(job),
                'created_at': job.created_at.isoformat(),
                'scheduled_at': job.scheduled_at.isoformat() if job.scheduled_at else None,
                'priority': job.priority.value,
                'status': job.status.value
            }
            
            # Determine queue based on priority and scheduling
            if job.scheduled_at and job.scheduled_at > datetime.utcnow():
                # Schedule for future execution
                delay_seconds = (job.scheduled_at - datetime.utcnow()).total_seconds()
                await self._schedule_job(job.id, job_data, delay_seconds)
                logger.info(f"📅 Scheduled call {job.id} for {job.scheduled_at}")
            else:
                # Add to immediate execution queue
                queue_name = self._get_queue_for_priority(job.priority)
                await self.redis_client.lpush(queue_name, json.dumps(job_data))
                logger.info(f"📞 Enqueued call {job.id} to {queue_name}")
            
            # Store job metadata
            await self.redis_client.setex(
                f"job:{job.id}",
                3600 * 24,  # 24 hours TTL
                json.dumps(job_data)
            )
            
            return job.id
            
        except Exception as e:
            logger.error(f"❌ Failed to enqueue call {job.id}: {e}")
            raise

    async def _schedule_job(self, job_id: str, job_data: Dict[str, Any], delay_seconds: float):
        """Schedule a job for future execution using Redis sorted sets"""
        execute_at = time.time() + delay_seconds
        await self.redis_client.zadd("scheduled_jobs", {json.dumps(job_data): execute_at})
        logger.info(f"⏰ Job {job_id} scheduled to execute in {delay_seconds} seconds")

    async def _get_queue_for_priority(self, priority: JobPriority) -> str:
        """Get queue name based on priority"""
        if priority == JobPriority.URGENT or priority == JobPriority.HIGH:
            return self.queues["calls.high"]
        elif priority == JobPriority.LOW:
            return self.queues["calls.low"]
        else:
            return self.queues["calls.normal"]

    async def start_processing(self):
        """
        Start processing jobs from queues
        Supports multiple concurrent workers
        """
        self.is_running = True
        logger.info("🚀 Starting queue processing...")
        
        # Start concurrent workers
        tasks = [
            asyncio.create_task(self._process_scheduled_jobs()),
            asyncio.create_task(self._process_queue_worker("high")),
            asyncio.create_task(self._process_queue_worker("normal")),
            asyncio.create_task(self._process_queue_worker("low")),
            asyncio.create_task(self._process_retry_worker()),
            asyncio.create_task(self._cleanup_completed_jobs()),
        ]
        
        try:
            await asyncio.gather(*tasks)
        except Exception as e:
            logger.error(f"❌ Queue processing error: {e}")
        finally:
            self.is_running = False

    async def _process_scheduled_jobs(self):
        """Move scheduled jobs to execution queues when ready"""
        while self.is_running:
            try:
                current_time = time.time()
                
                # Get jobs ready for execution
                ready_jobs = await self.redis_client.zrangebyscore(
                    "scheduled_jobs", 0, current_time, withscores=True
                )
                
                for job_data_json, score in ready_jobs:
                    try:
                        job_data = json.loads(job_data_json)
                        priority = JobPriority(job_data['priority'])
                        
                        # Move to execution queue
                        queue_name = self._get_queue_for_priority(priority)
                        await self.redis_client.lpush(queue_name, job_data_json)
                        
                        # Remove from scheduled set
                        await self.redis_client.zrem("scheduled_jobs", job_data_json)
                        
                        logger.info(f"📅➡️📞 Moved scheduled job {job_data['id']} to execution queue")
                        
                    except Exception as e:
                        logger.error(f"❌ Error processing scheduled job: {e}")
                
                await asyncio.sleep(1)  # Check every second
                
            except Exception as e:
                logger.error(f"❌ Scheduled jobs processor error: {e}")
                await asyncio.sleep(5)

    async def _process_queue_worker(self, priority: str):
        """Process jobs from a specific priority queue with rate limiting"""
        queue_name = self.queues[f"calls.{priority}"]
        
        while self.is_running:
            try:
                # Rate limiting check
                if not await self._check_rate_limit(priority):
                    await asyncio.sleep(1)
                    continue
                
                # Get job from queue (blocking with timeout)
                result = await self.redis_client.brpop(queue_name, timeout=5)
                
                if result:
                    _, job_data_json = result
                    job_data = json.loads(job_data_json)
                    
                    # Process the call
                    await self._process_call_job(job_data)
                
            except Exception as e:
                logger.error(f"❌ Queue worker {priority} error: {e}")
                await asyncio.sleep(2)

    async def _check_rate_limit(self, priority: str) -> bool:
        """Check if we can process more jobs based on rate limits"""
        try:
            # Simple rate limiting using Redis
            current_minute = int(time.time() / 60)
            key = f"rate_limit:{priority}:{current_minute}"
            
            current_count = await self.redis_client.get(key)
            current_count = int(current_count) if current_count else 0
            
            # Get rate limit based on priority
            if priority == "high":
                limit = self.rate_limits[JobPriority.HIGH]
            elif priority == "low":
                limit = self.rate_limits[JobPriority.LOW]
            else:
                limit = self.rate_limits[JobPriority.NORMAL]
            
            if current_count >= limit:
                return False
            
            # Increment counter
            await self.redis_client.incr(key)
            await self.redis_client.expire(key, 60)  # Expire after 1 minute
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Rate limit check error: {e}")
            return True  # Allow processing on error

    async def _process_call_job(self, job_data: Dict[str, Any]):
        """Process a single call job"""
        job_id = job_data['id']
        
        try:
            logger.info(f"🔄 Processing call job {job_id}")
            
            # Update job status
            job_data['status'] = JobStatus.PROCESSING.value
            await self._update_job_status(job_id, job_data)
            
            # Make HTTP request to agent service
            agent_payload = {
                "phone_number": job_data['phone_number'],
                "campaign_id": job_data['campaign_id'],
                "call_id": job_id,
                "agent_name": job_data.get('agent_name', 'wishfin-test'),
                "variables": job_data.get('variables', {}),
                "flow_name": job_data.get('agent_name', 'wishfin-test')
            }
            
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=120)  # Increased to 2 minutes for long call processing
            ) as session:
                async with session.post(
                    f"{self.agent_base_url}/start-call",
                    json=agent_payload
                ) as response:
                    
                    if response.status == 200:
                        result = await response.json()
                        
                        # Update job as completed
                        job_data['status'] = JobStatus.COMPLETED.value
                        job_data['result'] = result
                        await self._update_job_status(job_id, job_data)
                        
                        # 🚀 DISABLED: Backend notification now handled directly by bot.py
                        # await self._notify_backend(job_data, result)
                        logger.info(f"📤 OLD QUEUE: Backend notification skipped - bot.py handles this directly now")
                        
                        logger.info(f"✅ Call job {job_id} completed successfully")
                        
                    else:
                        error_text = await response.text()
                        raise Exception(f"Agent service returned {response.status}: {error_text}")
            
        except Exception as e:
            logger.error(f"❌ Call job {job_id} failed: {e}")
            
            # Handle retry logic
            await self._handle_job_failure(job_data, str(e))

    async def _handle_job_failure(self, job_data: Dict[str, Any], error_message: str):
        """Handle job failure with retry logic"""
        job_id = job_data['id']
        retry_count = job_data.get('retry_count', 0)
        max_retries = job_data.get('max_retries', 3)
        
        if retry_count < max_retries:
            # Schedule for retry with exponential backoff
            retry_delay = min(2 ** retry_count, 300)  # Max 5 minutes
            
            job_data['retry_count'] = retry_count + 1
            job_data['status'] = JobStatus.RETRY.value
            job_data['error_message'] = error_message
            
            # Add to retry queue with delay
            await asyncio.sleep(retry_delay)
            await self.redis_client.lpush(
                self.queues["calls.retry"],
                json.dumps(job_data)
            )
            
            logger.info(f"🔄 Job {job_id} scheduled for retry {retry_count + 1}/{max_retries} in {retry_delay}s")
            
        else:
            # Move to dead letter queue
            job_data['status'] = JobStatus.FAILED.value
            job_data['error_message'] = error_message
            
            await self.redis_client.lpush(
                self.queues["calls.dlq"],
                json.dumps(job_data)
            )
            
            logger.error(f"💀 Job {job_id} moved to dead letter queue after {max_retries} retries")
        
        await self._update_job_status(job_id, job_data)

    async def _process_retry_worker(self):
        """Process jobs from retry queue"""
        while self.is_running:
            try:
                result = await self.redis_client.brpop(self.queues["calls.retry"], timeout=5)
                
                if result:
                    _, job_data_json = result
                    job_data = json.loads(job_data_json)
                    
                    logger.info(f"🔄 Retrying job {job_data['id']}")
                    await self._process_call_job(job_data)
                
            except Exception as e:
                logger.error(f"❌ Retry worker error: {e}")
                await asyncio.sleep(5)

    async def _update_job_status(self, job_id: str, job_data: Dict[str, Any]):
        """Update job status in Redis"""
        try:
            await self.redis_client.setex(
                f"job:{job_id}",
                3600 * 24,  # 24 hours TTL
                json.dumps(job_data)
            )
        except Exception as e:
            logger.error(f"❌ Failed to update job status for {job_id}: {e}")

    async def _notify_backend(self, job_data: Dict[str, Any], result: Dict[str, Any]):
        """Notify backend API about call completion"""
        try:
            backend_api_url = os.getenv("BACKEND_API_URL", "http://localhost:3000")
            notify_url = f"{backend_api_url}/api/calls/external-updates"
            
            job_id = job_data['id']
            
            # Prepare payload for backend (array format as backend expects)
            notification_payload = {
                "call_id": job_id,
                "campaign_id": job_data['campaign_id'],
                "phone_number": job_data['phone_number'],
                "status": "completed" if result.get("status") != "failed" else "failed",
                "call_outcome": result.get("call_outcome", "completed"),
                "duration_seconds": result.get("duration_seconds", result.get("duration", 0)),
                "start_time": result.get("start_time"),
                "end_time": result.get("end_time"),
                "transcript": result.get("transcript", []),
                "recording_url": result.get("recording_url") or result.get("public_recording_url"),
                "variables": job_data.get("variables", {}),
                "agent_name": job_data.get("agent_name", "unknown"),
                "workflow_id": f"queue-{job_id}",
                "data_source": "queue_manager_system"
            }
            
            logger.info(f"📤 Notifying backend about call completion: {job_id}")
            
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30)
            ) as session:
                async with session.post(
                    notify_url,
                    json=[notification_payload],  # Backend expects array format
                    headers={"Content-Type": "application/json"}
                ) as response:
                    if response.status in [200, 201]:
                        response_data = await response.json()
                        logger.info(f"✅ Backend notified successfully for call {job_id}")
                    else:
                        error_text = await response.text()
                        logger.warning(f"⚠️ Backend notification failed ({response.status}): {error_text}")
                        
        except Exception as e:
            logger.error(f"❌ Failed to notify backend about call {job_data['id']}: {e}")
            # Don't raise - this shouldn't fail the call processing

    async def _cleanup_completed_jobs(self):
        """Cleanup old completed jobs"""
        while self.is_running:
            try:
                # Run cleanup every hour
                await asyncio.sleep(3600)
                
                # Clean up jobs older than 24 hours
                # This is handled by Redis TTL, but we can add additional cleanup here
                logger.info("🧹 Running job cleanup...")
                
            except Exception as e:
                logger.error(f"❌ Cleanup worker error: {e}")

    async def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get current status of a job"""
        try:
            job_data = await self.redis_client.get(f"job:{job_id}")
            return json.loads(job_data) if job_data else None
        except Exception as e:
            logger.error(f"❌ Failed to get job status for {job_id}: {e}")
            return None

    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a pending job"""
        try:
            job_data = await self.get_job_status(job_id)
            if not job_data:
                return False
            
            if job_data['status'] in [JobStatus.PENDING.value, JobStatus.RETRY.value]:
                job_data['status'] = JobStatus.CANCELLED.value
                await self._update_job_status(job_id, job_data)
                logger.info(f"🚫 Job {job_id} cancelled")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"❌ Failed to cancel job {job_id}: {e}")
            return False

    async def get_queue_stats(self) -> Dict[str, Any]:
        """Get current queue statistics"""
        try:
            stats = {}
            
            for queue_type, queue_name in self.queues.items():
                length = await self.redis_client.llen(queue_name)
                stats[queue_type] = length
            
            # Add scheduled jobs count
            scheduled_count = await self.redis_client.zcard("scheduled_jobs")
            stats["scheduled"] = scheduled_count
            
            return stats
            
        except Exception as e:
            logger.error(f"❌ Failed to get queue stats: {e}")
            return {}

# Singleton instance - Initialize with environment variables
queue_manager = ScalableQueueManager(
    redis_url=os.getenv("REDIS_URL", "redis://localhost:6379"),
    agent_base_url=os.getenv("AGENT_SERVER_URL", "http://localhost:8765")
)

# Utility functions for easy access
async def enqueue_call(phone_number: str, campaign_id: str, agent_name: str = "wishfin-test", 
                      variables: Dict[str, Any] = None, scheduled_at: datetime = None,
                      priority: JobPriority = JobPriority.NORMAL) -> str:
    """Convenience function to enqueue a call"""
    job = CallJob(
        id=str(uuid.uuid4()),
        phone_number=phone_number,
        campaign_id=campaign_id,
        agent_name=agent_name,
        variables=variables or {},
        scheduled_at=scheduled_at,
        priority=priority
    )
    
    return await queue_manager.enqueue_call(job)

async def get_job_status(job_id: str) -> Optional[Dict[str, Any]]:
    """Get job status"""
    return await queue_manager.get_job_status(job_id)

async def cancel_job(job_id: str) -> bool:
    """Cancel a job"""
    return await queue_manager.cancel_job(job_id)

async def get_queue_stats() -> Dict[str, Any]:
    """Get queue statistics"""
    return await queue_manager.get_queue_stats() 