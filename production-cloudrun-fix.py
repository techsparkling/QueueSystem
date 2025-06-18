#!/usr/bin/env python3
"""
PRODUCTION CLOUD RUN FIX
Addresses the core differences between local and Cloud Run environments
for reliable call tracking in production
"""

import asyncio
import aiohttp
import json
import os
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import plivo

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ProductionCloudRunManager:
    """Production-ready manager for Cloud Run deployment"""
    
    def __init__(self):
        # Plivo credentials
        self.plivo_auth_id = os.getenv("PLIVO_AUTH_ID")
        self.plivo_auth_token = os.getenv("PLIVO_AUTH_TOKEN")
        self.plivo_number = os.getenv("PLIVO_PHONE_NUMBER")
        
        # Service URLs
        self.agent_server_url = os.getenv("AGENT_SERVER_URL", "")
        self.backend_url = os.getenv("BACKEND_API_URL", "")
        
        # Cloud Run detection
        self.is_cloud_run = self._detect_cloud_run()
        
        # Initialize Plivo client
        if self.plivo_auth_id and self.plivo_auth_token:
            self.plivo_client = plivo.RestClient(self.plivo_auth_id, self.plivo_auth_token)
        else:
            self.plivo_client = None
            logger.warning("⚠️ Plivo credentials not found")
        
        # Production timeouts for Cloud Run
        if self.is_cloud_run:
            self.startup_timeout = 300  # 5 minutes for Cloud Run
            self.initial_delay = 30     # 30 seconds before first check
            self.check_interval = 20   # Check every 20 seconds
            self.request_timeout = 45  # 45 seconds per request
            self.max_retries = 5       # More retries for Cloud Run
            logger.info("🌩️ PRODUCTION: Cloud Run mode detected - using extended timeouts")
        else:
            self.startup_timeout = 120
            self.initial_delay = 10
            self.check_interval = 10
            self.request_timeout = 15
            self.max_retries = 3
            logger.info("🖥️ PRODUCTION: Local mode - using standard timeouts")
        
        logger.info(f"📞 PRODUCTION: Plivo Number: {self.plivo_number}")
        logger.info(f"🔗 PRODUCTION: Agent URL: {self.agent_server_url}")
        logger.info(f"⏱️ PRODUCTION: Startup timeout: {self.startup_timeout}s")
    
    def _detect_cloud_run(self) -> bool:
        """Detect if running in Cloud Run environment"""
        cloud_run_indicators = [
            os.getenv("K_SERVICE"),  # Cloud Run service name
            os.getenv("K_REVISION"), # Cloud Run revision
            os.getenv("GOOGLE_CLOUD_PROJECT"), # GCP project
            os.getenv("PORT"),  # Cloud Run port
        ]
        
        # Also check for common Cloud Run environment patterns
        is_gcp = any([
            os.getenv("GOOGLE_APPLICATION_CREDENTIALS"),
            os.getenv("GCLOUD_PROJECT"),
            "google" in os.getenv("USER_AGENT", "").lower(),
            "run.app" in self.agent_server_url
        ])
        
        return any(cloud_run_indicators) or is_gcp
    
    async def initiate_call_production(self, phone_number: str, campaign_id: str, config: Dict[str, Any], call_id: str) -> Dict[str, Any]:
        """Production call initiation with proper error handling"""
        try:
            logger.info(f"📞 PRODUCTION: Initiating call {call_id} to {phone_number}")
            
            if not self.plivo_client:
                raise Exception("Plivo client not initialized - check credentials")
            
            # Build URLs with proper Cloud Run handling
            answer_url = f"{self.agent_server_url}/outbound-answer"
            hangup_url = f"{self.agent_server_url}/hangup"
            
            # Validate URLs
            if not self.agent_server_url or "localhost" in self.agent_server_url:
                logger.warning(f"⚠️ PRODUCTION: Suspicious agent URL: {self.agent_server_url}")
            
            logger.info(f"📞 PRODUCTION: Answer URL: {answer_url}")
            
            # Make Plivo call with production settings
            call_params = {
                "from_": self.plivo_number,
                "to_": phone_number,
                "answer_url": answer_url,
                "hangup_url": hangup_url,
                "answer_method": "POST",
                "hangup_method": "POST"
            }
            
            # Add callback for status updates if in Cloud Run
            if self.is_cloud_run:
                call_params["callback_url"] = f"{self.agent_server_url}/call-status-update"
                call_params["callback_method"] = "POST"
            
            response = self.plivo_client.calls.create(**call_params)
            
            # Extract Plivo UUID
            plivo_uuid = (
                getattr(response, 'request_uuid', None) or 
                getattr(response, 'call_uuid', None) or
                getattr(response, 'uuid', None)
            )
            
            if not plivo_uuid:
                raise Exception("Failed to get Plivo call UUID from response")
            
            logger.info(f"✅ PRODUCTION: Call initiated - Plivo UUID: {plivo_uuid}")
            
            # Try to notify agent service (production-safe)
            agent_notification_success = await self._notify_agent_production(call_id, phone_number, campaign_id, config, plivo_uuid)
            
            return {
                "success": True,
                "call_id": call_id,
                "plivo_uuid": plivo_uuid,
                "status": "initiated",
                "phone_number": phone_number,
                "campaign_id": campaign_id,
                "agent_notified": agent_notification_success,
                "method": "production_plivo",
                "environment": "cloud_run" if self.is_cloud_run else "local"
            }
            
        except Exception as e:
            logger.error(f"❌ PRODUCTION: Call initiation failed for {call_id}: {e}")
            return {
                "success": False,
                "call_id": call_id,
                "error": str(e),
                "method": "production_plivo_failed"
            }
    
    async def track_call_production(self, call_id: str, plivo_uuid: str, timeout_minutes: int = 30) -> Dict[str, Any]:
        """Production call tracking with robust Cloud Run handling"""
        logger.info(f"📊 PRODUCTION: Starting call tracking for {call_id}")
        
        timeout_seconds = timeout_minutes * 60
        elapsed = 0
        
        # PRODUCTION: Extended initial delay for Cloud Run
        logger.info(f"⏳ PRODUCTION: Initial delay of {self.initial_delay}s for service readiness...")
        await asyncio.sleep(self.initial_delay)
        elapsed += self.initial_delay
        
        # Phase 1: Startup verification (production timeouts)
        startup_result = await self._verify_call_startup_production(call_id, plivo_uuid)
        elapsed += startup_result["elapsed"]
        
        if not startup_result["success"]:
            logger.error(f"❌ PRODUCTION: Call {call_id} failed to start: {startup_result['error']}")
            return await self._create_failure_result_production(call_id, "failed_to_start", elapsed, startup_result["error"])
        
        logger.info(f"✅ PRODUCTION: Call {call_id} startup verified")
        
        # Phase 2: Completion tracking (production method)
        completion_result = await self._track_completion_production(call_id, plivo_uuid, timeout_seconds - elapsed)
        
        # Phase 3: 🚀 DISABLED Backend notification (bot.py handles this directly now)
        # await self._notify_backend_production(completion_result)
        logger.info(f"📤 PRODUCTION: Backend notification skipped - bot.py handles this directly now")
        
        return completion_result
    
    async def _verify_call_startup_production(self, call_id: str, plivo_uuid: str) -> Dict[str, Any]:
        """Verify call startup with production timeouts"""
        logger.info(f"🔍 PRODUCTION: Verifying call startup for {call_id}")
        
        startup_elapsed = 0
        last_status = None
        consecutive_errors = 0
        max_consecutive_errors = 8 if self.is_cloud_run else 5
        
        while startup_elapsed < self.startup_timeout:
            try:
                # Method 1: Check Plivo API (most reliable)
                plivo_status = await self._check_plivo_status_production(plivo_uuid)
                
                if plivo_status["success"]:
                    current_status = plivo_status["status"]
                    
                    # Log status changes
                    if current_status != last_status:
                        logger.info(f"📋 PRODUCTION PLIVO: {call_id} status: {last_status} → {current_status}")
                        last_status = current_status
                    
                    # Check if call has started
                    if current_status in ["ringing", "in-progress", "answered"]:
                        logger.info(f"✅ PRODUCTION: Call {call_id} confirmed started via Plivo: {current_status}")
                        return {"success": True, "elapsed": startup_elapsed, "method": "plivo_api"}
                    
                    # Check if call completed quickly (failure cases)
                    elif current_status in ["completed", "failed", "busy", "no-answer"]:
                        duration = plivo_status.get("duration", 0)
                        if duration < 5:  # Quick completion = likely failure
                            error_msg = f"Call completed quickly with status {current_status} (duration: {duration}s)"
                            logger.warning(f"⚠️ PRODUCTION: {error_msg}")
                            return {"success": False, "elapsed": startup_elapsed, "error": error_msg}
                        else:
                            # Normal completion
                            logger.info(f"✅ PRODUCTION: Call {call_id} completed normally: {current_status}")
                            return {"success": True, "elapsed": startup_elapsed, "method": "plivo_completed"}
                
                # Reset error counter on successful check
                consecutive_errors = 0
                
                # Method 2: Check agent service (secondary verification)
                agent_status = await self._check_agent_status_production(call_id)
                
                if agent_status["success"] and agent_status["status"] not in ["unknown", "error", "not_found"]:
                    logger.info(f"✅ PRODUCTION: Call {call_id} confirmed started via agent: {agent_status['status']}")
                    return {"success": True, "elapsed": startup_elapsed, "method": "agent_api"}
                
                # Continue waiting
                await asyncio.sleep(self.check_interval)
                startup_elapsed += self.check_interval
                
                # Log progress for long waits
                if startup_elapsed % 60 == 0 and startup_elapsed > 0:
                    logger.info(f"⏳ PRODUCTION: Still verifying startup ({startup_elapsed}s/{self.startup_timeout}s)")
                
            except Exception as e:
                consecutive_errors += 1
                logger.warning(f"⚠️ PRODUCTION: Startup verification error {consecutive_errors}: {e}")
                
                # Too many consecutive errors = likely system issue
                if consecutive_errors >= max_consecutive_errors:
                    error_msg = f"Too many consecutive errors ({consecutive_errors}) during startup verification"
                    logger.error(f"❌ PRODUCTION: {error_msg}")
                    return {"success": False, "elapsed": startup_elapsed, "error": error_msg}
                
                await asyncio.sleep(self.check_interval)
                startup_elapsed += self.check_interval
        
        # Timeout reached
        error_msg = f"Startup verification timeout after {self.startup_timeout}s"
        logger.error(f"⏰ PRODUCTION: {error_msg}")
        return {"success": False, "elapsed": startup_elapsed, "error": error_msg}
    
    async def _track_completion_production(self, call_id: str, plivo_uuid: str, remaining_timeout: int) -> Dict[str, Any]:
        """Track call completion with production reliability"""
        logger.info(f"📊 PRODUCTION: Tracking completion for {call_id}")
        
        elapsed = 0
        last_status = None
        
        while elapsed < remaining_timeout:
            try:
                # Primary: Plivo API status
                plivo_status = await self._check_plivo_status_production(plivo_uuid)
                
                if plivo_status["success"]:
                    current_status = plivo_status["status"]
                    
                    # Log status changes
                    if current_status != last_status:
                        logger.info(f"📋 PRODUCTION TRACKING: {call_id} status: {last_status} → {current_status}")
                        last_status = current_status
                    
                    # Check for completion
                    if current_status in ["completed", "failed", "busy", "no-answer"]:
                        logger.info(f"✅ PRODUCTION: Call {call_id} completed with status: {current_status}")
                        
                        # Get additional data from agent (optional)
                        agent_data = await self._get_agent_data_optional(call_id)
                        
                        # Build comprehensive result
                        return await self._build_completion_result_production(
                            call_id, plivo_uuid, plivo_status, agent_data
                        )
                
                # Continue monitoring
                await asyncio.sleep(self.check_interval)
                elapsed += self.check_interval
                
                # Progress logging
                if elapsed % 120 == 0:  # Every 2 minutes
                    logger.info(f"⏳ PRODUCTION: Still tracking {call_id} ({elapsed}s elapsed)")
                
            except Exception as e:
                logger.warning(f"⚠️ PRODUCTION: Completion tracking error: {e}")
                await asyncio.sleep(self.check_interval)
                elapsed += self.check_interval
        
        # Timeout - get final status
        logger.warning(f"⏰ PRODUCTION: Completion tracking timeout for {call_id}")
        
        try:
            final_plivo_status = await self._check_plivo_status_production(plivo_uuid)
            final_agent_data = await self._get_agent_data_optional(call_id)
            
            result = await self._build_completion_result_production(
                call_id, plivo_uuid, final_plivo_status, final_agent_data
            )
            result["warning"] = f"Completed via timeout after {remaining_timeout}s"
            return result
            
        except Exception as e:
            logger.error(f"❌ PRODUCTION: Failed to get final status: {e}")
            return await self._create_failure_result_production(call_id, "timeout_error", elapsed, str(e))
    
    async def _check_plivo_status_production(self, plivo_uuid: str) -> Dict[str, Any]:
        """Check Plivo status with production error handling"""
        try:
            if not self.plivo_client:
                return {"success": False, "error": "Plivo client not available"}
            
            call_info = self.plivo_client.calls.get(plivo_uuid)
            
            return {
                "success": True,
                "status": getattr(call_info, 'call_state', 'unknown').lower(),
                "duration": int(getattr(call_info, 'duration', 0) or 0),
                "hangup_cause": getattr(call_info, 'hangup_cause', None),
                "answer_time": getattr(call_info, 'answer_time', None),
                "end_time": getattr(call_info, 'end_time', None),
                "direction": getattr(call_info, 'call_direction', 'outbound')
            }
            
        except Exception as e:
            logger.warning(f"⚠️ PRODUCTION: Plivo status check error: {e}")
            return {"success": False, "error": str(e)}
    
    async def _check_agent_status_production(self, call_id: str) -> Dict[str, Any]:
        """Check agent status with production timeouts"""
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.agent_server_url}/call-status/{call_id}"
                
                headers = {
                    "User-Agent": "ProductionCloudRunManager/1.0",
                    "Accept": "application/json",
                    "X-Source": "production-queue"
                }
                
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=self.request_timeout)) as response:
                    if response.status == 200:
                        data = await response.json()
                        return {
                            "success": True,
                            "status": data.get("status", "unknown"),
                            "data": data
                        }
                    elif response.status == 404:
                        return {"success": True, "status": "not_found"}
                    else:
                        return {"success": False, "error": f"HTTP {response.status}"}
                        
        except asyncio.TimeoutError:
            return {"success": False, "error": "Agent status check timeout"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _get_agent_data_optional(self, call_id: str) -> Dict[str, Any]:
        """Get additional data from agent service (optional)"""
        agent_status = await self._check_agent_status_production(call_id)
        
        if agent_status["success"] and "data" in agent_status:
            return agent_status["data"]
        
        return {}
    
    async def _build_completion_result_production(self, call_id: str, plivo_uuid: str, plivo_status: Dict[str, Any], agent_data: Dict[str, Any]) -> Dict[str, Any]:
        """Build comprehensive completion result"""
        
        # Determine outcome
        plivo_call_status = plivo_status.get("status", "unknown")
        duration = plivo_status.get("duration", 0)
        hangup_cause = plivo_status.get("hangup_cause", "")
        
        call_outcome = self._determine_call_outcome_production(plivo_call_status, duration, hangup_cause)
        
        # Extract agent data
        transcript = agent_data.get("transcript", [])
        recording_url = agent_data.get("public_recording_url") or agent_data.get("recording_file")
        
        result = {
            "call_id": call_id,
            "plivo_uuid": plivo_uuid,
            "status": "completed" if call_outcome != "failed" else "failed",
            "call_outcome": call_outcome,
            "duration": duration,
            "duration_seconds": duration,
            "transcript": transcript,
            "recording_file": recording_url,
            "public_recording_url": recording_url,
            "recording_status": "available" if recording_url else "not_available",
            "plivo_status": plivo_call_status,
            "hangup_cause": hangup_cause,
            "answer_time": plivo_status.get("answer_time"),
            "end_time": plivo_status.get("end_time") or datetime.now().isoformat(),
            "method": "production_tracking",
            "environment": "cloud_run" if self.is_cloud_run else "local",
            "next_action": "retry" if call_outcome in ["missed", "failed", "busy"] else "none"
        }
        
        logger.info(f"📊 PRODUCTION: Final result for {call_id}:")
        logger.info(f"   Outcome: {call_outcome}")
        logger.info(f"   Duration: {duration}s")
        logger.info(f"   Recording: {'Available' if recording_url else 'Not available'}")
        logger.info(f"   Transcript: {len(transcript)} entries")
        
        return result
    
    def _determine_call_outcome_production(self, plivo_status: str, duration: int, hangup_cause: str) -> str:
        """Determine call outcome with production logic"""
        plivo_status = plivo_status.lower()
        hangup_cause = (hangup_cause or "").lower()
        
        if plivo_status == "completed":
            if duration >= 10:  # Reasonable conversation
                return "completed"
            elif "no_answer" in hangup_cause or "no-answer" in hangup_cause:
                return "missed"
            elif "busy" in hangup_cause:
                return "busy"
            else:
                return "missed"  # Short call, likely not answered
        elif plivo_status == "failed":
            return "failed"
        elif plivo_status == "busy":
            return "busy"
        elif plivo_status in ["no-answer", "no_answer"]:
            return "missed"
        else:
            return "unknown"
    
    async def _notify_agent_production(self, call_id: str, phone_number: str, campaign_id: str, config: Dict[str, Any], plivo_uuid: str) -> bool:
        """Notify agent service with production error handling"""
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.agent_server_url}/start-call"
                payload = {
                    "call_id": call_id,
                    "plivo_call_uuid": plivo_uuid,
                    "phone_number": phone_number,
                    "campaign_id": campaign_id,
                    "config": config,
                    "method": "production_tracking"
                }
                
                headers = {
                    "Content-Type": "application/json",
                    "User-Agent": "ProductionCloudRunManager/1.0"
                }
                
                async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=self.request_timeout)) as response:
                    if response.status == 200:
                        logger.info(f"✅ PRODUCTION: Agent notified about call {call_id}")
                        return True
                    else:
                        logger.warning(f"⚠️ PRODUCTION: Agent notification returned {response.status}")
                        return False
                        
        except Exception as e:
            logger.warning(f"⚠️ PRODUCTION: Agent notification failed: {e}")
            return False
    
    async def _notify_backend_production(self, call_data: Dict[str, Any]) -> bool:
        """Notify backend with production reliability"""
        try:
            logger.info(f"📤 PRODUCTION: Notifying backend about call {call_data['call_id']}")
            
            notification = {
                "call_id": call_data["call_id"],
                "campaign_id": call_data.get("campaign_id"),
                "phone_number": call_data.get("phone_number"),
                "status": call_data["call_outcome"],
                "call_outcome": call_data["call_outcome"],
                "duration_seconds": call_data["duration_seconds"],
                "transcript": call_data.get("transcript", []),
                "recording_url": call_data.get("public_recording_url"),
                "recording_file": call_data.get("recording_file"),
                "plivo_data": {
                    "plivo_uuid": call_data.get("plivo_uuid"),
                    "plivo_status": call_data.get("plivo_status"),
                    "hangup_cause": call_data.get("hangup_cause")
                },
                "end_time": call_data.get("end_time", datetime.now().isoformat()),
                "method": "production_tracking"
            }
            
            async with aiohttp.ClientSession() as session:
                url = f"{self.backend_url}/api/calls/external-updates"
                
                async with session.post(url, json=[notification], timeout=aiohttp.ClientTimeout(total=60)) as response:
                    if response.status in [200, 201]:
                        logger.info(f"✅ PRODUCTION: Backend notification successful for call {call_data['call_id']}")
                        return True
                    else:
                        error_text = await response.text()
                        logger.error(f"❌ PRODUCTION: Backend notification failed ({response.status}): {error_text}")
                        return False
                        
        except Exception as e:
            logger.error(f"❌ PRODUCTION: Backend notification error: {e}")
            return False
    
    async def _create_failure_result_production(self, call_id: str, failure_type: str, duration: int, error: str = None) -> Dict[str, Any]:
        """Create production failure result"""
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
            "method": "production_tracking_failed",
            "environment": "cloud_run" if self.is_cloud_run else "local",
            "next_action": "retry" if failure_type != "timeout" else "none"
        } 