#!/usr/bin/env python3
"""
Standalone Agent Manager - No external dependencies
Contains the essential Plivo integration code directly
"""

import asyncio
import aiohttp
import json
import os
import logging
from typing import Dict, Any, Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class StandaloneAgentManager:
    """
    Standalone agent manager with Plivo integration
    No dependency on peregrine_temporal_workers
    """
    
    def __init__(self):
        self.session = None
        
        # Import Plivo client
        try:
            import plivo
            self.plivo_client = plivo.RestClient(
                auth_id=os.getenv("PLIVO_AUTH_ID"),
                auth_token=os.getenv("PLIVO_AUTH_TOKEN")
            )
            self.plivo_number = os.getenv("PLIVO_NUMBER", "918035737670")
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
            logger.info(f"🚀 STANDALONE: Initiating call to {phone_number}")
            if custom_call_id:
                logger.info(f"📋 Using custom call ID: {custom_call_id}")
            
            # Use your answer URL (update this to your actual URL)
            answer_url = config.get("answer_url", "https://your-ngrok-url.ngrok-free.app/outbound-answer")
            
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
            
            # Notify your voice bot server about the call
            await self._notify_bot_server(tracking_call_id, phone_number, campaign_id, config, plivo_call_uuid)
            
            logger.info(f"✅ STANDALONE: Call initiated!")
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
            logger.error(f"❌ STANDALONE: Failed to make Plivo call: {e}")
            return {
                "call_id": custom_call_id if custom_call_id else None,
                "status": "failed",
                "error": str(e),
                "phone_number": phone_number
            }
    
    async def _notify_bot_server(self, call_id: str, phone_number: str, campaign_id: str, config: Dict[str, Any], plivo_call_uuid: str = None):
        """Notify your voice bot server about a new call"""
        try:
            session = await self._get_session()
            url = f"{self.agent_server_url}/start-call"
            
            payload = {
                "call_id": call_id,
                "plivo_call_uuid": plivo_call_uuid,
                "phone_number": phone_number, 
                "campaign_id": campaign_id,
                "workflow_id": f"queue-{call_id}",
                "config": config,
                "flow_name": config.get('flow_name', 'wishfin-test'),
                "variables": config.get('variables', {})
            }
            
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status == 200:
                    result = await response.json()
                    logger.info(f"✅ STANDALONE: Bot server notified about call {call_id}")
                else:
                    error_text = await response.text()
                    logger.warning(f"⚠️ STANDALONE: Failed to notify bot server: {error_text}")
                    
        except Exception as e:
            logger.warning(f"⚠️ STANDALONE: Could not notify bot server about call {call_id}: {e}")
    
    async def wait_for_completion(self, call_id: str, timeout_minutes: int = 30) -> Dict[str, Any]:
        """Wait for call completion by polling bot server"""
        logger.info(f"⏱️ STANDALONE: Waiting for call {call_id} to complete...")
        
        timeout_seconds = timeout_minutes * 60
        poll_interval = 10
        elapsed = 0
        
        while elapsed < timeout_seconds:
            try:
                # Check call status from bot server
                status = await self.check_call_status(call_id)
                call_status = status.get("status", "unknown")
                
                # Check if call is finished
                if call_status in ["completed", "failed", "error", "ended", "hangup", "missed"]:
                    logger.info(f"✅ STANDALONE: Call {call_id} finished: {call_status}")
                    
                    return {
                        "call_id": call_id,
                        "status": "completed",
                        "call_outcome": call_status,
                        "duration": status.get("duration", elapsed),
                        "transcript": status.get("transcript", []),
                        "recording_file": status.get("recording_file"),
                        "public_recording_url": status.get("public_recording_url"),
                        "recording_status": status.get("recording_status", "unknown"),
                        "agent_response": status
                    }
                
                # Continue polling
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval
                
                if elapsed <= 60:
                    logger.info(f"📞 STANDALONE: Call {call_id} ringing... ({elapsed}s)")
                elif elapsed % 30 == 0:  # Log every 30 seconds after first minute
                    logger.info(f"⏳ STANDALONE: Still waiting for {call_id}... ({elapsed}s)")
                
            except Exception as e:
                logger.error(f"❌ STANDALONE: Error checking call status: {e}")
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval
        
        # Timeout reached
        logger.warning(f"⏰ STANDALONE: Call {call_id} monitoring timed out")
        return {
            "call_id": call_id,
            "status": "completed",
            "call_outcome": "timeout",
            "duration": timeout_seconds,
            "error": "Monitoring timeout"
        }
    
    async def check_call_status(self, call_id: str) -> Dict[str, Any]:
        """Check call status from bot server"""
        try:
            session = await self._get_session()
            url = f"{self.agent_server_url}/call-status/{call_id}"
            
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    result = await response.json()
                    return result
                else:
                    logger.warning(f"⚠️ STANDALONE: Bot server returned {response.status} for call status")
                    return {"status": "unknown", "error": f"HTTP {response.status}"}
                    
        except Exception as e:
            logger.error(f"❌ STANDALONE: Error checking call status: {e}")
            return {"status": "error", "error": str(e)}
    
    async def close(self):
        """Close HTTP session"""
        if self.session:
            await self.session.close()

# Global instance for the queue system to use
standalone_agent_manager = StandaloneAgentManager()

# Functions for queue manager to use
async def standalone_initiate_call(phone_number: str, campaign_id: str, call_config: Dict[str, Any], custom_call_id: str = None) -> Dict[str, Any]:
    """Function to be called from queue manager"""
    return await standalone_agent_manager.initiate_call(phone_number, campaign_id, call_config, custom_call_id)

async def standalone_wait_for_completion(call_id: str, timeout_minutes: int = 30) -> Dict[str, Any]:
    """Function to be called from queue manager"""
    return await standalone_agent_manager.wait_for_completion(call_id, timeout_minutes)

async def standalone_check_status(call_id: str) -> Dict[str, Any]:
    """Function to be called from queue manager"""
    return await standalone_agent_manager.check_call_status(call_id) 