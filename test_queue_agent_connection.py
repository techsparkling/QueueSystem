#!/usr/bin/env python3
"""
Test script to verify Standalone Queue System <-> Agent connection
"""

import asyncio
import aiohttp
import json
import sys
import os
from pathlib import Path

async def test_plivo_integration():
    """Test if we can import the Plivo integration"""
    print("🧪 Testing Plivo integration import...")
    
    try:
        from plivo_integration import PlivoCallManager
        manager = PlivoCallManager()
        print("✅ Plivo integration imported successfully")
        return True
    except Exception as e:
        print(f"❌ Failed to import Plivo integration: {e}")
        return False

async def test_queue_manager():
    """Test if queue manager can initialize"""
    print("🧪 Testing queue manager initialization...")
    
    try:
        from call_queue_manager import CallQueueManager
        queue_manager = CallQueueManager()
        await queue_manager.initialize()
        print("✅ Queue manager initialized successfully")
        await queue_manager.close()
        return True
    except Exception as e:
        print(f"❌ Failed to initialize queue manager: {e}")
        return False

async def test_queue_api():
    """Test if queue API is running"""
    print("🧪 Testing queue API connection...")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("http://localhost:8000/api/health") as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"✅ Queue API is healthy: {data}")
                    return True
                else:
                    print(f"❌ Queue API returned status {response.status}")
                    return False
    except Exception as e:
        print(f"❌ Failed to connect to queue API: {e}")
        print("💡 Make sure the queue system is running: python start_queue_system.py")
        return False

async def test_call_queuing():
    """Test queuing a call through the API"""
    print("🧪 Testing call queuing...")
    
    test_call = {
        "phone_number": "+919123456789",
        "campaign_id": "test-campaign",
        "call_config": {
            "voice": "en-US",
            "max_duration": 1800,
            "recording_enabled": True,
            "flow_name": "wishfin-test",
            "variables": {
                "name": "Test User",
                "email": "test@example.com"
            }
        },
        "custom_call_id": "test-call-123",
        "priority": "normal",
        "max_retries": 1
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "http://localhost:8000/api/calls/queue",
                json=test_call,
                headers={"Content-Type": "application/json"}
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"✅ Call queued successfully: {data}")
                    
                    # Check call status
                    call_id = data.get("call_id")
                    if call_id:
                        await asyncio.sleep(2)  # Wait a bit
                        async with session.get(f"http://localhost:8000/api/calls/{call_id}/status") as status_response:
                            if status_response.status == 200:
                                status_data = await status_response.json()
                                print(f"✅ Call status retrieved: {status_data.get('status')}")
                            else:
                                print(f"⚠️ Could not get call status: {status_response.status}")
                    
                    return True
                else:
                    error_text = await response.text()
                    print(f"❌ Failed to queue call: {response.status} - {error_text}")
                    return False
    except Exception as e:
        print(f"❌ Failed to test call queuing: {e}")
        return False

async def test_queue_status():
    """Test queue status endpoint"""
    print("🧪 Testing queue status...")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("http://localhost:8000/api/queue/status") as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"✅ Queue status: {json.dumps(data, indent=2)}")
                    return True
                else:
                    print(f"❌ Failed to get queue status: {response.status}")
                    return False
    except Exception as e:
        print(f"❌ Failed to test queue status: {e}")
        return False

async def test_environment_setup():
    """Test environment variables"""
    print("🧪 Testing environment setup...")
    
    required_vars = [
        "PLIVO_AUTH_ID",
        "PLIVO_AUTH_TOKEN", 
        "AGENT_SERVER_URL"
    ]
    
    missing_vars = []
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        print(f"❌ Missing environment variables: {', '.join(missing_vars)}")
        print("💡 Please set these in your .env file")
        return False
    else:
        print("✅ All required environment variables are set")
        return True

async def test_redis_connection():
    """Test Redis connection"""
    print("🧪 Testing Redis connection...")
    
    try:
        import redis
        r = redis.Redis(host='localhost', port=6379, decode_responses=True)
        r.ping()
        print("✅ Redis is running and accessible")
        return True
    except ImportError:
        print("❌ Redis package not installed: pip install redis")
        return False
    except Exception as e:
        print(f"❌ Redis connection failed: {e}")
        print("💡 Please start Redis: redis-server")
        return False

async def main():
    """Run all tests"""
    print("=" * 60)
    print("🧪 Standalone Queue System Connection Tests")
    print("=" * 60)
    
    tests = [
        ("Environment Setup", test_environment_setup),
        ("Redis Connection", test_redis_connection),
        ("Plivo Integration", test_plivo_integration),
        ("Queue Manager", test_queue_manager),
        ("Queue API", test_queue_api),
        ("Queue Status", test_queue_status),
        ("Call Queuing", test_call_queuing),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"\n📋 Running: {test_name}")
        print("-" * 40)
        
        try:
            result = await test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ Test {test_name} failed with exception: {e}")
            results.append((test_name, False))
        
        print("-" * 40)
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 Test Results Summary")
    print("=" * 60)
    
    passed = 0
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {test_name}")
        if result:
            passed += 1
    
    print(f"\n📈 Overall: {passed}/{len(results)} tests passed")
    
    if passed == len(results):
        print("🎉 All tests passed! Standalone queue system is ready for production.")
    else:
        print("⚠️ Some tests failed. Please check the issues above.")
        print("\n💡 Quick troubleshooting:")
        print("1. Make sure Redis is running: redis-server")
        print("2. Set environment variables in .env file")
        print("3. Start the queue system: python start_queue_system.py")
        print("4. Make sure your agent server is running on port 8765")
    
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main()) 