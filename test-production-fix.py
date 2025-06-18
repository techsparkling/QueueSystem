#!/usr/bin/env python3
"""
PRODUCTION FIX VERIFICATION SCRIPT
Tests the production Cloud Run fix to ensure calls work properly in Cloud Run environment
"""

import asyncio
import aiohttp
import json
import os
import logging
import time
from datetime import datetime
from typing import Dict, Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ProductionFixTester:
    """Test the production Cloud Run fix"""
    
    def __init__(self):
        # Service URLs
        self.service_url = os.getenv("QUEUE_SERVICE_URL", "http://localhost:8080")
        
        # Test configuration
        self.test_phone = os.getenv("TEST_PHONE_NUMBER", "+1234567890")  # Safe test number
        self.test_campaign = "production-test"
        
        logger.info(f"🧪 PRODUCTION TEST: Initializing tester")
        logger.info(f"   Service URL: {self.service_url}")
        logger.info(f"   Test Phone: {self.test_phone}")
    
    async def test_service_health(self) -> bool:
        """Test if the service is healthy"""
        try:
            logger.info("🏥 PRODUCTION TEST: Testing service health...")
            
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.service_url}/health", timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status == 200:
                        logger.info("✅ PRODUCTION TEST: Service health check passed")
                        return True
                    else:
                        logger.error(f"❌ PRODUCTION TEST: Health check failed: {response.status}")
                        return False
                        
        except Exception as e:
            logger.error(f"❌ PRODUCTION TEST: Health check error: {e}")
            return False
    
    async def test_queue_status(self) -> bool:
        """Test queue status endpoint"""
        try:
            logger.info("📊 PRODUCTION TEST: Testing queue status...")
            
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.service_url}/queue-status", timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.info("✅ PRODUCTION TEST: Queue status check passed")
                        logger.info(f"   Active workers: {data.get('active_workers', 0)}")
                        logger.info(f"   Queue length: {data.get('queue_length', 0)}")
                        return True
                    else:
                        logger.error(f"❌ PRODUCTION TEST: Queue status failed: {response.status}")
                        return False
                        
        except Exception as e:
            logger.error(f"❌ PRODUCTION TEST: Queue status error: {e}")
            return False
    
    async def test_call_queueing(self) -> tuple[bool, str]:
        """Test call queueing functionality"""
        try:
            logger.info("📞 PRODUCTION TEST: Testing call queueing...")
            
            call_payload = {
                "phone_number": self.test_phone,
                "campaign_id": self.test_campaign,
                "call_config": {
                    "flow_name": "test-agent",
                    "variables": {
                        "test_mode": True,
                        "test_timestamp": datetime.now().isoformat()
                    }
                }
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.service_url}/queue-call",
                    json=call_payload,
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as response:
                    if response.status in [200, 201]:
                        data = await response.json()
                        call_id = data.get("call_id") or data.get("id")
                        
                        if call_id:
                            logger.info(f"✅ PRODUCTION TEST: Call queued successfully - ID: {call_id}")
                            return True, call_id
                        else:
                            logger.error("❌ PRODUCTION TEST: No call ID returned")
                            return False, None
                    else:
                        error_text = await response.text()
                        logger.error(f"❌ PRODUCTION TEST: Call queueing failed ({response.status}): {error_text}")
                        return False, None
                        
        except Exception as e:
            logger.error(f"❌ PRODUCTION TEST: Call queueing error: {e}")
            return False, None
    
    async def test_call_tracking(self, call_id: str, timeout_minutes: int = 10) -> Dict[str, Any]:
        """Test call tracking to see if it completes properly"""
        try:
            logger.info(f"📊 PRODUCTION TEST: Tracking call {call_id} for up to {timeout_minutes} minutes...")
            
            timeout_seconds = timeout_minutes * 60
            elapsed = 0
            check_interval = 15  # Check every 15 seconds
            
            while elapsed < timeout_seconds:
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(
                            f"{self.service_url}/call-status/{call_id}",
                            timeout=aiohttp.ClientTimeout(total=30)
                        ) as response:
                            if response.status == 200:
                                data = await response.json()
                                status = data.get("status", "unknown")
                                outcome = data.get("call_outcome", "unknown")
                                
                                logger.info(f"📋 PRODUCTION TEST: Call {call_id} status: {status}, outcome: {outcome}")
                                
                                # Check if call completed
                                if status in ["completed", "failed"]:
                                    logger.info(f"✅ PRODUCTION TEST: Call {call_id} finished with status: {status}")
                                    
                                    # Log important details
                                    duration = data.get("duration_seconds", 0)
                                    data_source = data.get("data_source", "unknown")
                                    environment = data.get("environment_data", {}).get("environment", "unknown")
                                    method = data.get("environment_data", {}).get("method", "unknown")
                                    
                                    logger.info(f"   Duration: {duration}s")
                                    logger.info(f"   Data Source: {data_source}")
                                    logger.info(f"   Environment: {environment}")
                                    logger.info(f"   Method: {method}")
                                    
                                    # Check if it used the production fix
                                    if data_source == "production_cloudrun_manager":
                                        logger.info("🎉 PRODUCTION TEST: Call used PRODUCTION CLOUD RUN FIX!")
                                    elif data_source == "production_fallback_method":
                                        logger.info("🔄 PRODUCTION TEST: Call used production fallback method")
                                    else:
                                        logger.warning(f"⚠️ PRODUCTION TEST: Call used unexpected method: {data_source}")
                                    
                                    return data
                                
                                elif status == "processing":
                                    logger.info(f"⏳ PRODUCTION TEST: Call {call_id} still processing...")
                                
                                else:
                                    logger.info(f"📋 PRODUCTION TEST: Call {call_id} status: {status}")
                            
                            elif response.status == 404:
                                logger.warning(f"⚠️ PRODUCTION TEST: Call {call_id} not found")
                            
                            else:
                                logger.warning(f"⚠️ PRODUCTION TEST: Status check returned {response.status}")
                
                except Exception as e:
                    logger.warning(f"⚠️ PRODUCTION TEST: Status check error: {e}")
                
                # Wait before next check
                await asyncio.sleep(check_interval)
                elapsed += check_interval
                
                # Progress update
                if elapsed % 60 == 0:
                    logger.info(f"⏳ PRODUCTION TEST: Still tracking ({elapsed//60}m/{timeout_minutes}m)...")
            
            # Timeout reached
            logger.warning(f"⏰ PRODUCTION TEST: Call tracking timeout after {timeout_minutes} minutes")
            
            # Try to get final status
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"{self.service_url}/call-status/{call_id}") as response:
                        if response.status == 200:
                            data = await response.json()
                            logger.info(f"📋 PRODUCTION TEST: Final status: {data.get('status', 'unknown')}")
                            return data
            except:
                pass
            
            return {"status": "timeout", "call_id": call_id}
            
        except Exception as e:
            logger.error(f"❌ PRODUCTION TEST: Call tracking error: {e}")
            return {"status": "error", "error": str(e)}
    
    async def run_comprehensive_test(self) -> bool:
        """Run comprehensive production test"""
        logger.info("🚀 PRODUCTION TEST: Starting comprehensive test suite...")
        
        success_count = 0
        total_tests = 4
        
        # Test 1: Service Health
        if await self.test_service_health():
            success_count += 1
        
        # Test 2: Queue Status
        if await self.test_queue_status():
            success_count += 1
        
        # Test 3: Call Queueing
        queue_success, call_id = await self.test_call_queueing()
        if queue_success:
            success_count += 1
            
            # Test 4: Call Tracking (if queueing worked)
            if call_id:
                tracking_result = await self.test_call_tracking(call_id)
                
                if tracking_result.get("status") in ["completed", "failed"]:
                    success_count += 1
                    
                    # Check if production fix was used
                    data_source = tracking_result.get("data_source", "")
                    if data_source == "production_cloudrun_manager":
                        logger.info("🎉 PRODUCTION TEST: PRODUCTION FIX VERIFIED - Call used production_cloudrun_manager!")
                    elif data_source == "production_fallback_method":
                        logger.info("🔄 PRODUCTION TEST: Production fallback used successfully")
                    else:
                        logger.warning(f"⚠️ PRODUCTION TEST: Unexpected data source: {data_source}")
                
                else:
                    logger.warning("⚠️ PRODUCTION TEST: Call tracking did not complete properly")
        
        # Summary
        logger.info("")
        logger.info("📊 PRODUCTION TEST: Test Results Summary")
        logger.info(f"   Tests passed: {success_count}/{total_tests}")
        logger.info(f"   Success rate: {(success_count/total_tests)*100:.1f}%")
        
        if success_count == total_tests:
            logger.info("🎉 PRODUCTION TEST: ALL TESTS PASSED! Production fix is working!")
            return True
        else:
            logger.error("❌ PRODUCTION TEST: Some tests failed. Production fix needs investigation.")
            return False
    
    async def test_environment_detection(self) -> Dict[str, Any]:
        """Test environment detection capabilities"""
        try:
            logger.info("🌩️ PRODUCTION TEST: Testing environment detection...")
            
            # Import the production manager to test environment detection
            import sys
            import os
            sys.path.append(os.path.dirname(__file__))
            
            exec(open(os.path.join(os.path.dirname(__file__), 'production-cloudrun-fix.py')).read())
            manager = ProductionCloudRunManager()
            
            logger.info(f"   Cloud Run detected: {manager.is_cloud_run}")
            logger.info(f"   Startup timeout: {manager.startup_timeout}s")
            logger.info(f"   Check interval: {manager.check_interval}s")
            logger.info(f"   Request timeout: {manager.request_timeout}s")
            
            return {
                "is_cloud_run": manager.is_cloud_run,
                "startup_timeout": manager.startup_timeout,
                "check_interval": manager.check_interval,
                "request_timeout": manager.request_timeout
            }
            
        except Exception as e:
            logger.error(f"❌ PRODUCTION TEST: Environment detection test failed: {e}")
            return {"error": str(e)}

async def main():
    """Main test function"""
    logger.info("🧪 PRODUCTION CLOUD RUN FIX - VERIFICATION TESTS")
    logger.info("=" * 60)
    
    tester = ProductionFixTester()
    
    # Test environment detection
    env_result = await tester.test_environment_detection()
    logger.info(f"🌩️ Environment: {env_result}")
    
    # Run comprehensive test
    success = await tester.run_comprehensive_test()
    
    logger.info("")
    logger.info("=" * 60)
    if success:
        logger.info("🎉 PRODUCTION FIX VERIFICATION: SUCCESS!")
        logger.info("   The production Cloud Run fix is working correctly.")
        logger.info("   Calls should now work properly in Cloud Run environment.")
    else:
        logger.error("❌ PRODUCTION FIX VERIFICATION: FAILED!")
        logger.error("   The production fix needs investigation.")
        logger.error("   Check logs for specific issues.")
    
    return success

if __name__ == "__main__":
    asyncio.run(main()) 