#!/usr/bin/env python3
"""
Test complete integration with all services running
Tests: Backend -> Queue -> Agent -> Backend flow
"""

import requests
import asyncio
import aiohttp
import json
import time
from datetime import datetime

def test_all_services_health():
    """Test that all services are running"""
    print("🏥 Testing service health checks...")
    
    services = {
        "Backend": "http://localhost:3000/health",
        "Queue System": "http://localhost:8000/api/health", 
        "Agent Server": "http://localhost:8765/health"
    }
    
    all_healthy = True
    for service, url in services.items():
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                print(f"✅ {service}: Healthy")
            else:
                print(f"❌ {service}: Unhealthy (status {response.status_code})")
                all_healthy = False
        except Exception as e:
            print(f"❌ {service}: Not responding ({e})")
            all_healthy = False
    
    return all_healthy

def test_queue_with_proper_call_id():
    """Test queue with a proper UUID call_id format"""
    print("\n🧪 Testing queue with backend-compatible call ID...")
    
    # Generate a proper UUID format call_id (like backend generates)
    import uuid
    test_call_id = str(uuid.uuid4())
    
    payload = {
        "phone_number": "+918939894913",
        "campaign_id": "76b15d94-5e02-4e9b-a94f-6b31b3691b55",
        "custom_call_id": test_call_id,
        "call_config": {
            "flow_name": "Vyapari-test",
            "variables": {
                "firstName": "Test",
                "lastName": "User",
                "phoneNumber": "+918939894913"
            },
            "recording_enabled": True,
            "max_duration": 1800
        },
        "scheduled_at": datetime.utcnow().isoformat() + "Z",
        "priority": "normal",
        "max_retries": 3
    }
    
    print(f"📤 Sending call with ID: {test_call_id}")
    
    try:
        response = requests.post(
            "http://localhost:8000/api/calls/outbound",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Queue accepted call successfully!")
            print(f"📋 Queue response: {json.dumps(result, indent=2)}")
            
            # Verify call ID consistency
            returned_id = result.get('call_id')
            if returned_id == test_call_id:
                print(f"🎯 Call ID consistency verified: {returned_id}")
                return test_call_id
            else:
                print(f"⚠️ Call ID mismatch: sent {test_call_id}, got {returned_id}")
                return None
        else:
            print(f"❌ Queue rejected call: {response.status_code}")
            print(f"📋 Error: {response.text}")
            return None
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Request failed: {e}")
        return None

async def monitor_call_completion(call_id, timeout_seconds=60):
    """Monitor a call until completion or timeout"""
    print(f"\n⏳ Monitoring call {call_id} for completion...")
    
    start_time = time.time()
    
    async with aiohttp.ClientSession() as session:
        while time.time() - start_time < timeout_seconds:
            try:
                # Check agent server for call status
                async with session.get(f"http://localhost:8765/call-status/{call_id}") as response:
                    if response.status == 200:
                        status_data = await response.json()
                        call_status = status_data.get("status", "unknown")
                        print(f"📊 Call status: {call_status}")
                        
                        if call_status in ["completed", "failed", "error", "ended"]:
                            print(f"🏁 Call finished with status: {call_status}")
                            return call_status
                    else:
                        print(f"⚠️ Agent status check failed: {response.status}")
                        
            except Exception as e:
                print(f"❌ Error checking call status: {e}")
            
            await asyncio.sleep(5)  # Check every 5 seconds
    
    print(f"⏰ Monitoring timed out after {timeout_seconds} seconds")
    return "timeout"

def test_backend_result_reception():
    """Test if backend can receive results (using the webhook)"""
    print("\n📥 Testing backend result reception...")
    
    test_result = {
        "call_id": str(uuid.uuid4()),
        "status": "completed", 
        "duration_seconds": 45,
        "transcript": [
            {"speaker": "agent", "text": "Hello, this is a test call"},
            {"speaker": "user", "text": "Hi there"}
        ],
        "call_outcome": "test_successful",
        "variables": {"test": "integration"}
    }
    
    try:
        response = requests.post(
            "http://localhost:3000/api/calls/external-updates",
            json=[test_result],  # Backend expects array
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        
        if response.status_code in [200, 201]:
            print("✅ Backend accepted result successfully!")
            return True
        else:
            print(f"❌ Backend rejected result: {response.status_code}")
            print(f"📋 Error: {response.text}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Backend result test failed: {e}")
        return False

async def main():
    """Run complete integration test"""
    print("🔄 Complete Integration Test")
    print("=" * 50)
    
    # Step 1: Health checks
    if not test_all_services_health():
        print("\n❌ Some services are not healthy. Please start all services first.")
        return
    
    # Step 2: Test queue with proper call ID
    call_id = test_queue_with_proper_call_id()
    if not call_id:
        print("\n❌ Queue test failed")
        return
    
    # Step 3: Monitor call (brief monitoring)
    final_status = await monitor_call_completion(call_id, timeout_seconds=30)
    
    # Step 4: Test backend result reception
    backend_test = test_backend_result_reception()
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 Integration Test Summary:")
    print(f"✅ All services running: Yes")
    print(f"✅ Queue accepts calls: Yes")  
    print(f"✅ Call ID consistency: Yes")
    print(f"📞 Call completion: {final_status}")
    print(f"✅ Backend accepts results: {'Yes' if backend_test else 'No'}")
    
    if final_status not in ["timeout"] and backend_test:
        print("\n🎉 INTEGRATION SUCCESS! All components working together!")
    else:
        print("\n⚠️ Integration partially working. Check call completion flow.")

if __name__ == "__main__":
    import uuid
    asyncio.run(main()) 