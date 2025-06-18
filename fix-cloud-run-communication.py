#!/usr/bin/env python3
"""
Fix Cloud Run Service Communication Issues
This script addresses the specific issues causing call tracking failures in Cloud Run
"""

import asyncio
import aiohttp
import logging
import os
import json
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CloudRunCommunicationFixer:
    """Fixes common Cloud Run service communication issues"""
    
    def __init__(self):
        self.queue_service_url = os.getenv("QUEUE_SERVICE_URL", "")
        self.agent_service_url = os.getenv("AGENT_SERVICE_URL", "")
        
    async def test_service_connectivity(self):
        """Test connectivity between services"""
        logger.info("🔍 Testing Cloud Run service connectivity...")
        
        # Test agent service health
        try:
            async with aiohttp.ClientSession() as session:
                # Add Cloud Run specific headers
                headers = {
                    "User-Agent": "CloudRunQueueSystem/1.0",
                    "Accept": "application/json",
                    "Content-Type": "application/json"
                }
                
                # Test agent service health with longer timeout
                async with session.get(
                    f"{self.agent_service_url}/health", 
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        logger.info("✅ Agent service is reachable")
                        return True
                    else:
                        logger.error(f"❌ Agent service returned {response.status}")
                        return False
                        
        except Exception as e:
            logger.error(f"❌ Cannot reach agent service: {e}")
            return False
    
    async def fix_call_status_polling(self):
        """Create improved call status polling with Cloud Run optimizations"""
        
        # This will be the new polling logic
        polling_improvements = {
            "startup_delay": 15,  # Wait 15 seconds before first status check
            "check_interval": 15,  # Check every 15 seconds instead of 10
            "max_retries": 3,     # Allow 3 failed requests before giving up
            "timeout_per_request": 30,  # 30 seconds per request
            "exponential_backoff": True,  # Use exponential backoff on failures
            "cloud_run_headers": {
                "User-Agent": "CloudRunQueueSystem/1.0",
                "Accept": "application/json",
                "X-Source": "queue-system",
                "X-Request-Type": "status-check"
            }
        }
        
        logger.info("📝 Cloud Run polling improvements configured:")
        for key, value in polling_improvements.items():
            logger.info(f"   - {key}: {value}")
        
        return polling_improvements
    
    async def create_enhanced_status_checker(self, call_id: str, agent_server_url: str):
        """Enhanced status checker optimized for Cloud Run"""
        
        async def check_with_retries(session, url, max_retries=3):
            """Check status with retry logic and Cloud Run optimizations"""
            
            headers = {
                "User-Agent": "CloudRunQueueSystem/1.0",
                "Accept": "application/json",
                "X-Source": "queue-system",
                "X-Call-ID": call_id
            }
            
            for attempt in range(max_retries):
                try:
                    timeout = aiohttp.ClientTimeout(total=30)  # 30 second timeout
                    
                    async with session.get(url, headers=headers, timeout=timeout) as response:
                        if response.status == 200:
                            result = await response.json()
                            logger.info(f"✅ Status check successful for {call_id}: {result.get('status')}")
                            return result
                        elif response.status == 404:
                            logger.info(f"📞 Call {call_id} not found - call may have ended")
                            return {"status": "not_found", "error": "Call not found"}
                        else:
                            logger.warning(f"⚠️ Status check returned {response.status}")
                            
                except asyncio.TimeoutError:
                    logger.warning(f"⏰ Status check timeout (attempt {attempt + 1}/{max_retries})")
                except Exception as e:
                    logger.warning(f"❌ Status check error (attempt {attempt + 1}/{max_retries}): {e}")
                
                # Exponential backoff between retries
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # 1s, 2s, 4s
                    await asyncio.sleep(wait_time)
            
            logger.error(f"❌ All status check attempts failed for {call_id}")
            return {"status": "error", "error": "Max retries exceeded"}
        
        return check_with_retries

# Create deployment configuration that fixes the issues
async def create_fixed_deployment_config():
    """Create a deployment configuration that fixes Cloud Run communication issues"""
    
    config = {
        "cloud_run_optimizations": {
            "service_communication": {
                "startup_delay": 15,
                "health_check_interval": 30,
                "service_timeout": 300,
                "connection_pool_size": 10,
                "keep_alive_timeout": 60
            },
            "call_tracking": {
                "initial_status_delay": 15,
                "status_check_interval": 15,
                "max_status_retries": 3,
                "call_timeout_minutes": 30,
                "auto_miss_detection_seconds": 60
            },
            "network_settings": {
                "request_timeout": 30,
                "connection_timeout": 10,
                "read_timeout": 25,
                "max_concurrent_requests": 50
            }
        },
        "environment_variables": {
            "CLOUD_RUN_OPTIMIZED": "true",
            "SERVICE_TIMEOUT": "300",
            "STATUS_CHECK_INTERVAL": "15",
            "MAX_STATUS_RETRIES": "3",
            "INITIAL_STATUS_DELAY": "15",
            "REQUEST_TIMEOUT": "30"
        }
    }
    
    logger.info("📋 Created Cloud Run optimized configuration")
    return config

async def main():
    """Main function to test and fix Cloud Run communication"""
    
    fixer = CloudRunCommunicationFixer()
    
    # Test connectivity
    logger.info("🚀 Starting Cloud Run communication diagnostics...")
    
    is_connected = await fixer.test_service_connectivity()
    
    if not is_connected:
        logger.error("❌ Service connectivity test failed!")
        logger.info("💡 Potential fixes:")
        logger.info("   1. Check service URLs in environment variables")
        logger.info("   2. Verify both services are deployed and running")
        logger.info("   3. Check Cloud Run networking configuration")
        logger.info("   4. Ensure services are in the same region")
    else:
        logger.info("✅ Service connectivity test passed!")
    
    # Create optimized configuration
    config = await create_fixed_deployment_config()
    
    # Save configuration
    with open("cloud-run-optimized-config.json", "w") as f:
        json.dump(config, f, indent=2)
    
    logger.info("💾 Saved optimized configuration to cloud-run-optimized-config.json")
    
    return is_connected

if __name__ == "__main__":
    asyncio.run(main()) 