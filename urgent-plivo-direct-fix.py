#!/usr/bin/env python3
"""
URGENT PLIVO DIRECT FIX
Bypasses agent service communication issues and uses Plivo API directly
For demo-critical deployments where service communication is unreliable
"""

import asyncio
import aiohttp
import json
import os
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import plivo

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class UrgentPlivoDirectManager:
    """Direct Plivo API manager that bypasses unreliable service communication"""
    
    def __init__(self):
        # Plivo credentials
        self.plivo_auth_id = os.getenv("PLIVO_AUTH_ID")
        self.plivo_auth_token = os.getenv("PLIVO_AUTH_TOKEN") 
        self.plivo_number = os.getenv("PLIVO_PHONE_NUMBER")
        
        # Service URLs
        self.agent_server_url = os.getenv("AGENT_SERVER_URL", "")
        self.backend_url = os.getenv("BACKEND_API_URL", "")
        
        # Initialize Plivo client
        self.plivo_client = plivo.RestClient(self.plivo_auth_id, self.plivo_auth_token)
        
        logger.info("🚨 URGENT MODE: Using direct Plivo API for call tracking")
        logger.info(f"📞 Plivo Number: {self.plivo_number}")
        logger.info(f"🔗 Agent URL: {self.agent_server_url}")
        logger.info(f"🔗 Backend URL: {self.backend_url}")
    
    async def initiate_call_direct(self, phone_number: str, campaign_id: str, config: Dict[str, Any], call_id: str) -> Dict[str, Any]:
        """Initiate call and track it directly via Plivo API"""
        try:
            logger.info(f"🚨 URGENT: Starting direct call to {phone_number}")
            
            # Build answer URL - this MUST be publicly accessible
            answer_url = f"{self.agent_server_url}/outbound-answer"
            hangup_url = f"{self.agent_server_url}/hangup"
            
            logger.info(f"📞 Answer URL: {answer_url}")
            logger.info(f"📞 Hangup URL: {hangup_url}")
            
            # Make Plivo call
            response = self.plivo_client.calls.create(
                from_=self.plivo_number,
                to_=phone_number,
                answer_url=answer_url,
                hangup_url=hangup_url,
                answer_method="POST",
                hangup_method="POST",
                # Add callback URL for status updates
                callback_url=f"{self.agent_server_url}/call-status-update",
                callback_method="POST"
            )
            
            # Get Plivo UUID
            plivo_uuid = getattr(response, 'request_uuid', None) or getattr(response, 'call_uuid', None)
            
            if not plivo_uuid:
                raise Exception("Failed to get Plivo call UUID")
            
            logger.info(f"✅ URGENT: Call initiated - Plivo UUID: {plivo_uuid}")
            
            # Try to notify agent (but don't fail if it doesn't work)
            try:
                await self._notify_agent_optional(call_id, phone_number, campaign_id, config, plivo_uuid)
            except Exception as e:
                logger.warning(f"⚠️ Agent notification failed (continuing anyway): {e}")
            
            return {
                "success": True,
                "call_id": call_id,
                "plivo_uuid": plivo_uuid,
                "status": "initiated",
                "phone_number": phone_number,
                "campaign_id": campaign_id,
                "method": "direct_plivo"
            }
            
        except Exception as e:
            logger.error(f"❌ URGENT: Failed to initiate call: {e}")
            return {
                "success": False,
                "call_id": call_id,
                "error": str(e),
                "method": "direct_plivo"
            }
    
    async def track_call_direct(self, call_id: str, plivo_uuid: str, timeout_minutes: int = 30) -> Dict[str, Any]:
        """Track call using ONLY Plivo API - most reliable method"""
        logger.info(f"🚨 URGENT: Tracking call {call_id} directly via Plivo API")
        
        timeout_seconds = timeout_minutes * 60
        check_interval = 10  # Check every 10 seconds
        elapsed = 0
        
        last_status = None
        call_connected = False
        
        while elapsed < timeout_seconds:
            try:
                # Get call status directly from Plivo
                call_info = self.plivo_client.calls.get(plivo_uuid)
                
                current_status = getattr(call_info, 'call_state', 'unknown').lower()
                duration = int(getattr(call_info, 'duration', 0) or 0)
                hangup_cause = getattr(call_info, 'hangup_cause', None)
                answer_time = getattr(call_info, 'answer_time', None)
                end_time = getattr(call_info, 'end_time', None)
                
                # Log status changes
                if current_status != last_status:
                    logger.info(f"📋 PLIVO DIRECT: {call_id} status: {last_status} → {current_status}")
                    last_status = current_status
                
                # Track if call was ever connected
                if current_status in ['in-progress', 'answered']:
                    call_connected = True
                
                # Check for completion
                if current_status in ['completed', 'failed', 'busy', 'no-answer']:
                    logger.info(f"✅ URGENT: Call {call_id} completed with status: {current_status}")
                    
                    # Determine final outcome
                    call_outcome = self._determine_outcome(current_status, duration, hangup_cause, call_connected)
                    
                    # Try to get transcript from agent (optional)
                    transcript = await self._get_transcript_optional(call_id)
                    recording_url = await self._get_recording_optional(call_id)
                    
                    result = {
                        "call_id": call_id,
                        "plivo_uuid": plivo_uuid,
                        "status": "completed" if current_status != "failed" else "failed",
                        "call_outcome": call_outcome,
                        "duration": duration,
                        "duration_seconds": duration,
                        "transcript": transcript,
                        "recording_file": recording_url,
                        "public_recording_url": recording_url,
                        "recording_status": "available" if recording_url else "not_available",
                        "plivo_status": current_status,
                        "hangup_cause": hangup_cause,
                        "answer_time": answer_time,
                        "end_time": end_time or datetime.now().isoformat(),
                        "call_connected": call_connected,
                        "method": "direct_plivo_tracking",
                        "next_action": "retry" if call_outcome in ["missed", "failed", "busy"] else "none"
                    }
                    
                    logger.info(f"📊 URGENT: Final result for {call_id}:")
                    logger.info(f"   Outcome: {call_outcome}")
                    logger.info(f"   Duration: {duration}s")
                    logger.info(f"   Connected: {call_connected}")
                    logger.info(f"   Recording: {'Yes' if recording_url else 'No'}")
                    logger.info(f"   Transcript: {len(transcript)} entries" if transcript else "   Transcript: None")
                    
                    return result
                
                # Continue monitoring
                await asyncio.sleep(check_interval)
                elapsed += check_interval
                
                # Log progress every minute
                if elapsed % 60 == 0:
                    logger.info(f"⏳ URGENT: Still tracking {call_id} - {elapsed}s elapsed, status: {current_status}")
                
            except Exception as e:
                logger.error(f"❌ URGENT: Error checking Plivo status: {e}")
                await asyncio.sleep(check_interval)
                elapsed += check_interval
        
        # Timeout - get final status
        logger.warning(f"⏰ URGENT: Timeout for call {call_id} after {timeout_minutes} minutes")
        
        try:
            # One final check
            call_info = self.plivo_client.calls.get(plivo_uuid)
            final_status = getattr(call_info, 'call_state', 'unknown').lower()
            duration = int(getattr(call_info, 'duration', 0) or 0)
            
            call_outcome = self._determine_outcome(final_status, duration, None, call_connected)
            
            return {
                "call_id": call_id,
                "plivo_uuid": plivo_uuid,
                "status": "timeout",
                "call_outcome": call_outcome,
                "duration": duration,
                "duration_seconds": duration,
                "transcript": await self._get_transcript_optional(call_id),
                "recording_file": await self._get_recording_optional(call_id),
                "plivo_status": final_status,
                "call_connected": call_connected,
                "method": "direct_plivo_timeout",
                "warning": f"Completed via timeout after {timeout_minutes} minutes"
            }
            
        except Exception as e:
            logger.error(f"❌ URGENT: Failed final status check: {e}")
            return {
                "call_id": call_id,
                "status": "failed",
                "call_outcome": "timeout_error",
                "duration": 0,
                "error": str(e),
                "method": "direct_plivo_error"
            }
    
    def _determine_outcome(self, plivo_status: str, duration: int, hangup_cause: str = None, was_connected: bool = False) -> str:
        """Determine call outcome from Plivo data"""
        plivo_status = plivo_status.lower()
        hangup_cause = (hangup_cause or "").lower()
        
        if plivo_status == "completed":
            if duration >= 5 or was_connected:
                return "completed"  # Successful call
            elif "no_answer" in hangup_cause or "no-answer" in hangup_cause:
                return "missed"
            elif "busy" in hangup_cause:
                return "busy"
            else:
                return "missed"  # Short call, likely missed
        elif plivo_status == "failed":
            return "failed"
        elif plivo_status == "busy":
            return "busy"
        elif plivo_status in ["no-answer", "no_answer"]:
            return "missed"
        else:
            return "unknown"
    
    async def _notify_agent_optional(self, call_id: str, phone_number: str, campaign_id: str, config: Dict[str, Any], plivo_uuid: str):
        """Try to notify agent service (but don't fail if it doesn't work)"""
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.agent_server_url}/start-call"
                payload = {
                    "call_id": call_id,
                    "plivo_call_uuid": plivo_uuid,
                    "phone_number": phone_number,
                    "campaign_id": campaign_id,
                    "config": config,
                    "method": "urgent_direct"
                }
                
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        logger.info(f"✅ URGENT: Agent notified about call {call_id}")
                    else:
                        logger.warning(f"⚠️ URGENT: Agent notification returned {response.status}")
        except Exception as e:
            logger.warning(f"⚠️ URGENT: Agent notification failed: {e}")
    
    async def _get_transcript_optional(self, call_id: str) -> list:
        """Try to get transcript from agent service (optional)"""
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.agent_server_url}/call-status/{call_id}"
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get("transcript", [])
        except Exception as e:
            logger.warning(f"⚠️ URGENT: Failed to get transcript for {call_id}: {e}")
        return []
    
    async def _get_recording_optional(self, call_id: str) -> Optional[str]:
        """Try to get recording URL from agent service (optional)"""
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.agent_server_url}/call-status/{call_id}"
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get("public_recording_url") or data.get("recording_file")
        except Exception as e:
            logger.warning(f"⚠️ URGENT: Failed to get recording for {call_id}: {e}")
        return None
    
    async def notify_backend_direct(self, call_data: Dict[str, Any]) -> bool:
        """Notify backend directly with call results"""
        try:
            logger.info(f"📤 URGENT: Notifying backend about call {call_data['call_id']}")
            
            # Prepare backend notification
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
                    "hangup_cause": call_data.get("hangup_cause"),
                    "call_connected": call_data.get("call_connected", False)
                },
                "end_time": call_data.get("end_time", datetime.now().isoformat()),
                "method": "urgent_direct_tracking"
            }
            
            async with aiohttp.ClientSession() as session:
                url = f"{self.backend_url}/api/calls/external-updates"
                
                # Backend expects array format
                async with session.post(url, json=[notification], timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status in [200, 201]:
                        logger.info(f"✅ URGENT: Backend notified successfully for call {call_data['call_id']}")
                        return True
                    else:
                        error_text = await response.text()
                        logger.error(f"❌ URGENT: Backend notification failed ({response.status}): {error_text}")
                        return False
                        
        except Exception as e:
            logger.error(f"❌ URGENT: Failed to notify backend: {e}")
            return False

# Test function for urgent demo
async def test_urgent_call(phone_number: str = "+919123456789"):
    """Test the urgent direct call system"""
    logger.info("🚨 TESTING URGENT DIRECT CALL SYSTEM")
    
    manager = UrgentPlivoDirectManager()
    
    # Test call
    call_id = f"urgent-test-{int(datetime.now().timestamp())}"
    
    # Initiate call
    result = await manager.initiate_call_direct(
        phone_number=phone_number,
        campaign_id="urgent-test",
        config={"flow_name": "test", "variables": {}},
        call_id=call_id
    )
    
    if not result["success"]:
        logger.error(f"❌ Call initiation failed: {result['error']}")
        return False
    
    # Track call
    plivo_uuid = result["plivo_uuid"]
    call_data = await manager.track_call_direct(call_id, plivo_uuid, timeout_minutes=5)
    
    # 🚀 DISABLED: Backend notification now handled by bot.py directly
    # await manager.notify_backend_direct(call_data)
    logger.info(f"📤 URGENT: Backend notification skipped - bot.py handles this directly now")
    
    logger.info("🎉 URGENT TEST COMPLETED")
    return True

if __name__ == "__main__":
    # Run urgent test
    asyncio.run(test_urgent_call()) 