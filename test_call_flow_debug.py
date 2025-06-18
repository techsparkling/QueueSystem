#!/usr/bin/env python3
"""
Debug script to test the call flow and identify where it's failing
"""

import asyncio
import aiohttp
import json
import os
from datetime import datetime

async def test_agent_server_connection():
    """Test if agent server is running and responsive"""
    agent_server_url = os.getenv("AGENT_SERVER_URL", "http://localhost:8080")
    
    print(f"🔍 Testing agent server at: {agent_server_url}")
    
    try:
        async with aiohttp.ClientSession() as session:
            # Test health endpoint
            try:
                async with session.get(f"{agent_server_url}/health", timeout=aiohttp.ClientTimeout(total=5)) as response:
                    if response.status == 200:
                        print("✅ Agent server health check passed")
                    else:
                        print(f"⚠️ Agent server health check returned: {response.status}")
            except Exception as e:
                print(f"❌ Agent server health check failed: {e}")
            
            # Test call status endpoint with a dummy call
            test_call_id = "test-call-123"
            try:
                async with session.get(f"{agent_server_url}/call-status/{test_call_id}", timeout=aiohttp.ClientTimeout(total=5)) as response:
                    result = await response.text()
                    print(f"📋 Call status endpoint test ({response.status}): {result[:100]}...")
            except Exception as e:
                print(f"❌ Call status endpoint test failed: {e}")
                
    except Exception as e:
        print(f"❌ Failed to connect to agent server: {e}")

async def test_queue_call_simulation():
    """Simulate what happens when queue tries to start a call"""
    print("\n🧪 Testing queue call simulation...")
    
    # Simulate the exact flow that queue system does
    test_call_id = f"queue-debug-{int(datetime.now().timestamp())}"
    phone_number = "+1234567890"
    campaign_id = "test-campaign"
    
    config = {
        "backend_call_id": test_call_id,
        "queue_job_id": f"queue-{test_call_id}",
        "phone_number": phone_number,
        "campaign_id": campaign_id,
        "flow_name": "test-flow",
        "variables": {"test": "debug"}
    }
    
    agent_server_url = os.getenv("AGENT_SERVER_URL", "http://localhost:8080")
    
    print(f"📤 Simulating call notification to agent server...")
    print(f"   Call ID: {test_call_id}")
    print(f"   Phone: {phone_number}")
    print(f"   Config: {json.dumps(config, indent=2)}")
    
    try:
        async with aiohttp.ClientSession() as session:
            # Step 1: Notify agent server about call
            payload = {
                "call_id": test_call_id,
                "plivo_call_uuid": f"plivo-{test_call_id}",
                "phone_number": phone_number,
                "campaign_id": campaign_id,
                "workflow_id": f"queue-{test_call_id}",
                "config": config,
                "flow_name": config.get('flow_name', 'test-flow'),
                "variables": config.get('variables', {}),
                "queue_call_id": test_call_id,
                "data_source": "debug_test"
            }
            
            async with session.post(f"{agent_server_url}/start-call", json=payload, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    result = await response.json()
                    print(f"✅ Agent server accepted call notification")
                    print(f"📋 Response: {json.dumps(result, indent=2)}")
                else:
                    error_text = await response.text()
                    print(f"❌ Agent server rejected call notification ({response.status}): {error_text}")
                    return
            
            # Step 2: Monitor call status
            print(f"\n⏱️ Monitoring call status for 30 seconds...")
            for i in range(6):  # Check 6 times over 30 seconds
                await asyncio.sleep(5)
                
                try:
                    async with session.get(f"{agent_server_url}/call-status/{test_call_id}", timeout=aiohttp.ClientTimeout(total=5)) as response:
                        if response.status == 200:
                            status = await response.json()
                            call_status = status.get("status", "unknown")
                            print(f"📊 Status check {i+1}: {call_status}")
                            
                            if call_status in ["completed", "failed", "error", "ended"]:
                                print(f"🏁 Call finished with status: {call_status}")
                                print(f"📋 Final result: {json.dumps(status, indent=2)}")
                                break
                        else:
                            print(f"⚠️ Status check {i+1} failed: HTTP {response.status}")
                except Exception as e:
                    print(f"❌ Status check {i+1} error: {e}")
            
    except Exception as e:
        print(f"❌ Call simulation failed: {e}")

async def test_backend_notification():
    """Test backend notification endpoint"""
    print("\n📤 Testing backend notification...")
    
    backend_url = os.getenv("BACKEND_API_URL", "http://localhost:3000")
    
    test_payload = {
        "call_id": "test-backend-notification",
        "status": "completed",
        "duration_seconds": 120,
        "transcript": [{"speaker": "agent", "text": "Test"}],
        "call_outcome": "test"
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{backend_url}/api/calls/external-updates", json=test_payload, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status in [200, 201]:
                    result = await response.json()
                    print(f"✅ Backend notification accepted")
                    print(f"📋 Response: {json.dumps(result, indent=2)}")
                else:
                    error_text = await response.text()
                    print(f"❌ Backend notification failed ({response.status}): {error_text}")
    except Exception as e:
        print(f"❌ Backend notification error: {e}")

async def main():
    """Run all diagnostic tests"""
    print("🔍 Call Flow Diagnostic Tool")
    print("=" * 50)
    
    # Test 1: Agent server connection
    await test_agent_server_connection()
    
    # Test 2: Simulate queue call flow
    await test_queue_call_simulation()
    
    # Test 3: Test backend notification
    await test_backend_notification()
    
    print("\n" + "=" * 50)
    print("🏁 Diagnostic completed")
    print("\nKey findings:")
    print("- If agent server is not responding: Start PipecatPlivoOutbound system")
    print("- If calls immediately fail: Check agent server configuration") 
    print("- If backend notifications fail: Check backend authentication")

if __name__ == "__main__":
    asyncio.run(main()) 