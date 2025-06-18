#!/usr/bin/env python3
"""
Test Complete Call Flow - Verify call_id tracking and variable passing
Tests the entire flow: Backend -> Queue -> Plivo -> Voice Bot -> Backend
"""

import asyncio
import aiohttp
import json
import time
from datetime import datetime

# Test configuration
QUEUE_API_URL = "http://localhost:8001"
BACKEND_API_URL = "http://35.200.234.200:3000"
VOICE_BOT_URL = "http://localhost:8765"

async def test_complete_flow():
    """Test the complete call flow with proper tracking"""
    
    print("🧪 Testing Complete Call Flow")
    print("=" * 50)
    
    # Test data
    backend_call_id = f"test-backend-{int(time.time())}"
    test_phone = "+919123456789"
    test_campaign = "test-campaign"
    test_variables = {
        "name": "John Doe",
        "email": "john@example.com",
        "loan_amount": "50000",
        "purpose": "home renovation"
    }
    
    print(f"📋 Test Call ID: {backend_call_id}")
    print(f"📞 Phone: {test_phone}")
    print(f"📊 Variables: {test_variables}")
    print()
    
    try:
        # Step 1: Queue the call (simulating backend request)
        print("1️⃣ Queuing call via CallQueueSystem...")
        
        queue_payload = {
            "phone_number": test_phone,
            "campaign_id": test_campaign,
            "custom_call_id": backend_call_id,  # This is the backend's call_id
            "call_config": {
                "flow_name": "wishfin-test",
                "variables": test_variables,
                "recording_enabled": True,
                "max_duration": 300
            },
            "priority": "high",
            "max_retries": 1
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{QUEUE_API_URL}/api/calls/outbound", json=queue_payload) as response:
                if response.status == 200:
                    queue_result = await response.json()
                    print(f"✅ Call queued successfully: {queue_result}")
                    print(f"📋 Returned call_id: {queue_result.get('call_id')}")
                else:
                    error_text = await response.text()
                    print(f"❌ Failed to queue call: {error_text}")
                    return
        
        print()
        
        # Step 2: Check queue status
        print("2️⃣ Checking queue status...")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{QUEUE_API_URL}/api/queue/status") as response:
                if response.status == 200:
                    status = await response.json()
                    print(f"📊 Queue Status: {status}")
                else:
                    print(f"❌ Failed to get queue status")
        
        print()
        
        # Step 3: Monitor call processing
        print("3️⃣ Monitoring call processing...")
        
        for i in range(10):  # Monitor for 10 seconds
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{QUEUE_API_URL}/api/calls/{backend_call_id}/status") as response:
                    if response.status == 200:
                        call_status = await response.json()
                        print(f"📞 Call Status [{i+1}/10]: {call_status.get('status')} - {call_status}")
                        
                        if call_status.get('status') in ['completed', 'failed', 'missed']:
                            print(f"🎯 Call reached final status: {call_status.get('status')}")
                            break
                    else:
                        print(f"⚠️ Could not get call status: {response.status}")
            
            await asyncio.sleep(1)
        
        print()
        
        # Step 4: Check voice bot status
        print("4️⃣ Checking voice bot call tracking...")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{VOICE_BOT_URL}/call-status/{backend_call_id}") as response:
                if response.status == 200:
                    bot_status = await response.json()
                    print(f"🤖 Voice Bot Status: {bot_status}")
                    print(f"📝 Transcript entries: {len(bot_status.get('transcript', []))}")
                    print(f"🎵 Recording: {bot_status.get('recording_status')}")
                else:
                    error_text = await response.text()
                    print(f"⚠️ Voice bot status check failed: {error_text}")
        
        print()
        
        # Step 5: Verify backend received the data
        print("5️⃣ Checking if backend received completion data...")
        
        # This would check the backend's call status endpoint
        # Since we don't have direct access, we'll simulate this check
        print("📤 Backend should have received call completion data via /api/calls/external-updates")
        print("🔍 Check backend logs to verify data was received with:")
        print(f"   - call_id: {backend_call_id}")
        print(f"   - variables: {test_variables}")
        print(f"   - transcript: [conversation data]")
        print(f"   - recording_url: [if available]")
        
        print()
        print("✅ Complete flow test finished!")
        print("🔍 Check logs in all systems to verify proper data flow")
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()

async def test_variable_passing():
    """Test that variables are properly passed through the system"""
    
    print("\n🧪 Testing Variable Passing")
    print("=" * 30)
    
    test_variables = {
        "customer_name": "Jane Smith",
        "account_number": "ACC123456",
        "balance": "₹25,000",
        "due_date": "2025-01-20",
        "payment_amount": "₹5,000"
    }
    
    backend_call_id = f"test-vars-{int(time.time())}"
    
    queue_payload = {
        "phone_number": "+919876543210",
        "campaign_id": "variable-test",
        "custom_call_id": backend_call_id,
        "call_config": {
            "flow_name": "carepal-test",
            "variables": test_variables,
            "test_mode": True
        },
        "priority": "normal"
    }
    
    print(f"📋 Testing with variables: {test_variables}")
    
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{QUEUE_API_URL}/api/calls/outbound", json=queue_payload) as response:
            if response.status == 200:
                result = await response.json()
                print(f"✅ Variable test call queued: {result.get('call_id')}")
            else:
                error_text = await response.text()
                print(f"❌ Variable test failed: {error_text}")
    
    # Wait a moment then check if variables were passed to voice bot
    await asyncio.sleep(2)
    
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{VOICE_BOT_URL}/call-status/{backend_call_id}") as response:
            if response.status == 200:
                bot_status = await response.json()
                returned_variables = bot_status.get('variables', {})
                print(f"🔍 Variables in voice bot: {returned_variables}")
                
                if returned_variables == test_variables:
                    print("✅ Variables passed correctly!")
                else:
                    print("❌ Variable mismatch!")
                    print(f"   Expected: {test_variables}")
                    print(f"   Received: {returned_variables}")
            else:
                print(f"⚠️ Could not check voice bot variables")

if __name__ == "__main__":
    print("🚀 Starting Complete Flow Tests")
    print("Make sure all systems are running:")
    print("  - CallQueueSystem (port 8001)")
    print("  - PipecatPlivoOutbound (port 8765)")
    print("  - Backend (port 3000)")
    print("  - Redis server")
    print()
    
    asyncio.run(test_complete_flow())
    asyncio.run(test_variable_passing()) 