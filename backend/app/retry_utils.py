"""Retry utilities with exponential backoff for external services."""

import time
import logging
from typing import Callable, TypeVar, Optional, Type, Tuple
from functools import wraps

logger = logging.getLogger(__name__)

T = TypeVar('T')


def exponential_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,)
):
    """
    Decorator that implements exponential backoff retry logic.
    
    Args:
        max_retries: Maximum number of retry attempts (default: 3)
        base_delay: Initial delay in seconds (default: 1.0)
        max_delay: Maximum delay in seconds (default: 60.0)
        exponential_base: Base for exponential calculation (default: 2.0)
        exceptions: Tuple of exception types to catch and retry (default: all exceptions)
    
    Returns:
        Decorated function with retry logic
    
    Example:
        @exponential_backoff(max_retries=3, base_delay=1.0)
        def risky_operation():
            # Code that might fail
            pass
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    
                    if attempt == max_retries:
                        # Final attempt failed, raise the exception
                        logger.error(
                            f"Function {func.__name__} failed after {max_retries + 1} attempts: {str(e)}",
                            extra={
                                "function": func.__name__,
                                "attempts": max_retries + 1,
                                "error": str(e)
                            }
                        )
                        raise
                    
                    # Calculate delay with exponential backoff
                    delay = min(base_delay * (exponential_base ** attempt), max_delay)
                    
                    logger.warning(
                        f"Function {func.__name__} failed (attempt {attempt + 1}/{max_retries + 1}), "
                        f"retrying in {delay:.2f}s: {str(e)}",
                        extra={
                            "function": func.__name__,
                            "attempt": attempt + 1,
                            "max_attempts": max_retries + 1,
                            "delay": delay,
                            "error": str(e)
                        }
                    )
                    
                    time.sleep(delay)
            
            # This should never be reached, but just in case
            if last_exception:
                raise last_exception
            
        return wrapper
    return decorator


def retry_on_failure(
    func: Callable[..., T],
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable[[Exception, int], None]] = None
) -> T:
    """
    Execute a function with retry logic (non-decorator version).
    
    Args:
        func: Function to execute
        max_retries: Maximum number of retry attempts (default: 3)
        base_delay: Initial delay in seconds (default: 1.0)
        max_delay: Maximum delay in seconds (default: 60.0)
        exponential_base: Base for exponential calculation (default: 2.0)
        exceptions: Tuple of exception types to catch and retry (default: all exceptions)
        on_retry: Optional callback function called on each retry with (exception, attempt_number)
    
    Returns:
        Result of the function call
    
    Raises:
        Exception: If all retry attempts fail
    
    Example:
        result = retry_on_failure(
            lambda: risky_operation(),
            max_retries=3,
            base_delay=1.0
        )
    """
    last_exception = None
    
    for attempt in range(max_retries + 1):
        try:
            return func()
        except exceptions as e:
            last_exception = e
            
            if attempt == max_retries:
                # Final attempt failed, raise the exception
                logger.error(
                    f"Function failed after {max_retries + 1} attempts: {str(e)}",
                    extra={
                        "attempts": max_retries + 1,
                        "error": str(e)
                    }
                )
                raise
            
            # Calculate delay with exponential backoff
            delay = min(base_delay * (exponential_base ** attempt), max_delay)
            
            logger.warning(
                f"Function failed (attempt {attempt + 1}/{max_retries + 1}), "
                f"retrying in {delay:.2f}s: {str(e)}",
                extra={
                    "attempt": attempt + 1,
                    "max_attempts": max_retries + 1,
                    "delay": delay,
                    "error": str(e)
                }
            )
            
            # Call on_retry callback if provided
            if on_retry:
                on_retry(e, attempt + 1)
            
            time.sleep(delay)
    
    # This should never be reached, but just in case
    if last_exception:
        raise last_exception
