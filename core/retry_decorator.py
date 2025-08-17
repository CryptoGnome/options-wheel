"""
Retry decorator for handling API failures and network errors.
"""
import time
import logging
from functools import wraps
from typing import Optional, Tuple, Type, Union
import random

logger = logging.getLogger(f"strategy.{__name__}")

class RetryException(Exception):
    """Custom exception for retry failures"""
    pass

def exponential_backoff_with_jitter(
    attempt: int,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    jitter: bool = True
) -> float:
    """
    Calculate exponential backoff with optional jitter.
    
    Args:
        attempt: Current attempt number (0-based)
        base_delay: Base delay in seconds
        max_delay: Maximum delay in seconds
        jitter: Whether to add random jitter
    
    Returns:
        Delay in seconds
    """
    delay = min(base_delay * (2 ** attempt), max_delay)
    if jitter:
        delay = delay * (0.5 + random.random() * 0.5)
    return delay

def retry_on_failure(
    max_attempts: int = 3,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    backoff: bool = True,
    jitter: bool = True
):
    """
    Decorator to retry function calls on failure.
    
    Args:
        max_attempts: Maximum number of attempts
        exceptions: Tuple of exceptions to catch and retry
        base_delay: Base delay between retries in seconds
        max_delay: Maximum delay between retries
        backoff: Whether to use exponential backoff
        jitter: Whether to add jitter to delays
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(max_attempts):
                try:
                    result = func(*args, **kwargs)
                    if attempt > 0:
                        logger.info(f"{func.__name__} succeeded after {attempt + 1} attempts")
                    return result
                    
                except exceptions as e:
                    last_exception = e
                    
                    if attempt == max_attempts - 1:
                        logger.error(
                            f"{func.__name__} failed after {max_attempts} attempts: {str(e)}"
                        )
                        raise RetryException(
                            f"Failed after {max_attempts} attempts: {str(e)}"
                        ) from e
                    
                    if backoff:
                        delay = exponential_backoff_with_jitter(
                            attempt, base_delay, max_delay, jitter
                        )
                    else:
                        delay = base_delay
                    
                    logger.warning(
                        f"{func.__name__} attempt {attempt + 1}/{max_attempts} failed: {str(e)}. "
                        f"Retrying in {delay:.2f} seconds..."
                    )
                    time.sleep(delay)
            
            if last_exception:
                raise last_exception
                
        return wrapper
    return decorator

class CircuitBreaker:
    """
    Circuit breaker pattern implementation for API calls.
    """
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        expected_exception: Type[Exception] = Exception
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        self.failure_count = 0
        self.last_failure_time: Optional[float] = None
        self.state = "closed"  # closed, open, half-open
        
    def call(self, func, *args, **kwargs):
        """
        Execute function with circuit breaker protection.
        """
        if self.state == "open":
            if self.last_failure_time and \
               time.time() - self.last_failure_time >= self.recovery_timeout:
                self.state = "half-open"
                logger.info(f"Circuit breaker entering half-open state for {func.__name__}")
            else:
                raise RetryException(
                    f"Circuit breaker is open for {func.__name__}. "
                    f"Waiting for recovery timeout."
                )
        
        try:
            result = func(*args, **kwargs)
            if self.state == "half-open":
                self.state = "closed"
                self.failure_count = 0
                logger.info(f"Circuit breaker closed for {func.__name__}")
            return result
            
        except self.expected_exception as e:
            self.failure_count += 1
            self.last_failure_time = time.time()
            
            if self.failure_count >= self.failure_threshold:
                self.state = "open"
                logger.error(
                    f"Circuit breaker opened for {func.__name__} "
                    f"after {self.failure_count} failures"
                )
            
            raise e
    
    def reset(self):
        """Reset circuit breaker to closed state."""
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "closed"