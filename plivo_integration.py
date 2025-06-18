#!/usr/bin/env python3
"""
Plivo Integration for Call Queue System
Handles real Plivo calls and agent communication
"""

import asyncio
import aiohttp
import json
import os
import logging
from typing import Dict, Any, Optional
from dotenv import load_dotenv
from datetime import datetime

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PlivoCallManager:
    """
    Manages Plivo calls for the queue system
    Clean implementation without external dependencies
    """
    
    def __init__(self):
        self.session = None
        
        # Initialize Plivo client
        try:
            import plivo
            self.plivo_client = plivo.RestClient(
                auth_id=os.getenv("PLIVO_AUTH_ID"),
                auth_token=os.getenv("PLIVO_AUTH_TOKEN")
            )
            self.plivo_number = os.getenv("PLIVO_PHONE_NUMBER", os.getenv("PLIVO_NUMBER", "918035737670"))
        except ImportError:
            logger.error("❌ Plivo SDK not installed. Run: pip install plivo")
            raise
        except Exception as e:
            logger.error(f"❌ Failed to initialize Plivo client: {e}")
            raise
        
        # Agent server configuration
        self.agent_server_url = os.getenv("AGENT_SERVER_URL", "https://pipecat-agent-staging-443142017693.us-east1.run.app")
        
    async def _get_session(self):
        """Get or create aiohttp session"""
        if not self.session:
            self.session = aiohttp.ClientSession()
        return self.session
    
    async def initiate_call(
        self, 
        phone_number: str, 
        campaign_id: str, 
        config: Dict[str, Any],
        custom_call_id: str = None
    ) -> Dict[str, Any]:
        """Initiate a real Plivo call"""
        try:
            logger.info(f"🚀 QUEUE: Initiating call to {phone_number}")
            if custom_call_id:
                logger.info(f"📋 Using custom call ID: {custom_call_id}")
            
            # Use answer URL from environment
            answer_url = os.getenv("SERVER_URL", self.agent_server_url) + "/outbound-answer"
            
            response = self.plivo_client.calls.create(
                from_=self.plivo_number,
                to_=phone_number,
                answer_url=answer_url,
                hangup_url=answer_url,
                answer_method="POST",
                hangup_method="POST"
            )
            
            # Get Plivo's call UUID
            plivo_call_uuid = getattr(response, 'request_uuid', None) or \
                             getattr(response, 'call_uuid', None) or \
                             getattr(response, 'uuid', None)
            
            if not plivo_call_uuid:
                plivo_call_uuid = f"unknown-{phone_number}-{int(asyncio.get_event_loop().time())}"
            
            # Determine final call_id
            tracking_call_id = custom_call_id if custom_call_id else plivo_call_uuid
            
            # Notify agent server
            await self._notify_agent_server(tracking_call_id, phone_number, campaign_id, config, plivo_call_uuid)
            
            logger.info(f"✅ QUEUE: Call initiated!")
            logger.info(f"📋 Tracking Call ID: {tracking_call_id}")
            logger.info(f"📋 Plivo Call UUID: {plivo_call_uuid}")
            
            return {
                "call_id": tracking_call_id,
                "plivo_call_uuid": plivo_call_uuid,
                "status": "initiated", 
                "phone_number": phone_number,
                "campaign_id": campaign_id,
                "plivo_response": getattr(response, 'message', 'Call initiated')
            }
                    
        except Exception as e:
            logger.error(f"❌ QUEUE: Failed to make Plivo call: {e}")
            return {
                "call_id": custom_call_id if custom_call_id else None,
                "status": "failed",
                "error": str(e),
                "phone_number": phone_number
            }
    
    async def _notify_agent_server(self, call_id: str, phone_number: str, campaign_id: str, config: Dict[str, Any], plivo_call_uuid: str = None):
        """Notify the agent server about a new call - FIXED to pass backend call_id properly"""
        try:
            session = await self._get_session()
            url = f"{self.agent_server_url}/start-call"
            
            # CRITICAL FIX: Use the backend's call_id, not our internal queue ID
            backend_call_id = config.get('backend_call_id') or call_id
            
            payload = {
                "call_id": backend_call_id,  # Use backend's call_id for proper tracking
                "plivo_call_uuid": plivo_call_uuid,
                "phone_number": phone_number, 
                "campaign_id": campaign_id,
                "workflow_id": f"queue-{call_id}",  # Keep queue reference in workflow_id
                "config": config,
                "flow_name": config.get('flow_name', 'wishfin-test'),
                "variables": config.get('variables', {}),  # PASS VARIABLES FROM CONFIG
                # Additional metadata for tracking
                "queue_call_id": call_id,  # Keep reference to queue ID
                "data_source": "call_queue_system"
            }
            
            logger.info(f"📤 Notifying agent server with backend call_id: {backend_call_id}")
            logger.info(f"📋 Variables: {len(payload['variables'])} fields")
            logger.info(f"🎯 Flow: {payload['flow_name']}")
            
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status == 200:
                    result = await response.json()
                    logger.info(f"✅ QUEUE: Agent server notified about call {backend_call_id}")
                    logger.info(f"📋 Agent response: {result}")
                else:
                    error_text = await response.text()
                    logger.warning(f"⚠️ QUEUE: Failed to notify agent server: {error_text}")
                    
        except Exception as e:
            logger.warning(f"⚠️ QUEUE: Could not notify agent server about call {call_id}: {e}")
    
    async def wait_for_completion(self, call_id: str, timeout_minutes: int = 30) -> Dict[str, Any]:
        """Wait for call completion by polling agent server (like Temporal system) - CLOUD RUN OPTIMIZED"""
        logger.info(f"⏱️ QUEUE: Waiting for call completion for {call_id}...")
        
        timeout_seconds = timeout_minutes * 60
        
        # CLOUD RUN FIX: Longer startup delay to allow agent service to register the call
        cloud_run_mode = os.getenv("CLOUD_RUN_OPTIMIZED", "false").lower() == "true"
        if cloud_run_mode:
            check_interval = int(os.getenv("STATUS_CHECK_INTERVAL", "15"))  # 15 seconds for Cloud Run
            startup_timeout = 180  # 3 minutes for Cloud Run startup
            initial_delay = int(os.getenv("INITIAL_STATUS_DELAY", "20"))  # 20 seconds initial delay
            max_retries = int(os.getenv("MAX_STATUS_RETRIES", "3"))
            request_timeout = int(os.getenv("REQUEST_TIMEOUT", "30"))
            logger.info(f"🌩️ CLOUD RUN MODE: Delays={initial_delay}s, Interval={check_interval}s, Timeout={request_timeout}s")
        else:
            check_interval = 10
            startup_timeout = 120
            initial_delay = 5
            max_retries = 2
            request_timeout = 10
            logger.info(f"🖥️ LOCAL MODE: Standard timing configuration")
        
        elapsed = 0
        
        # CLOUD RUN FIX: Initial delay to allow agent service to register the call
        logger.info(f"⏳ QUEUE: Initial delay of {initial_delay}s for agent service to register call...")
        await asyncio.sleep(initial_delay)
        elapsed += initial_delay
        
        # First verify the call started properly (Cloud Run optimized)
        startup_elapsed = 0
        call_started = False
        consecutive_errors = 0
        
        logger.info(f"🔍 QUEUE: Checking if call {call_id} starts properly...")
        
        while startup_elapsed < startup_timeout and not call_started:
            try:
                # CLOUD RUN FIX: Enhanced status check with retry logic
                status = await self._check_call_status_with_retries(call_id, max_retries, request_timeout)
                call_status = status.get("status", "unknown")
                
                # Reset error counter on successful check
                consecutive_errors = 0
                
                if call_status in ["unknown", "error"]:
                    # Still starting up or temporary error
                    logger.info(f"📞 QUEUE: Call {call_id} starting/initializing... ({startup_elapsed + initial_delay}s total)")
                    await asyncio.sleep(check_interval)
                    startup_elapsed += check_interval
                    continue
                elif call_status in ["initiated", "ringing", "in_progress", "active", "connected", "talking"]:
                    # Call has started successfully
                    call_started = True
                    logger.info(f"✅ QUEUE: Call {call_id} started successfully with status: {call_status}")
                    break
                elif call_status in ["completed", "ended", "hangup", "failed", "missed", "busy", "rejected"]:
                    # Call completed quickly (probably failed/missed)
                    logger.info(f"📞 QUEUE: Call {call_id} completed quickly with status: {call_status}")
                    
                    # ENHANCED: Get comprehensive completion data
                    completion_data = await self._get_completion_data(call_id, status)
                    return completion_data
                elif call_status == "not_found":
                    # Call not registered yet - common in Cloud Run
                    logger.info(f"📞 QUEUE: Call {call_id} not registered yet, continuing to wait...")
                    await asyncio.sleep(check_interval)
                    startup_elapsed += check_interval
                    continue
                    
            except Exception as e:
                consecutive_errors += 1
                logger.warning(f"⚠️ QUEUE: Error checking startup status (error {consecutive_errors}): {e}")
                
                # CLOUD RUN FIX: More tolerant of initial errors
                if consecutive_errors >= 5:  # Allow more errors in Cloud Run
                    logger.error(f"❌ QUEUE: Too many consecutive errors ({consecutive_errors}) checking call {call_id}")
                    return await self._create_failure_result(call_id, "startup_errors", startup_elapsed + initial_delay, f"Consecutive errors: {e}")
                
                await asyncio.sleep(check_interval)
                startup_elapsed += check_interval
        
        if not call_started:
            logger.error(f"❌ QUEUE: Call {call_id} failed to start within {startup_timeout}s")
            return await self._create_failure_result(call_id, "failed_to_start", startup_elapsed + initial_delay)
        
        # Now wait for completion using TRIPLE approach: Plivo API + Redis callbacks + Agent polling
        logger.info(f"⏳ QUEUE: Waiting for call completion for {call_id}...")
        last_status = None
        consecutive_completed_checks = 0
        consecutive_errors = 0
        
        # Import redis for callback checking
        import redis.asyncio as redis
        redis_client = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))
        
        # Get Plivo UUID for direct API checking (like Temporal system)
        job_key = f"call_job:{call_id}"
        plivo_uuid = await redis_client.hget(job_key, "plivo_uuid")
        if plivo_uuid:
            plivo_uuid = plivo_uuid.decode() if isinstance(plivo_uuid, bytes) else plivo_uuid
            logger.info(f"📋 QUEUE: Will use Plivo API checking with UUID: {plivo_uuid}")
        
        while elapsed < timeout_seconds:
            try:
                # PRIORITY 1: Check for completion callback in Redis (like Temporal did)
                result_data = await redis_client.hget(job_key, "result")
                redis_status = await redis_client.hget(job_key, "status")
                
                if result_data:
                    # We have completion data from agent callback!
                    logger.info(f"✅ QUEUE: Received completion callback for call {call_id}")
                    result = json.loads(result_data)
                    logger.info(f"   Status: {result.get('call_outcome', 'unknown')}")
                    logger.info(f"   Duration: {result.get('duration_seconds', 0)}s")
                    return result
                
                # PRIORITY 2: Check Plivo API directly (like Temporal system) - GROUND TRUTH
                if plivo_uuid:
                    plivo_status = await self.check_plivo_call_status(plivo_uuid)
                    current_plivo_status = plivo_status.get("status", "unknown")
                    
                    # Log Plivo status changes
                    if current_plivo_status != last_status:
                        logger.info(f"📋 PLIVO: Call {call_id} status changed: {last_status} → {current_plivo_status}")
                        last_status = current_plivo_status
                        consecutive_completed_checks = 0
                    
                    # Check for completion via Plivo API (most reliable)
                    if current_plivo_status in ["completed", "failed", "missed", "busy", "rejected"]:
                        consecutive_completed_checks += 1
                        
                        # Require 2 consecutive "completed" checks from Plivo
                        if consecutive_completed_checks >= 2 or current_plivo_status != "completed":
                            logger.info(f"✅ QUEUE: Call {call_id} confirmed completed via Plivo API: {current_plivo_status}")
                            
                            # Get agent data for transcript/recording (secondary data)
                            agent_status = await self._check_call_status_with_retries(call_id, max_retries, request_timeout)
                            
                            # Combine Plivo (primary) + Agent (secondary) data
                            completion_data = await self._combine_plivo_agent_data(call_id, plivo_status, agent_status)
                            return completion_data
                        else:
                            logger.info(f"📋 PLIVO: Call {call_id} status '{current_plivo_status}' - confirming...")
                
                    # CRITICAL: Auto-detect missed calls stuck in "initiated" for >60s (Cloud Run optimized)
                    elif current_plivo_status in ["initiated", "queued", "ringing"] and elapsed >= 60:
                        logger.warning(f"⏰ QUEUE: Call {call_id} stuck in '{current_plivo_status}' for {elapsed}s - auto-marking as MISSED")
                        
                        # Create missed call result using Plivo data
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
                            "end_time": datetime.now().isoformat(),
                            "hangup_cause": "no_answer_timeout",
                            "plivo_data": plivo_status.get("plivo_data", {}),
                            "plivo_status": current_plivo_status,
                            "agent_response": {"transcript": [], "call_outcome": "missed"},
                            "next_action": "retry",
                            "data_source": "plivo_api_timeout_detection",
                            "auto_detected": True,
                            "detection_reason": f"Stuck in '{current_plivo_status}' for {elapsed}s"
                        }
                        
                        logger.info(f"📵 QUEUE: Auto-detected MISSED call {call_id} - will be sent to backend and removed from queue")
                        return missed_result
                
                # PRIORITY 3: Agent server fallback - for transcript/recording data (Cloud Run optimized)
                status = await self._check_call_status_with_retries(call_id, max_retries, request_timeout)
                current_status = status.get("status", "unknown")
                
                # Reset error counter on successful check
                consecutive_errors = 0
                
                # Check if call not found (agent server cleaned it up)
                if status.get("error") and "not found" in status.get("error", "").lower():
                    logger.info(f"📞 QUEUE: Agent server says call {call_id} not found - call likely ended")
                    return await self._create_failure_result(call_id, "call_not_found", elapsed, "Call not found on agent server")
                
                # Log status changes
                if current_status != last_status:
                    logger.info(f"📋 QUEUE: Call {call_id} status changed: {last_status} → {current_status}")
                    last_status = current_status
                    consecutive_completed_checks = 0
                
                # Check for completion via polling
                if current_status in ["completed", "ended", "hangup", "failed", "missed", "busy", "rejected"]:
                    consecutive_completed_checks += 1
                    
                    # Require 2 consecutive "completed" checks to avoid false positives
                    if consecutive_completed_checks >= 2 or current_status != "completed":
                        logger.info(f"✅ QUEUE: Call {call_id} confirmed completed via polling with status: {current_status}")
                        
                        # Get comprehensive completion data
                        completion_data = await self._get_completion_data(call_id, status)
                        return completion_data
                    else:
                        logger.info(f"📋 QUEUE: Call {call_id} status '{current_status}' - confirming...")
                
                # CRITICAL: Auto-detect missed calls stuck in "initiated" for >60s (agent fallback)
                elif current_status in ["initiated", "unknown"] and elapsed >= 60:
                    logger.warning(f"⏰ QUEUE: Call {call_id} stuck in '{current_status}' for {elapsed}s - auto-marking as MISSED (agent fallback)")
                    
                    # Create missed call result
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
                        "end_time": datetime.now().isoformat(),
                        "hangup_cause": "no_answer_timeout",
                        "agent_response": {"transcript": [], "call_outcome": "missed"},
                        "next_action": "retry",
                        "data_source": "agent_api_timeout_detection",
                        "auto_detected": True,
                        "detection_reason": f"Stuck in '{current_status}' for {elapsed}s"
                    }
                    
                    logger.info(f"📵 QUEUE: Auto-detected MISSED call {call_id} - will be sent to backend and removed from queue")
                    return missed_result
                
                # Continue waiting
                await asyncio.sleep(check_interval)
                elapsed += check_interval
                
                # Log progress periodically
                if elapsed % 60 == 0:  # Every minute
                    logger.info(f"⏳ QUEUE: Still waiting for completion ({elapsed}s/{timeout_seconds}s) - Status: {current_status}")
                
            except Exception as e:
                consecutive_errors += 1
                logger.warning(f"⚠️ QUEUE: Error in completion check (error {consecutive_errors}): {e}")
                
                # CRITICAL FIX: If we can't reach the agent server or call not found,
                # the call has likely ended - check Redis for any completion data
                try:
                    result_data = await redis_client.hget(job_key, "result")
                    if result_data:
                        logger.info(f"✅ QUEUE: Found completion data in Redis during error recovery")
                        return json.loads(result_data)
                except:
                    pass
                
                # CLOUD RUN FIX: More tolerant of errors, longer backoff
                if consecutive_errors >= 6:  # Allow more errors in Cloud Run
                    logger.warning(f"💥 QUEUE: {consecutive_errors} consecutive errors checking call {call_id} - assuming call ended")
                    
                    # Create a completion result based on error
                    return await self._create_failure_result(
                        call_id, 
                        "connection_lost", 
                        elapsed,
                        f"Lost connection to agent server after {consecutive_errors} attempts"
                    )
                
                # Exponential backoff on errors
                error_backoff = min(consecutive_errors * 5, 30)  # 5s, 10s, 15s, ... max 30s
                await asyncio.sleep(error_backoff)
                elapsed += error_backoff
        
        # Timeout reached - get final status
        logger.warning(f"⏰ QUEUE: Timeout waiting for completion ({timeout_minutes} min), getting final status...")
        try:
            final_status = await self._check_call_status_with_retries(call_id, max_retries, request_timeout)
            logger.info(f"📋 QUEUE: Final status for {call_id}: {final_status.get('status', 'unknown')}")
            
            # Create timeout result with final status
            completion_data = await self._get_completion_data(call_id, final_status, is_timeout=True)
            return completion_data
            
        except Exception as e:
            logger.error(f"❌ QUEUE: Failed to get final status: {e}")
            return await self._create_failure_result(call_id, "timeout", timeout_seconds, str(e))
    
    async def _check_call_status_with_retries(self, call_id: str, max_retries: int = 3, timeout_seconds: int = 30) -> Dict[str, Any]:
        """Enhanced call status checking with Cloud Run optimizations"""
        
        for attempt in range(max_retries):
            try:
                session = await self._get_session()
                url = f"{self.agent_server_url}/call-status/{call_id}"
                
                # Cloud Run optimized headers
                headers = {
                    "User-Agent": "CloudRunQueueSystem/1.0",
                    "Accept": "application/json",
                    "X-Source": "queue-system",
                    "X-Call-ID": call_id,
                    "X-Attempt": str(attempt + 1)
                }
                
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=timeout_seconds)) as response:
                    if response.status == 200:
                        result = await response.json()
                        call_status = result.get("status", "unknown")
                        
                        return {
                            "call_id": call_id,
                            "status": call_status,
                            "duration": result.get("duration", 0),
                            "transcript": result.get("transcript", []),
                            "recording_file": result.get("recording_file"),
                            "public_recording_url": result.get("public_recording_url"),
                            "recording_status": result.get("recording_status", "unknown"),
                            "agent_response": result
                        }
                    elif response.status == 404:
                        logger.info(f"📞 QUEUE: Call {call_id} not found on agent server (404) - likely not registered yet or ended")
                        return {"status": "not_found", "error": "Call not found"}
                    else:
                        logger.warning(f"⚠️ QUEUE: Agent server returned {response.status} for call status (attempt {attempt + 1})")
                        if attempt == max_retries - 1:  # Last attempt
                            return {"status": "unknown", "error": f"HTTP {response.status}"}
                        
            except asyncio.TimeoutError:
                logger.warning(f"⏰ QUEUE: Status check timeout for {call_id} (attempt {attempt + 1}/{max_retries})")
                if attempt == max_retries - 1:
                    return {"status": "error", "error": "Timeout"}
            except Exception as e:
                logger.warning(f"❌ QUEUE: Error checking call status for {call_id} (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt == max_retries - 1:
                    return {"status": "error", "error": str(e)}
            
            # Exponential backoff between retries
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # 1s, 2s, 4s
                await asyncio.sleep(wait_time)
        
        return {"status": "error", "error": "Max retries exceeded"}
    
    async def _combine_plivo_agent_data(self, call_id: str, plivo_status: Dict[str, Any], agent_status: Dict[str, Any]) -> Dict[str, Any]:
        """Combine Plivo call status (primary) with agent transcript/recording data (secondary)"""
        try:
            # Use Plivo data as primary source (most reliable)
            duration = plivo_status.get("duration", 0)
            call_outcome = plivo_status.get("status", "completed")
            hangup_cause = plivo_status.get("hangup_cause")
            
            # Get transcript and recording from agent (secondary source)
            transcript = agent_status.get("transcript", [])
            recording_file = agent_status.get("recording_file")
            public_recording_url = agent_status.get("public_recording_url")
            recording_status = agent_status.get("recording_status", "unknown")
            
            # Build comprehensive result
            result = {
                "call_id": call_id,
                "status": "completed" if call_outcome not in ["failed"] else "failed",
                "call_outcome": call_outcome,
                "duration": duration,
                "duration_seconds": duration,
                
                # Transcript from agent server
                "transcript": transcript,
                "main_transcript": transcript,
                "agent_transcript": transcript,
                
                # Recording from agent server
                "recording_file": recording_file,
                "public_recording_url": public_recording_url,
                "recording_status": recording_status,
                
                # Timing from Plivo
                "end_time": plivo_status.get("end_time") or datetime.now().isoformat(),
                "answer_time": plivo_status.get("answer_time"),
                
                # Plivo metadata
                "hangup_cause": hangup_cause,
                "plivo_data": plivo_status.get("plivo_data", {}),
                "plivo_status": plivo_status.get("plivo_status"),
                
                # Agent response structure for compatibility
                "agent_response": {
                    "call_id": call_id,
                    "status": call_outcome,
                    "duration": duration,
                    "transcript": transcript,
                    "recording_file": recording_file,
                    "recording_status": recording_status,
                    "public_recording_url": public_recording_url,
                    "agent_response": {
                        "transcript": transcript,
                        "call_outcome": call_outcome,
                        "error": agent_status.get("error")
                    }
                },
                
                "next_action": "retry" if call_outcome in ["missed", "failed"] else "none",
                "data_source": "plivo_api_primary"
            }
            
            logger.info(f"📋 QUEUE: Combined data for {call_id}: Plivo({call_outcome}, {duration}s) + Agent({len(transcript)} transcript, {recording_status} recording)")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ QUEUE: Error combining Plivo+Agent data: {e}")
            # Fallback to agent data only
            return await self._get_completion_data(call_id, agent_status)
    
    async def _get_completion_data(self, call_id: str, status: Dict[str, Any], is_timeout: bool = False) -> Dict[str, Any]:
        """Get comprehensive completion data matching Temporal format"""
        try:
            # Extract comprehensive data from status
            duration = status.get("duration", 0)
            if isinstance(duration, str):
                try:
                    duration = int(float(duration))
                except:
                    duration = 0
            
            transcript = status.get("transcript", [])
            if not isinstance(transcript, list):
                transcript = []
            
            call_outcome = status.get("status", "completed")
            if call_outcome == "completed" and is_timeout:
                call_outcome = "timeout"
            
            # Build comprehensive result
            result = {
                "call_id": call_id,
                "status": "completed" if not is_timeout else "timeout",
                "call_outcome": call_outcome,
                "duration": duration,
                "duration_seconds": duration,
                "transcript": transcript,
                "recording_file": status.get("recording_file"),
                "public_recording_url": status.get("public_recording_url"),
                "recording_status": status.get("recording_status", "unknown"),
                "end_time": datetime.now().isoformat(),
                "agent_response": status.get("agent_response", status),
                "next_action": "retry" if call_outcome in ["missed", "failed"] else "none"
            }
            
            if is_timeout:
                result["warning"] = f"Completed via timeout - final status: {call_outcome}"
            
            logger.info(f"📋 QUEUE: Completion data for {call_id}: {call_outcome}, {duration}s, {len(transcript)} transcript entries")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ QUEUE: Error building completion data: {e}")
            return await self._create_failure_result(call_id, "data_error", 0, str(e))
    
    async def _create_failure_result(self, call_id: str, failure_type: str, duration: int, error: str = None) -> Dict[str, Any]:
        """Create a failure result"""
        return {
            "call_id": call_id,
            "status": "failed",
            "call_outcome": failure_type,
            "duration": duration,
            "duration_seconds": duration,
            "transcript": [],
            "recording_file": None,
            "public_recording_url": None,
            "recording_status": "failed",
            "end_time": datetime.now().isoformat(),
            "error": error or f"Call {failure_type}",
            "next_action": "retry" if failure_type != "timeout" else "none"
        }
    
    async def check_call_status(self, call_id: str) -> Dict[str, Any]:
        """Check call status from agent server"""
        try:
            session = await self._get_session()
            url = f"{self.agent_server_url}/call-status/{call_id}"
            
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    result = await response.json()
                    call_status = result.get("status", "unknown")
                    
                    return {
                        "call_id": call_id,
                        "status": call_status,
                        "duration": result.get("duration", 0),
                        "transcript": result.get("transcript", []),
                        "recording_file": result.get("recording_file"),
                        "public_recording_url": result.get("public_recording_url"),
                        "recording_status": result.get("recording_status", "unknown"),
                        "agent_response": result
                    }
                elif response.status == 404:
                    logger.info(f"📞 QUEUE: Call {call_id} not found on agent server (404) - likely ended")
                    return {"status": "unknown", "error": "Call not found"}
                else:
                    logger.warning(f"⚠️ QUEUE: Agent server returned {response.status} for call status")
                    return {"status": "unknown", "error": f"HTTP {response.status}"}
                    
        except Exception as e:
            logger.error(f"❌ QUEUE: Error checking call status: {e}")
            return {"status": "error", "error": str(e)}
    
    async def close(self):
        """Close HTTP session"""
        if self.session:
            await self.session.close()

    async def check_plivo_call_status(self, plivo_call_uuid: str) -> Dict[str, Any]:
        """Check call status directly from Plivo API (like Temporal system)"""
        try:
            if not plivo_call_uuid:
                return {"status": "unknown", "error": "No Plivo UUID provided"}
            
            logger.info(f"📞 QUEUE: Checking Plivo API for call status: {plivo_call_uuid}")
            
            # Get call details from Plivo API
            call_response = self.plivo_client.calls.get(plivo_call_uuid)
            
            # Extract call information
            call_status = getattr(call_response, 'call_state', 'unknown').lower()
            call_direction = getattr(call_response, 'call_direction', 'unknown')
            duration = getattr(call_response, 'duration', 0)
            hangup_cause = getattr(call_response, 'hangup_cause', None)
            answer_time = getattr(call_response, 'answer_time', None)
            end_time = getattr(call_response, 'end_time', None)
            
            # Convert Plivo duration to integer
            try:
                duration = int(duration) if duration else 0
            except:
                duration = 0
            
            logger.info(f"📋 PLIVO: Call {plivo_call_uuid} - Status: {call_status}, Duration: {duration}s, Cause: {hangup_cause}")
            
            # Map Plivo status to our status system
            mapped_status = self._map_plivo_status(call_status, duration, hangup_cause)
            
            return {
                "call_id": plivo_call_uuid,
                "status": mapped_status,
                "plivo_status": call_status,
                "duration": duration,
                "hangup_cause": hangup_cause,
                "answer_time": answer_time,
                "end_time": end_time,
                "direction": call_direction,
                "plivo_data": {
                    "call_state": call_status,
                    "duration": duration,
                    "hangup_cause": hangup_cause,
                    "answer_time": answer_time,
                    "end_time": end_time,
                    "call_direction": call_direction
                }
            }
            
        except Exception as e:
            logger.error(f"❌ QUEUE: Error checking Plivo call status: {e}")
            return {"status": "error", "error": str(e), "plivo_uuid": plivo_call_uuid}
    
    def _map_plivo_status(self, plivo_status: str, duration: int, hangup_cause: str = None) -> str:
        """Map Plivo call status to our internal status system"""
        plivo_status = plivo_status.lower() if plivo_status else "unknown"
        hangup_cause = hangup_cause.lower() if hangup_cause else ""
        
        # Map based on Plivo status
        if plivo_status in ["queued", "initiated"]:
            return "initiated"
        elif plivo_status in ["ringing"]:
            return "ringing"
        elif plivo_status in ["in-progress", "answered"]:
            return "in_progress"
        elif plivo_status in ["completed"]:
            # For completed calls, check duration and hangup cause
            if duration < 5:  # Very short calls are likely missed
                if "no_answer" in hangup_cause or "no-answer" in hangup_cause:
                    return "missed"
                elif "busy" in hangup_cause:
                    return "busy"
                elif "rejected" in hangup_cause:
                    return "rejected"
                else:
                    return "missed"  # Default for short calls
            else:
                return "completed"  # Normal completion
        elif plivo_status in ["failed"]:
            return "failed"
        elif plivo_status in ["busy"]:
            return "busy"
        elif plivo_status in ["no-answer", "no_answer"]:
            return "missed"
        elif plivo_status in ["rejected"]:
            return "rejected"
        else:
            return "unknown"

# Global instance for the queue system
plivo_call_manager = PlivoCallManager()

# Functions for queue manager to use
async def initiate_call(phone_number: str, campaign_id: str, call_config: Dict[str, Any], custom_call_id: str = None) -> Dict[str, Any]:
    """Function to be called from queue manager"""
    return await plivo_call_manager.initiate_call(phone_number, campaign_id, call_config, custom_call_id)

async def wait_for_completion(call_id: str, timeout_minutes: int = 30) -> Dict[str, Any]:
    """Function to be called from queue manager"""
    return await plivo_call_manager.wait_for_completion(call_id, timeout_minutes)

async def check_call_status(call_id: str) -> Dict[str, Any]:
    """Function to be called from queue manager"""
    return await plivo_call_manager.check_call_status(call_id) 

async def check_plivo_call_status(plivo_call_uuid: str) -> Dict[str, Any]:
    """Function to check Plivo API directly (like Temporal system)"""
    return await plivo_call_manager.check_plivo_call_status(plivo_call_uuid) 