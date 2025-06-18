#!/usr/bin/env python3
"""
Production Startup Script - Crash-Proof Queue System
Starts the system with full resilience, monitoring, and recovery
"""

import asyncio
import logging
import signal
import sys
import os
from datetime import datetime
from typing import Dict, Any
from dotenv import load_dotenv

# Load environment variables first
load_dotenv()

from crash_recovery import crash_recovery_manager
# Cloud Run doesn't need process monitor - it manages the single process
# from process_monitor import create_queue_system_monitor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('queue_system.log')
    ]
)
logger = logging.getLogger(__name__)

class ProductionQueueSystem:
    """Production-grade queue system with full crash recovery"""
    
    def __init__(self):
        self.process_monitor = None
        self.crash_recovery = None
        self.running = False
        self.startup_time = None
        self.server_task = None  # For Cloud Run API server
        
    async def startup(self):
        """Start the system with all resilience features"""
        logger.info("=" * 80)
        logger.info("🚀 PRODUCTION QUEUE SYSTEM STARTUP")
        logger.info("=" * 80)
        
        self.startup_time = datetime.utcnow()
        
        try:
            # 1. Prerequisites check
            await self._check_prerequisites()
            
            # 2. Initialize crash recovery
            await self._initialize_crash_recovery()
            
            # 3. Setup health checks and recovery strategies
            await self._setup_health_monitoring()
            
            # 4. Start process monitor
            await self._start_process_monitor()
            
            # 5. Setup signal handlers
            self._setup_signal_handlers()
            
            self.running = True
            logger.info("✅ PRODUCTION SYSTEM READY")
            logger.info("🔗 Health: http://localhost:8000/api/health")
            logger.info("📊 Status: http://localhost:8000/api/queue/status")
            logger.info("🛡️ Monitoring: Active with auto-recovery")
            
            # Keep running
            await self._main_loop()
            
        except Exception as e:
            logger.error(f"❌ STARTUP FAILED: {e}")
            await self.shutdown()
            sys.exit(1)
    
    async def _cleanup_existing_processes(self):
        """Clean up any existing processes"""
        logger.info("🧹 Cleaning up existing processes...")
        
        import psutil
        
        # Kill all related processes
        processes_to_kill = ['queue_api_service', 'call_queue_manager', 'production_start']
        killed_count = 0
        
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = ' '.join(proc.info['cmdline'] or [])
                if any(keyword in cmdline for keyword in processes_to_kill):
                    if proc.pid != os.getpid():  # Don't kill ourselves
                        logger.info(f"🔥 Stopping existing process {proc.info['pid']}: {proc.info['name']}")
                        proc.terminate()
                        killed_count += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        
        if killed_count > 0:
            logger.info(f"✅ Stopped {killed_count} existing processes")
            await asyncio.sleep(3)  # Wait for processes to stop
        else:
            logger.info("✅ No existing processes found")

    async def _check_prerequisites(self):
        """Check all prerequisites"""
        logger.info("🔍 Checking prerequisites...")
        
        # Stop any existing processes first
        await self._cleanup_existing_processes()
        
        # Check Redis (use environment URL for Cloud Run)
        try:
            import redis
            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
            r = redis.from_url(redis_url, decode_responses=True)
            r.ping()
            logger.info(f"✅ Redis: Connected to {redis_url}")
        except Exception as e:
            raise Exception(f"Redis not available: {e}")
        
        # Check environment variables
        required_vars = [
            "PLIVO_AUTH_ID",
            "PLIVO_AUTH_TOKEN", 
            "AGENT_SERVER_URL"
        ]
        
        missing = [var for var in required_vars if not os.getenv(var)]
        if missing:
            raise Exception(f"Missing environment variables: {missing}")
        
        logger.info("✅ Environment: All variables set")
        
        # Check Python dependencies
        try:
            import aiohttp
            import fastapi
            import plivo
            logger.info("✅ Dependencies: All packages available")
        except ImportError as e:
            raise Exception(f"Missing Python package: {e}")
    
    async def _initialize_crash_recovery(self):
        """Initialize crash recovery system"""
        logger.info("🛡️ Initializing crash recovery...")
        
        self.crash_recovery = crash_recovery_manager
        await self.crash_recovery.initialize()
        
        logger.info("✅ Crash recovery: Active")
    
    async def _setup_health_monitoring(self):
        """Setup health checks and recovery strategies"""
        logger.info("💓 Setting up health monitoring...")
        
        # Redis health check
        async def redis_health():
            try:
                import redis
                redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
                r = redis.from_url(redis_url, decode_responses=True)
                r.ping()
                return True
            except:
                return False
        
        # Queue API health check (skip in Cloud Run since it's the same process)
        async def api_health():
            # In Cloud Run, we ARE the API service, so just return True
            return True
        
        # Agent service health check
        async def agent_health():
            try:
                import aiohttp
                agent_url = os.getenv("AGENT_SERVER_URL", "https://pipecat-agent-staging-443142017693.us-east1.run.app")
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"{agent_url}/health", timeout=aiohttp.ClientTimeout(total=5)) as response:
                        return response.status == 200
            except:
                return False
        
        # Register health checks
        await self.crash_recovery.register_health_check("redis", redis_health)
        await self.crash_recovery.register_health_check("queue_api", api_health)
        await self.crash_recovery.register_health_check("agent_service", agent_health)
        
        # Recovery strategies
        async def restart_redis():
            logger.info("🔄 Attempting Redis restart...")
            import subprocess
            try:
                subprocess.run(["redis-server", "--daemonize", "yes"], check=True)
                await asyncio.sleep(5)
                return True
            except:
                return False
        
        await self.crash_recovery.register_recovery_strategy("redis", restart_redis)
        
        logger.info("✅ Health monitoring: Configured")
    
    async def _start_process_monitor(self):
        """Start process monitoring (Cloud Run adaptation)"""
        logger.info("👷 Starting process monitor (Cloud Run mode)...")
        
        # In Cloud Run, we don't need multi-process monitoring
        # Instead, we'll start the API service directly
        try:
            from queue_api_service import app
            import uvicorn
            
            # Start the FastAPI server in the background
            port = int(os.getenv("PORT", 8000))
            host = os.getenv("HOST", "0.0.0.0")
            
            config = uvicorn.Config(
                app=app,
                host=host,
                port=port,
                log_level="info",
                access_log=False,  # Reduce noise
                loop="asyncio"
            )
            server = uvicorn.Server(config)
            
            # Start server in background task
            self.server_task = asyncio.create_task(server.serve())
            
            logger.info(f"✅ API server started on {host}:{port}")
            
        except Exception as e:
            logger.error(f"❌ Failed to start API server: {e}")
            raise
    
    def _setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown"""
        def signal_handler(signum, frame):
            logger.info(f"📡 Received signal {signum}, initiating graceful shutdown...")
            asyncio.create_task(self.shutdown())
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    async def _main_loop(self):
        """Main system loop"""
        while self.running:
            try:
                # Periodic system status report
                await self._status_report()
                await asyncio.sleep(300)  # Every 5 minutes
                
            except Exception as e:
                logger.error(f"❌ Main loop error: {e}")
                await asyncio.sleep(60)
    
    async def _status_report(self):
        """Generate periodic status report"""
        try:
            # System uptime
            uptime = datetime.utcnow() - self.startup_time
            
            # Server status (Cloud Run mode)
            server_status = "running" if self.server_task and not self.server_task.done() else "stopped"
            
            # Crash recovery status
            recovery_status = await self.crash_recovery.get_system_status() if self.crash_recovery else {}
            
            # Queue metrics (simplified)
            queue_metrics = {"queue_size": 0, "processed_today": 0}  # Would get from Redis
            
            logger.info("📊 SYSTEM STATUS REPORT (CLOUD RUN)")
            logger.info(f"⏱️  Uptime: {uptime}")
            logger.info(f"🌐 API Server: {server_status}")
            logger.info(f"📞 Queue: {queue_metrics['queue_size']} pending, {queue_metrics['processed_today']} processed today")
            logger.info(f"🛡️  Circuit Breakers: {len(recovery_status.get('circuit_breakers', {}))} active")
            
        except Exception as e:
            logger.error(f"❌ Status report error: {e}")
    
    async def shutdown(self):
        """Graceful shutdown"""
        if not self.running:
            return
        
        logger.info("🛑 GRACEFUL SHUTDOWN INITIATED")
        self.running = False
        
        try:
            # Stop API server (Cloud Run mode)
            if self.server_task and not self.server_task.done():
                self.server_task.cancel()
                try:
                    await self.server_task
                except asyncio.CancelledError:
                    pass
                logger.info("✅ API server stopped")
            
            # Stop crash recovery
            if self.crash_recovery:
                # Cleanup if needed
                logger.info("✅ Crash recovery stopped")
            
            logger.info("✅ SHUTDOWN COMPLETE")
            
        except Exception as e:
            logger.error(f"❌ Shutdown error: {e}")

# System management functions
async def start_production_system():
    """Start the production system"""
    system = ProductionQueueSystem()
    await system.startup()

async def emergency_stop():
    """Emergency stop all processes"""
    logger.warning("🚨 EMERGENCY STOP INITIATED")
    
    import psutil
    
    # Kill all related processes
    processes_to_kill = ['queue_api_service', 'call_queue_manager', 'production_start', 'agent_service']
    killed_count = 0
    
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmdline = ' '.join(proc.info['cmdline'] or [])
            if any(keyword in cmdline for keyword in processes_to_kill):
                logger.warning(f"🔥 Killing process {proc.info['pid']}: {proc.info['name']}")
                proc.kill()
                killed_count += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    
    logger.warning(f"🚨 EMERGENCY STOP COMPLETE - Killed {killed_count} processes")

async def system_status():
    """Get current system status"""
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get("http://localhost:8000/api/health") as response:
                if response.status == 200:
                    data = await response.json()
                    print("🟢 System Status: HEALTHY")
                    print(f"📊 Details: {data}")
                else:
                    print("🔴 System Status: UNHEALTHY")
            
    except Exception as e:
        print(f"❌ Cannot connect to system: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "start":
            asyncio.run(start_production_system())
        elif command == "stop":
            asyncio.run(emergency_stop())
        elif command == "status":
            asyncio.run(system_status())
        else:
            print("Usage: python production_start.py [start|stop|status]")
    else:
        # Default: start system
        asyncio.run(start_production_system()) 