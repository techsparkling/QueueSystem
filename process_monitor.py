#!/usr/bin/env python3
"""
Process Monitor - Supervisor for Queue System
Monitors processes and automatically restarts them on failure
"""

import asyncio
import logging
import signal
import subprocess
import time
import psutil
import os
from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ProcessState(Enum):
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"

@dataclass
class ProcessConfig:
    name: str
    command: str
    args: List[str] = None
    working_dir: str = None
    max_restarts: int = 5
    restart_delay: int = 5
    health_check_url: Optional[str] = None
    environment: Dict[str, str] = None

class ProcessMonitor:
    """Monitors and manages system processes"""
    
    def __init__(self):
        self.processes: Dict[str, subprocess.Popen] = {}
        self.process_configs: Dict[str, ProcessConfig] = {}
        self.process_states: Dict[str, ProcessState] = {}
        self.restart_counts: Dict[str, int] = {}
        self.last_restart_time: Dict[str, float] = {}
        self.running = False
        
    def register_process(self, config: ProcessConfig):
        """Register a process for monitoring"""
        self.process_configs[config.name] = config
        self.process_states[config.name] = ProcessState.STOPPED
        self.restart_counts[config.name] = 0
        logger.info(f"📋 Registered process: {config.name}")
    
    async def start_all(self):
        """Start all registered processes"""
        self.running = True
        logger.info("🚀 Starting all processes...")
        
        for name in self.process_configs:
            await self.start_process(name)
        
        # Start monitoring loop
        asyncio.create_task(self._monitoring_loop())
    
    async def start_process(self, name: str):
        """Start a specific process"""
        config = self.process_configs.get(name)
        if not config:
            logger.error(f"❌ Process config not found: {name}")
            return False
        
        if self.process_states.get(name) == ProcessState.RUNNING:
            logger.info(f"⚠️ Process {name} already running")
            return True
        
        try:
            self.process_states[name] = ProcessState.STARTING
            logger.info(f"🚀 Starting process: {name}")
            
            # Prepare command
            cmd = [config.command]
            if config.args:
                cmd.extend(config.args)
            
            # Prepare environment
            env = os.environ.copy()
            if config.environment:
                env.update(config.environment)
            
            # Start process
            process = subprocess.Popen(
                cmd,
                cwd=config.working_dir or os.getcwd(),
                env=env,
                stdout=None,  # Allow output to be visible
                stderr=None,  # Allow error output to be visible
                preexec_fn=os.setsid if os.name != 'nt' else None
            )
            
            self.processes[name] = process
            self.process_states[name] = ProcessState.RUNNING
            
            logger.info(f"✅ Process {name} started with PID: {process.pid}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to start process {name}: {e}")
            self.process_states[name] = ProcessState.FAILED
            return False
    
    async def stop_process(self, name: str, graceful: bool = True):
        """Stop a specific process"""
        process = self.processes.get(name)
        if not process:
            logger.warning(f"⚠️ Process {name} not found")
            return
        
        try:
            self.process_states[name] = ProcessState.STOPPING
            logger.info(f"🛑 Stopping process: {name}")
            
            if graceful:
                # Send SIGTERM for graceful shutdown
                if os.name != 'nt':
                    os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                else:
                    process.terminate()
                
                # Wait for graceful shutdown
                try:
                    process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    logger.warning(f"⚠️ Process {name} didn't stop gracefully, forcing...")
                    if os.name != 'nt':
                        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                    else:
                        process.kill()
            else:
                # Force kill
                if os.name != 'nt':
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                else:
                    process.kill()
            
            del self.processes[name]
            self.process_states[name] = ProcessState.STOPPED
            logger.info(f"✅ Process {name} stopped")
            
        except Exception as e:
            logger.error(f"❌ Error stopping process {name}: {e}")
    
    async def restart_process(self, name: str):
        """Restart a specific process"""
        logger.info(f"🔄 Restarting process: {name}")
        
        # Check restart limits
        config = self.process_configs.get(name)
        if config and self.restart_counts[name] >= config.max_restarts:
            logger.error(f"❌ Process {name} exceeded max restarts ({config.max_restarts})")
            return False
        
        # Stop if running
        if name in self.processes:
            await self.stop_process(name)
        
        # Wait before restart
        config = self.process_configs.get(name)
        restart_delay = config.restart_delay if config else 5
        await asyncio.sleep(restart_delay)
        
        # Start process
        success = await self.start_process(name)
        if success:
            self.restart_counts[name] += 1
            self.last_restart_time[name] = time.time()
            
        return success
    
    async def _monitoring_loop(self):
        """Main monitoring loop"""
        while self.running:
            try:
                for name, process in list(self.processes.items()):
                    await self._check_process_health(name, process)
                
                # Reset restart counts if processes have been stable
                await self._reset_restart_counts()
                
                await asyncio.sleep(10)  # Check every 10 seconds
                
            except Exception as e:
                logger.error(f"❌ Monitoring loop error: {e}")
                await asyncio.sleep(30)
    
    async def _check_process_health(self, name: str, process: subprocess.Popen):
        """Check if a process is healthy"""
        try:
            # Check if process is still running
            exit_code = process.poll()
            
            if exit_code is not None:
                logger.error(f"❌ Process {name} exited with code: {exit_code}")
                self.process_states[name] = ProcessState.FAILED
                
                # Remove from processes dict
                del self.processes[name]
                
                # Attempt restart
                await self.restart_process(name)
                return
            
            # Check resource usage
            try:
                proc_info = psutil.Process(process.pid)
                cpu_percent = proc_info.cpu_percent()
                memory_info = proc_info.memory_info()
                
                # Log resource usage periodically
                if int(time.time()) % 300 == 0:  # Every 5 minutes
                    logger.info(f"📊 Process {name} - CPU: {cpu_percent:.1f}%, Memory: {memory_info.rss / 1024 / 1024:.1f}MB")
                
                # Check for resource limits (optional)
                if cpu_percent > 90:
                    logger.warning(f"⚠️ Process {name} high CPU usage: {cpu_percent:.1f}%")
                
                if memory_info.rss > 2 * 1024 * 1024 * 1024:  # 2GB
                    logger.warning(f"⚠️ Process {name} high memory usage: {memory_info.rss / 1024 / 1024:.1f}MB")
                
            except psutil.NoSuchProcess:
                logger.error(f"❌ Process {name} no longer exists")
                self.process_states[name] = ProcessState.FAILED
                del self.processes[name]
                await self.restart_process(name)
            
            # HTTP health check (if configured)
            config = self.process_configs.get(name)
            if config and config.health_check_url:
                await self._http_health_check(name, config.health_check_url)
                
        except Exception as e:
            logger.error(f"❌ Health check error for {name}: {e}")
    
    async def _http_health_check(self, name: str, url: str):
        """Perform HTTP health check"""
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status != 200:
                        logger.warning(f"⚠️ Process {name} health check failed: HTTP {response.status}")
                        # Could implement restart logic here if needed
                        
        except Exception as e:
            logger.warning(f"⚠️ Process {name} health check error: {e}")
    
    async def _reset_restart_counts(self):
        """Reset restart counts for stable processes"""
        current_time = time.time()
        
        for name, last_restart in list(self.last_restart_time.items()):
            # If process has been stable for 1 hour, reset restart count
            if current_time - last_restart > 3600:
                if self.restart_counts[name] > 0:
                    logger.info(f"🔄 Resetting restart count for stable process: {name}")
                    self.restart_counts[name] = 0
                del self.last_restart_time[name]
    
    async def stop_all(self):
        """Stop all processes"""
        self.running = False
        logger.info("🛑 Stopping all processes...")
        
        for name in list(self.processes.keys()):
            await self.stop_process(name)
        
        logger.info("✅ All processes stopped")
    
    def get_status(self) -> Dict[str, Dict]:
        """Get status of all processes"""
        status = {}
        
        for name, config in self.process_configs.items():
            process = self.processes.get(name)
            
            status[name] = {
                "state": self.process_states.get(name, ProcessState.STOPPED).value,
                "pid": process.pid if process else None,
                "restart_count": self.restart_counts.get(name, 0),
                "max_restarts": config.max_restarts,
                "command": f"{config.command} {' '.join(config.args or [])}"
            }
            
        return status

# Pre-configured process monitor for the queue system
def create_queue_system_monitor() -> ProcessMonitor:
    """Create a process monitor configured for the queue system"""
    monitor = ProcessMonitor()
    
    # Get the virtual environment python path
    import sys
    python_path = sys.executable
    
    # Queue API Service
    monitor.register_process(ProcessConfig(
        name="queue_api",
        command=python_path,
        args=["queue_api_service.py"],
        max_restarts=10,
        restart_delay=5,
        health_check_url="http://localhost:8000/api/health"
    ))
    
    # Queue Workers
    monitor.register_process(ProcessConfig(
        name="queue_workers",
        command=python_path,
        args=["call_queue_manager.py"],
        max_restarts=10,
        restart_delay=10
    ))
    
    return monitor

if __name__ == "__main__":
    async def main():
        monitor = create_queue_system_monitor()
        
        # Setup signal handlers for graceful shutdown
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, shutting down...")
            asyncio.create_task(monitor.stop_all())
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        try:
            await monitor.start_all()
            
            # Keep running until stopped
            while monitor.running:
                await asyncio.sleep(1)
                
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
        finally:
            await monitor.stop_all()
    
    asyncio.run(main()) 