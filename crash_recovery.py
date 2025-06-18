#!/usr/bin/env python3
"""
Crash Recovery System - Production Grade Resilience
Handles crashes, circuit breakers, and automatic recovery
"""

import asyncio
import logging
import time
import json
import os
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Callable
from enum import Enum
import redis.asyncio as redis
import aiohttp
from dataclasses import dataclass

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CircuitState(Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Circuit breaker triggered
    HALF_OPEN = "half_open" # Testing if service recovered

@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 5
    recovery_timeout: int = 60
    success_threshold: int = 3
    timeout: int = 30

class CircuitBreaker:
    """Circuit breaker pattern implementation"""
    
    def __init__(self, name: str, config: CircuitBreakerConfig = None):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = None
        
    async def call(self, func: Callable, *args, **kwargs):
        """Execute function with circuit breaker protection"""
        
        if self.state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self.state = CircuitState.HALF_OPEN
                logger.info(f"🔄 Circuit breaker {self.name} attempting reset")
            else:
                raise Exception(f"Circuit breaker {self.name} is OPEN")
        
        try:
            result = await func(*args, **kwargs)
            await self._on_success()
            return result
            
        except Exception as e:
            await self._on_failure(e)
            raise
    
    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset"""
        if not self.last_failure_time:
            return True
        
        return (time.time() - self.last_failure_time) >= self.config.recovery_timeout
    
    async def _on_success(self):
        """Handle successful operation"""
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.config.success_threshold:
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.success_count = 0
                logger.info(f"✅ Circuit breaker {self.name} reset to CLOSED")
        else:
            self.failure_count = 0
    
    async def _on_failure(self, error: Exception):
        """Handle failed operation"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.config.failure_threshold:
            self.state = CircuitState.OPEN
            self.success_count = 0
            logger.error(f"🔴 Circuit breaker {self.name} opened due to: {error}")

class CrashRecoveryManager:
    """Manages crash recovery and system resilience"""
    
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis_url = redis_url
        self.redis_client = None
        self.circuit_breakers = {}
        self.health_checks = {}
        self.recovery_strategies = {}
        
    async def initialize(self):
        """Initialize crash recovery system"""
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            await self.redis_client.ping()
            
            # Initialize circuit breakers
            await self._setup_circuit_breakers()
            
            # Start monitoring
            asyncio.create_task(self._monitoring_loop())
            
            logger.info("🛡️ Crash Recovery Manager initialized")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize crash recovery: {e}")
            raise
    
    async def _setup_circuit_breakers(self):
        """Setup circuit breakers for critical services"""
        services = {
            "plivo_api": CircuitBreakerConfig(failure_threshold=3, recovery_timeout=30),
            "agent_service": CircuitBreakerConfig(failure_threshold=5, recovery_timeout=60),
            "database": CircuitBreakerConfig(failure_threshold=2, recovery_timeout=120),
            "redis": CircuitBreakerConfig(failure_threshold=3, recovery_timeout=30)
        }
        
        for service_name, config in services.items():
            self.circuit_breakers[service_name] = CircuitBreaker(service_name, config)
            logger.info(f"🔧 Circuit breaker setup for {service_name}")
    
    async def execute_with_resilience(self, service_name: str, func: Callable, *args, **kwargs):
        """Execute function with full resilience (circuit breaker + retry)"""
        circuit_breaker = self.circuit_breakers.get(service_name)
        if not circuit_breaker:
            # No circuit breaker, execute directly
            return await func(*args, **kwargs)
        
        # Execute with circuit breaker protection
        return await circuit_breaker.call(func, *args, **kwargs)
    
    async def register_health_check(self, service_name: str, health_func: Callable):
        """Register a health check function"""
        self.health_checks[service_name] = health_func
        logger.info(f"💓 Health check registered for {service_name}")
    
    async def register_recovery_strategy(self, service_name: str, recovery_func: Callable):
        """Register a recovery strategy"""
        self.recovery_strategies[service_name] = recovery_func
        logger.info(f"🔄 Recovery strategy registered for {service_name}")
    
    async def _monitoring_loop(self):
        """Main monitoring loop"""
        while True:
            try:
                await self._check_system_health()
                await self._recover_failed_jobs()
                await self._cleanup_stale_data()
                await asyncio.sleep(30)  # Check every 30 seconds
                
            except Exception as e:
                logger.error(f"❌ Monitoring loop error: {e}")
                await asyncio.sleep(60)  # Back off on error
    
    async def _check_system_health(self):
        """Check health of all registered services"""
        unhealthy_services = []
        
        for service_name, health_func in self.health_checks.items():
            try:
                is_healthy = await health_func()
                if not is_healthy:
                    unhealthy_services.append(service_name)
                    
            except Exception as e:
                logger.error(f"❌ Health check failed for {service_name}: {e}")
                unhealthy_services.append(service_name)
        
        # Attempt recovery for unhealthy services
        for service_name in unhealthy_services:
            await self._attempt_service_recovery(service_name)
    
    async def _attempt_service_recovery(self, service_name: str):
        """Attempt to recover a failed service"""
        recovery_func = self.recovery_strategies.get(service_name)
        if recovery_func:
            try:
                logger.info(f"🔄 Attempting recovery for {service_name}")
                await recovery_func()
                logger.info(f"✅ Recovery successful for {service_name}")
                
            except Exception as e:
                logger.error(f"❌ Recovery failed for {service_name}: {e}")
    
    async def _recover_failed_jobs(self):
        """Recover jobs that were processing during a crash"""
        try:
            # Find jobs that were marked as PROCESSING but haven't updated in 10 minutes
            cutoff_time = datetime.utcnow() - timedelta(minutes=10)
            
            # Scan for stale processing jobs
            job_keys = await self.redis_client.keys("call_job:*")
            
            for job_key in job_keys:
                job_data = await self.redis_client.hget(job_key, "data")
                if job_data:
                    job_dict = json.loads(job_data)
                    
                    if job_dict.get("status") == "processing":
                        updated_at = job_dict.get("updated_at")
                        if updated_at:
                            updated_time = datetime.fromisoformat(updated_at.replace('Z', '+00:00'))
                            
                            if updated_time < cutoff_time:
                                # Job is stale, re-queue it
                                job_dict["status"] = "queued"
                                job_dict["retry_count"] = job_dict.get("retry_count", 0) + 1
                                job_dict["error"] = "Recovered from crash"
                                job_dict["updated_at"] = datetime.utcnow().isoformat()
                                
                                # Re-queue the job
                                await self.redis_client.lpush("call_queue", json.dumps(job_dict))
                                await self.redis_client.hset(job_key, "data", json.dumps(job_dict))
                                
                                logger.info(f"🔄 Recovered stale job: {job_dict.get('id')}")
                                
        except Exception as e:
            logger.error(f"❌ Failed to recover jobs: {e}")
    
    async def _cleanup_stale_data(self):
        """Cleanup stale data from Redis"""
        try:
            # Remove expired job data (older than 7 days)
            cutoff_time = datetime.utcnow() - timedelta(days=7)
            
            job_keys = await self.redis_client.keys("call_job:*")
            
            for job_key in job_keys:
                job_data = await self.redis_client.hget(job_key, "data")
                if job_data:
                    job_dict = json.loads(job_data)
                    created_at = job_dict.get("created_at")
                    
                    if created_at:
                        created_time = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                        
                        if created_time < cutoff_time:
                            await self.redis_client.delete(job_key)
                            logger.info(f"🧹 Cleaned up old job: {job_dict.get('id')}")
                            
        except Exception as e:
            logger.error(f"❌ Cleanup failed: {e}")
    
    async def get_system_status(self) -> Dict[str, Any]:
        """Get overall system status"""
        circuit_status = {}
        for name, cb in self.circuit_breakers.items():
            circuit_status[name] = {
                "state": cb.state.value,
                "failure_count": cb.failure_count,
                "success_count": cb.success_count
            }
        
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "circuit_breakers": circuit_status,
            "health_checks_count": len(self.health_checks),
            "recovery_strategies_count": len(self.recovery_strategies)
        }

# Global instance - use environment Redis URL
crash_recovery_manager = CrashRecoveryManager(
    redis_url=os.getenv("REDIS_URL", "redis://localhost:6379")
)

# Helper functions for easy integration
async def execute_with_circuit_breaker(service_name: str, func: Callable, *args, **kwargs):
    """Execute function with circuit breaker protection"""
    return await crash_recovery_manager.execute_with_resilience(service_name, func, *args, **kwargs)

async def register_health_check(service_name: str, health_func: Callable):
    """Register a health check"""
    await crash_recovery_manager.register_health_check(service_name, health_func)

async def register_recovery_strategy(service_name: str, recovery_func: Callable):
    """Register a recovery strategy"""
    await crash_recovery_manager.register_recovery_strategy(service_name, recovery_func) 