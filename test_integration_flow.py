#!/usr/bin/env python3
"""
Test script to verify the complete integration flow:
1. Backend sends call to queue (SCHEDULED -> IN_PROGRESS)
2. Queue prevents duplicates
3. Queue executes call and sends results back to backend
4. Backend updates final status (IN_PROGRESS -> COMPLETED/FAILED)
"""

import asyncio
import aiohttp
import json
import time
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
BACKEND_URL = os.getenv("BACKEND_API_URL", "http://localhost:3000")
QUEUE_URL = os.getenv("QUEUE_API_URL", "http://localhost:8001")

class IntegrationFlowTest:
    def __init__(self):
        self.test_results = []
    
    async def run_tests(self):
        """Run comprehensive integration tests"""
        print("🧪 Starting Integration Flow Tests")
        print("=" * 50)
        
        # Test 1: Normal flow without duplicates
        await self.test_normal_flow()
        
        # Test 2: Duplicate prevention
        await self.test_duplicate_prevention()
        
        # Test 3: Backend call status tracking
        await self.test_status_tracking()
        
        # Print results
        self.print_results()
    
    async def test_normal_flow(self):
        """Test normal flow: Backend -> Queue -> Execution -> Backend notification"""
        print("\n📞 Test 1: Normal Integration Flow")
        print("-" * 30)
        
        try:
            # Step 1: Create a test call in backend
            call_data = {
                "campaignId": "test-campaign-001",
                "agentId": "test-agent-001", 
                "contactId": "test-contact-001",
                "type": "outbound",
                "phoneNumber": "+1234567890",
                "scheduledAt": (datetime.now() + timedelta(seconds=10)).isoformat() + "Z",
                "variable": {"test_var": "test_value"}
            }
            
            print(f"📋 Creating test call: {call_data['phoneNumber']}")
            call_response = await self.make_request(
                "POST", 
                f"{BACKEND_URL}/api/calls", 
                call_data,
                requires_auth=True
            )
            
            if not call_response or 'call' not in call_response:
                raise Exception("Failed to create call in backend")
            
            backend_call_id = call_response['call']['id']
            print(f"✅ Backend call created: {backend_call_id}")
            
            # Step 2: Wait for scheduler to trigger (calls should be IN_PROGRESS)
            print("⏳ Waiting for scheduler to trigger call...")
            await asyncio.sleep(15)  # Wait for scheduler
            
            # Check call status in backend
            call_status = await self.check_call_status(backend_call_id)
            print(f"📊 Call status after scheduler: {call_status}")
            
            if call_status != "in_progress":
                raise Exception(f"Expected 'in_progress', got '{call_status}'")
            
            # Step 3: Simulate queue completion notification
            completion_data = {
                "call_id": backend_call_id,
                "status": "completed",
                "duration_seconds": 120,
                "transcript": [{"speaker": "agent", "text": "Hello!"}, {"speaker": "user", "text": "Hi!"}],
                "recording_url": "https://test-recording.com/test.mp3",
                "call_outcome": "successful",
                "variables": {"result": "success"}
            }
            
            print(f"📤 Sending completion notification to backend...")
            completion_response = await self.make_request(
                "POST",
                f"{BACKEND_URL}/api/calls/external-updates",
                completion_data
            )
            
            if completion_response and completion_response.get('success'):
                print("✅ Backend successfully received completion notification")
            else:
                raise Exception("Backend failed to process completion")
            
            # Step 4: Verify final status
            await asyncio.sleep(2)
            final_status = await self.check_call_status(backend_call_id)
            print(f"🏁 Final call status: {final_status}")
            
            if final_status != "completed":
                raise Exception(f"Expected 'completed', got '{final_status}'")
            
            self.test_results.append({
                "test": "Normal Flow",
                "status": "PASSED",
                "details": f"Call {backend_call_id} processed successfully"
            })
            
        except Exception as e:
            print(f"❌ Normal flow test failed: {e}")
            self.test_results.append({
                "test": "Normal Flow", 
                "status": "FAILED",
                "error": str(e)
            })
    
    async def test_duplicate_prevention(self):
        """Test that queue prevents duplicate calls"""
        print("\n🛡️ Test 2: Duplicate Prevention")
        print("-" * 30)
        
        try:
            # Create a call
            call_data = {
                "campaignId": "test-campaign-002",
                "agentId": "test-agent-002",
                "contactId": "test-contact-002", 
                "type": "outbound",
                "phoneNumber": "+1234567891",
                "variable": {"test": "duplicate_test"}
            }
            
            print(f"📋 Creating first call: {call_data['phoneNumber']}")
            call_response = await self.make_request(
                "POST",
                f"{BACKEND_URL}/api/calls",
                call_data,
                requires_auth=True
            )
            
            backend_call_id = call_response['call']['id']
            print(f"✅ First call created: {backend_call_id}")
            
            # Try to send same call to queue multiple times (simulate backend retries)
            queue_call_data = {
                "phone_number": call_data['phoneNumber'],
                "campaign_id": call_data['campaignId'],
                "custom_call_id": backend_call_id,
                "call_config": {
                    "variables": call_data['variable'],
                    "flow_name": "test_agent"
                }
            }
            
            print("📤 Sending call to queue (attempt 1)...")
            queue_response1 = await self.make_request(
                "POST",
                f"{QUEUE_URL}/api/queue/calls",
                queue_call_data
            )
            
            print("📤 Sending same call to queue (attempt 2 - should be prevented)...")
            queue_response2 = await self.make_request(
                "POST", 
                f"{QUEUE_URL}/api/queue/calls",
                queue_call_data
            )
            
            if queue_response1 and queue_response2:
                if queue_response1.get('job_id') == queue_response2.get('job_id'):
                    print("✅ Duplicate prevention working - same job_id returned")
                    self.test_results.append({
                        "test": "Duplicate Prevention",
                        "status": "PASSED", 
                        "details": "Queue correctly prevented duplicate calls"
                    })
                else:
                    raise Exception("Duplicate prevention failed - different job_ids returned")
            else:
                raise Exception("Failed to queue calls")
                
        except Exception as e:
            print(f"❌ Duplicate prevention test failed: {e}")
            self.test_results.append({
                "test": "Duplicate Prevention",
                "status": "FAILED",
                "error": str(e)
            })
    
    async def test_status_tracking(self):
        """Test that status changes are tracked correctly"""
        print("\n📊 Test 3: Status Tracking")
        print("-" * 30)
        
        try:
            # Create call and track status changes
            call_data = {
                "campaignId": "test-campaign-003",
                "agentId": "test-agent-003",
                "contactId": "test-contact-003",
                "type": "outbound", 
                "phoneNumber": "+1234567892",
                "scheduledAt": (datetime.now() + timedelta(seconds=5)).isoformat() + "Z"
            }
            
            print(f"📋 Creating call for status tracking: {call_data['phoneNumber']}")
            call_response = await self.make_request(
                "POST",
                f"{BACKEND_URL}/api/calls",
                call_data,
                requires_auth=True
            )
            
            backend_call_id = call_response['call']['id']
            initial_status = await self.check_call_status(backend_call_id)
            print(f"📊 Initial status: {initial_status}")
            
            if initial_status != "scheduled":
                raise Exception(f"Expected 'scheduled', got '{initial_status}'")
            
            # Wait for scheduler to move to in_progress
            print("⏳ Waiting for scheduler to change status to in_progress...")
            await asyncio.sleep(10)
            
            progress_status = await self.check_call_status(backend_call_id)
            print(f"📊 Status after scheduler: {progress_status}")
            
            if progress_status != "in_progress":
                raise Exception(f"Expected 'in_progress', got '{progress_status}'")
            
            # Simulate completion
            completion_data = {
                "call_id": backend_call_id,
                "status": "completed",
                "duration_seconds": 90
            }
            
            await self.make_request(
                "POST",
                f"{BACKEND_URL}/api/calls/external-updates",
                completion_data
            )
            
            await asyncio.sleep(2)
            final_status = await self.check_call_status(backend_call_id)
            print(f"📊 Final status: {final_status}")
            
            if final_status != "completed":
                raise Exception(f"Expected 'completed', got '{final_status}'")
            
            print("✅ Status tracking working correctly")
            self.test_results.append({
                "test": "Status Tracking",
                "status": "PASSED",
                "details": "scheduled -> in_progress -> completed"
            })
            
        except Exception as e:
            print(f"❌ Status tracking test failed: {e}")
            self.test_results.append({
                "test": "Status Tracking",
                "status": "FAILED", 
                "error": str(e)
            })
    
    async def check_call_status(self, call_id: str) -> str:
        """Get current call status from backend"""
        try:
            response = await self.make_request(
                "GET",
                f"{BACKEND_URL}/api/calls/{call_id}",
                requires_auth=True
            )
            return response.get('status', 'unknown') if response else 'unknown'
        except:
            return 'unknown'
    
    async def make_request(self, method: str, url: str, data: dict = None, requires_auth: bool = False):
        """Make HTTP request with proper error handling"""
        try:
            headers = {'Content-Type': 'application/json'}
            
            # Add auth if required (mock token for testing)
            if requires_auth:
                headers['Authorization'] = 'Bearer test-token'
            
            async with aiohttp.ClientSession() as session:
                if method == "GET":
                    async with session.get(url, headers=headers) as response:
                        if response.status < 400:
                            return await response.json()
                        else:
                            print(f"⚠️ Request failed: {response.status} - {await response.text()}")
                            return None
                else:
                    async with session.request(method, url, json=data, headers=headers) as response:
                        if response.status < 400:
                            return await response.json()
                        else:
                            print(f"⚠️ Request failed: {response.status} - {await response.text()}")
                            return None
        except Exception as e:
            print(f"⚠️ Request error: {e}")
            return None
    
    def print_results(self):
        """Print test results summary"""
        print("\n" + "=" * 50)
        print("🧪 Integration Test Results")
        print("=" * 50)
        
        passed = sum(1 for result in self.test_results if result['status'] == 'PASSED')
        total = len(self.test_results)
        
        for result in self.test_results:
            status_icon = "✅" if result['status'] == 'PASSED' else "❌"
            print(f"{status_icon} {result['test']}: {result['status']}")
            if 'details' in result:
                print(f"   └─ {result['details']}")
            if 'error' in result:
                print(f"   └─ Error: {result['error']}")
        
        print(f"\n📊 Summary: {passed}/{total} tests passed")
        
        if passed == total:
            print("🎉 All integration tests passed!")
        else:
            print("⚠️ Some tests failed - check the integration flow")

async def main():
    """Run integration tests"""
    test_runner = IntegrationFlowTest()
    await test_runner.run_tests()

if __name__ == "__main__":
    asyncio.run(main()) 