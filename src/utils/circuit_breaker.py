"""
Circuit Breaker Pattern Implementation
Provides async-aware circuit breaker functionality for service resilience
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum
from functools import wraps
from typing import Any, Callable, Dict, Optional, Union

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states"""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Circuit is open, failing fast
    HALF_OPEN = "half_open"  # Testing if service has recovered


@dataclass
class CircuitBreakerConfig:
    """Circuit breaker configuration"""
    failure_threshold: int = 3          # Failures before opening circuit
    recovery_timeout: int = 30          # Seconds before trying half-open
    success_threshold: int = 1          # Successes needed to close from half-open
    timeout: float = 5.0                # Individual operation timeout
    expected_exception: type = Exception # Exception type that counts as failure


@dataclass
class CircuitBreakerMetrics:
    """Circuit breaker metrics for monitoring"""
    state: CircuitState
    failure_count: int
    success_count: int
    last_failure_time: Optional[float]
    last_success_time: Optional[float]
    total_requests: int
    circuit_opened_count: int


class CircuitBreaker:
    """
    Async-aware circuit breaker implementation
    
    Provides resilience for external service calls by:
    - Failing fast when service is known to be down
    - Automatically recovering when service comes back
    - Providing metrics for monitoring
    """
    
    def __init__(self, name: str, config: Optional[CircuitBreakerConfig] = None):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        
        # State management
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[float] = None
        self._last_success_time: Optional[float] = None
        self._total_requests = 0
        self._circuit_opened_count = 0
        
        # Thread safety
        self._lock = asyncio.Lock()
        
        logger.info(f"Circuit breaker '{name}' initialized with config: {self.config}")
    
    @property
    def state(self) -> CircuitState:
        """Get current circuit state"""
        return self._state
    
    @property
    def metrics(self) -> CircuitBreakerMetrics:
        """Get current metrics"""
        return CircuitBreakerMetrics(
            state=self._state,
            failure_count=self._failure_count,
            success_count=self._success_count,
            last_failure_time=self._last_failure_time,
            last_success_time=self._last_success_time,
            total_requests=self._total_requests,
            circuit_opened_count=self._circuit_opened_count
        )
    
    async def _should_attempt_reset(self) -> bool:
        """Check if circuit should attempt to reset"""
        if self._state != CircuitState.OPEN:
            return False
            
        if self._last_failure_time is None:
            return True
            
        return time.time() - self._last_failure_time >= self.config.recovery_timeout
    
    async def _record_success(self):
        """Record successful operation"""
        async with self._lock:
            self._success_count += 1
            self._last_success_time = time.time()
            
            if self._state == CircuitState.HALF_OPEN:
                if self._success_count >= self.config.success_threshold:
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
                    logger.info(f"Circuit breaker '{self.name}' closed after successful recovery")
            elif self._state == CircuitState.CLOSED:
                # Reset failure count on success in closed state
                self._failure_count = 0
    
    async def _record_failure(self, exception: Exception):
        """Record failed operation"""
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()
            
            if self._state == CircuitState.CLOSED:
                if self._failure_count >= self.config.failure_threshold:
                    self._state = CircuitState.OPEN
                    self._circuit_opened_count += 1
                    logger.warning(
                        f"Circuit breaker '{self.name}' opened after {self._failure_count} failures. "
                        f"Last error: {exception}"
                    )
            elif self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                logger.warning(
                    f"Circuit breaker '{self.name}' failed during half-open test, reopening circuit"
                )
    
    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function with circuit breaker protection
        
        Args:
            func: Function to execute (can be sync or async)
            *args: Function arguments
            **kwargs: Function keyword arguments
            
        Returns:
            Function result
            
        Raises:
            CircuitBreakerOpenException: When circuit is open
            Original exception: When function fails
        """
        async with self._lock:
            self._total_requests += 1
            
            # Check if circuit should attempt reset
            if await self._should_attempt_reset():
                self._state = CircuitState.HALF_OPEN
                self._success_count = 0
                logger.info(f"Circuit breaker '{self.name}' attempting recovery (half-open)")
        
        # Fail fast if circuit is open
        if self._state == CircuitState.OPEN:
            raise CircuitBreakerOpenException(
                f"Circuit breaker '{self.name}' is open. "
                f"Last failure: {self._last_failure_time}"
            )
        
        # Execute function with timeout
        try:
            if asyncio.iscoroutinefunction(func):
                # Async function
                result = await asyncio.wait_for(
                    func(*args, **kwargs),
                    timeout=self.config.timeout
                )
            else:
                # Sync function - run in thread pool
                loop = asyncio.get_event_loop()
                result = await asyncio.wait_for(
                    loop.run_in_executor(None, lambda: func(*args, **kwargs)),
                    timeout=self.config.timeout
                )
            
            await self._record_success()
            return result
            
        except Exception as e:
            # Only count expected exceptions as failures
            if isinstance(e, self.config.expected_exception):
                await self._record_failure(e)
            raise
    
    def sync_call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Synchronous wrapper for circuit breaker call
        
        For use in non-async contexts
        """
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        return loop.run_until_complete(self.call(func, *args, **kwargs))
    
    def reset(self):
        """Manually reset circuit breaker to closed state"""
        async def _reset():
            async with self._lock:
                self._state = CircuitState.CLOSED
                self._failure_count = 0
                self._success_count = 0
                logger.info(f"Circuit breaker '{self.name}' manually reset")
        
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        loop.run_until_complete(_reset())


class CircuitBreakerOpenException(Exception):
    """Exception raised when circuit breaker is open"""
    pass


# Decorator for easy usage
def circuit_breaker(name: str, config: Optional[CircuitBreakerConfig] = None):
    """
    Decorator to apply circuit breaker to functions
    
    Usage:
        @circuit_breaker("my_service")
        async def my_function():
            # function implementation
            pass
    """
    cb = CircuitBreaker(name, config)
    
    def decorator(func: Callable):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            return await cb.call(func, *args, **kwargs)
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            return cb.sync_call(func, *args, **kwargs)
        
        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            wrapper = async_wrapper
        else:
            wrapper = sync_wrapper
        
        # Attach circuit breaker for access to metrics
        wrapper.circuit_breaker = cb
        return wrapper
    
    return decorator


# Global circuit breaker registry for monitoring
_circuit_breakers: Dict[str, CircuitBreaker] = {}


def get_circuit_breaker(name: str, config: Optional[CircuitBreakerConfig] = None) -> CircuitBreaker:
    """Get or create a circuit breaker by name"""
    if name not in _circuit_breakers:
        _circuit_breakers[name] = CircuitBreaker(name, config)
    return _circuit_breakers[name]


def get_all_circuit_breakers() -> Dict[str, CircuitBreaker]:
    """Get all registered circuit breakers for monitoring"""
    return _circuit_breakers.copy()
