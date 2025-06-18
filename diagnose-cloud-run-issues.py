#!/usr/bin/env python3
"""
Cloud Run Call Tracking Diagnostic Tool
Run this to identify why calls are immediately marked as failed in Cloud Run
"""

import asyncio
import aiohttp
import json
import os
import logging
from datetime import datetime

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class CloudRunDiagnostic:
    def __init__(self):
        self.queue_service_url = os.getenv("QUEUE_SERVICE_URL", "")
        self.agent_service_url = os.getenv("AGENT_SERVICE_URL", "")
        self.backend_service_url = os.getenv("BACKEND_URL", "")
        
        # Test URLs (replace with your actual URLs)
        if not self.queue_service_url:
            self.queue_service_url = input("Enter Queue Service URL (e.g., https://queue-system-xxx.run.app): ").strip()
        if not self.agent_service_url:
            self.agent_service_url = input("Enter Agent Service URL (e.g., https://pipecat-agent-xxx.run.app): ").strip()
        if not self.backend_service_url:
            self.backend_service_url = input("Enter Backend Service URL (e.g., https://backend-xxx.run.app): ").strip()
    
    async def test_service_health(self, service_name: str, url: str):
        """Test if a service is healthy and responsive"""
        logger.info(f"🔍 Testing {service_name} health: {url}")
        
        try:
            async with aiohttp.ClientSession() as session:
                health_url = f"{url}/health"
                
                start_time = datetime.now()
                async with session.get(health_url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    end_time = datetime.now()
                    response_time = (end_time - start_time).total_seconds()
                    
                    if response.status == 200:
                        result = await response.json()
                        logger.info(f"✅ {service_name} is healthy (Response time: {response_time:.2f}s)")
                        return True, response_time, result
                    else:
                        logger.error(f"❌ {service_name} returned status {response.status}")
                        return False, response_time, {"error": f"HTTP {response.status}"}
        except asyncio.TimeoutError:
            logger.error(f"⏰ {service_name} health check timed out (>30s)")
            return False, 30.0, {"error": "Timeout"}
        except Exception as e:
            logger.error(f"❌ {service_name} health check failed: {e}")
            return False, 0, {"error": str(e)}
    
    async def test_service_communication(self):
        """Test communication between queue and agent services"""
        logger.info("🔗 Testing service-to-service communication...")
        
        # Simulate the queue checking agent status
        test_call_id = f"test-{int(datetime.now().timestamp())}"
        
        try:
            async with aiohttp.ClientSession() as session:
                # Test the exact endpoint that queue system uses
                status_url = f"{self.agent_service_url}/call-status/{test_call_id}"
                
                logger.info(f"📞 Testing status check: {status_url}")
                
                headers = {
                    "User-Agent": "CloudRunQueueSystem/1.0",
                    "Accept": "application/json",
                    "X-Source": "diagnostic-tool"
                }
                
                start_time = datetime.now()
                async with session.get(status_url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    end_time = datetime.now()
                    response_time = (end_time - start_time).total_seconds()
                    
                    logger.info(f"📋 Status check response: {response.status} (Time: {response_time:.2f}s)")
                    
                    if response.status == 404:
                        logger.info("✅ Agent service correctly returns 404 for non-existent call")
                        return True, response_time
                    elif response.status == 200:
                        result = await response.json()
                        logger.info(f"📊 Unexpected 200 response: {result}")
                        return True, response_time
                    else:
                        logger.error(f"❌ Unexpected status code: {response.status}")
                        return False, response_time
                        
        except asyncio.TimeoutError:
            logger.error("⏰ Service communication timed out")
            return False, 30.0
        except Exception as e:
            logger.error(f"❌ Service communication failed: {e}")
            return False, 0
    
    async def test_call_registration_timing(self):
        """Test the timing of call registration in agent service"""
        logger.info("⏱️ Testing call registration timing simulation...")
        
        # Simulate what happens when queue initiates a call
        test_call_id = f"timing-test-{int(datetime.now().timestamp())}"
        
        # Test immediate status check (what queue does now)
        logger.info("📞 Testing immediate status check (current queue behavior)...")
        
        try:
            async with aiohttp.ClientSession() as session:
                status_url = f"{self.agent_service_url}/call-status/{test_call_id}"
                
                # Immediate check
                async with session.get(status_url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    logger.info(f"📋 Immediate check result: {response.status}")
                    if response.status == 404:
                        logger.info("✅ As expected - call not found immediately")
                    
                # Check after delays to see optimal timing
                for delay in [5, 10, 15, 20]:
                    logger.info(f"⏳ Waiting {delay}s then checking status...")
                    await asyncio.sleep(delay)
                    
                    async with session.get(status_url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                        logger.info(f"📋 After {delay}s delay: {response.status}")
                        
                        if response.status == 404:
                            logger.info(f"   Call still not registered after {delay}s")
                        else:
                            logger.info(f"   Call would be found after {delay}s delay")
                            
        except Exception as e:
            logger.error(f"❌ Timing test failed: {e}")
    
    async def check_environment_variables(self):
        """Check if environment variables are properly configured"""
        logger.info("🔧 Checking environment configuration...")
        
        required_vars = {
            "CLOUD_RUN_OPTIMIZED": "Should be 'true' for Cloud Run",
            "STATUS_CHECK_INTERVAL": "Should be 15+ seconds for Cloud Run",
            "INITIAL_STATUS_DELAY": "Should be 15+ seconds for Cloud Run",
            "REQUEST_TIMEOUT": "Should be 30+ seconds for Cloud Run",
            "MAX_STATUS_RETRIES": "Should be 3+ for Cloud Run"
        }
        
        issues = []
        
        for var, description in required_vars.items():
            value = os.getenv(var)
            if value:
                logger.info(f"✅ {var}={value} ({description})")
                
                # Check specific values
                if var == "CLOUD_RUN_OPTIMIZED" and value.lower() != "true":
                    issues.append(f"{var} should be 'true' for Cloud Run deployment")
                elif var == "STATUS_CHECK_INTERVAL" and int(value) < 15:
                    issues.append(f"{var} should be 15+ seconds for Cloud Run (current: {value})")
                elif var == "INITIAL_STATUS_DELAY" and int(value) < 15:
                    issues.append(f"{var} should be 15+ seconds for Cloud Run (current: {value})")
                elif var == "REQUEST_TIMEOUT" and int(value) < 30:
                    issues.append(f"{var} should be 30+ seconds for Cloud Run (current: {value})")
                elif var == "MAX_STATUS_RETRIES" and int(value) < 3:
                    issues.append(f"{var} should be 3+ for Cloud Run (current: {value})")
            else:
                logger.warning(f"⚠️ {var} not set ({description})")
                issues.append(f"{var} not configured")
        
        return issues
    
    async def simulate_call_flow(self):
        """Simulate the complete call flow to identify failure points"""
        logger.info("🎯 Simulating complete call flow...")
        
        # This simulates what the queue system does
        steps = [
            "1. Queue initiates Plivo call",
            "2. Queue immediately checks agent status",
            "3. Queue polls agent status every 10-15s",
            "4. Queue waits for completion or timeout"
        ]
        
        for i, step in enumerate(steps, 1):
            logger.info(f"📋 Step {i}: {step}")
            
            if i == 2:
                # This is where the issue occurs
                logger.warning("⚠️ ISSUE POINT: Agent service hasn't registered call yet")
                logger.warning("   Queue gets 404/unknown status and may mark as failed")
                
            elif i == 3:
                logger.info("💡 FIX: Need longer delays and retry logic")
    
    async def run_full_diagnostic(self):
        """Run complete diagnostic suite"""
        logger.info("🚀 Starting Cloud Run call tracking diagnostic...")
        logger.info("=" * 60)
        
        # Test 1: Service Health
        logger.info("\n📊 TEST 1: Service Health Checks")
        logger.info("-" * 30)
        
        queue_healthy, queue_time, queue_result = await self.test_service_health("Queue Service", self.queue_service_url)
        agent_healthy, agent_time, agent_result = await self.test_service_health("Agent Service", self.agent_service_url)
        backend_healthy, backend_time, backend_result = await self.test_service_health("Backend Service", self.backend_service_url)
        
        # Test 2: Service Communication
        logger.info("\n🔗 TEST 2: Service Communication")
        logger.info("-" * 30)
        
        comm_working, comm_time = await self.test_service_communication()
        
        # Test 3: Call Registration Timing
        logger.info("\n⏱️ TEST 3: Call Registration Timing")
        logger.info("-" * 30)
        
        await self.test_call_registration_timing()
        
        # Test 4: Environment Configuration
        logger.info("\n🔧 TEST 4: Environment Configuration")
        logger.info("-" * 30)
        
        env_issues = await self.check_environment_variables()
        
        # Test 5: Call Flow Simulation
        logger.info("\n🎯 TEST 5: Call Flow Simulation")
        logger.info("-" * 30)
        
        await self.simulate_call_flow()
        
        # Summary and Recommendations
        logger.info("\n" + "=" * 60)
        logger.info("📋 DIAGNOSTIC SUMMARY")
        logger.info("=" * 60)
        
        issues_found = []
        
        if not queue_healthy:
            issues_found.append("Queue service is not healthy")
        if not agent_healthy:
            issues_found.append("Agent service is not healthy")
        if not backend_healthy:
            issues_found.append("Backend service is not healthy")
        if not comm_working:
            issues_found.append("Service-to-service communication failing")
        if env_issues:
            issues_found.extend(env_issues)
        
        if queue_time > 5 or agent_time > 5 or comm_time > 5:
            issues_found.append("Slow response times between services")
        
        if issues_found:
            logger.error("❌ Issues found:")
            for issue in issues_found:
                logger.error(f"   • {issue}")
        else:
            logger.info("✅ No major issues detected")
        
        # Recommendations
        logger.info("\n💡 RECOMMENDATIONS:")
        logger.info("1. Update CallQueueSystem with Cloud Run optimizations")
        logger.info("2. Set CLOUD_RUN_OPTIMIZED=true in environment")
        logger.info("3. Increase status check intervals to 15+ seconds")
        logger.info("4. Add 20+ second initial delay before status checks")
        logger.info("5. Enable retry logic with exponential backoff")
        logger.info("6. Use the fixed deployment script: deploy-to-cloudrun-fixed.sh")
        
        return len(issues_found) == 0

async def main():
    """Main diagnostic function"""
    diagnostic = CloudRunDiagnostic()
    
    try:
        success = await diagnostic.run_full_diagnostic()
        
        if success:
            logger.info("\n🎉 Diagnostic completed - ready for fixed deployment!")
            return 0
        else:
            logger.error("\n💥 Issues found - apply recommended fixes")
            return 1
            
    except Exception as e:
        logger.error(f"❌ Diagnostic failed: {e}")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main()) 