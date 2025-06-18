#!/usr/bin/env python3
"""
Startup script for Call Queue System
Runs the API server and queue workers
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

# Add the current directory to Python path
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

from api_server import app
from call_queue_manager import CallQueueManager
import uvicorn

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def main():
    """Main startup function"""
    logger.info("🚀 Starting Call Queue System...")
    
    # Check environment variables
    required_env_vars = [
        "PLIVO_AUTH_ID",
        "PLIVO_AUTH_TOKEN", 
        "PLIVO_PHONE_NUMBER",
        "AGENT_SERVER_URL",
        "BACKEND_API_URL"
    ]
    
    missing_vars = []
    for var in required_env_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        logger.error(f"❌ Missing required environment variables: {missing_vars}")
        logger.error("Please set these environment variables before starting the queue system.")
        return
    
    logger.info("✅ Environment variables configured")
    logger.info(f"📞 Plivo Number: {os.getenv('PLIVO_PHONE_NUMBER')}")
    logger.info(f"🤖 Agent Server: {os.getenv('AGENT_SERVER_URL')}")
    logger.info(f"🌐 Backend API: {os.getenv('BACKEND_API_URL')}")
    
    # Test Redis connection
    try:
        import redis.asyncio as redis
        redis_client = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))
        await redis_client.ping()
        logger.info("✅ Redis connection successful")
        await redis_client.close()
    except Exception as e:
        logger.error(f"❌ Redis connection failed: {e}")
        logger.error("Please ensure Redis is running on localhost:6379")
        return
    
    # Start the API server
    logger.info("🌐 Starting Call Queue API Server on port 8000...")
    logger.info("📋 Endpoints available:")
    logger.info("   POST /api/calls/queue - Queue a new call")
    logger.info("   GET  /api/calls/status - Get queue status")
    logger.info("   GET  /api/calls/{call_id}/status - Get call status")
    logger.info("   POST /api/calls/results - Receive completion callbacks")
    logger.info("   GET  /health - Health check")
    
    # Run the server
    config = uvicorn.Config(
        app=app,
        host="0.0.0.0",
        port=8000,
        log_level="info",
        access_log=True
    )
    
    server = uvicorn.Server(config)
    await server.serve()

if __name__ == "__main__":
    # Load environment variables from .env file if it exists
    try:
        from dotenv import load_dotenv
        env_file = current_dir.parent / ".env"
        if env_file.exists():
            load_dotenv(env_file)
            logger.info(f"✅ Loaded environment from {env_file}")
        else:
            logger.info("⚠️ No .env file found, using system environment variables")
    except ImportError:
        logger.info("⚠️ python-dotenv not installed, using system environment variables")
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Call Queue System shut down")
    except Exception as e:
        logger.error(f"❌ Failed to start Call Queue System: {e}")
        sys.exit(1) 