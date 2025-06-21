"""
Base service class with robust error handling and retry logic
"""
import time
import logging
import requests
from typing import Dict, Any, Optional, Callable
from functools import wraps
from src.config import config
from src.exceptions import (
    ServiceUnavailableError, 
    AuthenticationError, 
    RateLimitError,
    SwarmException
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BaseService:
    """Base class for all external service integrations"""
    
    def __init__(self, service_name: str):
        self.service_name = service_name
        self.session = requests.Session()
        self.session.timeout = config.api_timeout
        
    def _make_request(self, method: str, url: str, **kwargs) -> requests.Response:
        """Make HTTP request with proper error handling and retries"""
        
        for attempt in range(config.max_retries):
            try:
                logger.info(f"Making {method} request to {url} (attempt {attempt + 1})")
                
                response = self.session.request(method, url, **kwargs)
                
                # Handle different HTTP status codes appropriately
                if response.status_code == 200:
                    return response
                elif response.status_code == 401:
                    raise AuthenticationError(
                        f"Authentication failed for {self.service_name}",
                        error_code="AUTH_FAILED",
                        details={"status_code": response.status_code, "response": response.text}
                    )
                elif response.status_code == 429:
                    raise RateLimitError(
                        f"Rate limit exceeded for {self.service_name}",
                        error_code="RATE_LIMIT",
                        details={"status_code": response.status_code, "retry_after": response.headers.get("Retry-After")}
                    )
                elif response.status_code >= 500:
                    # Server error - retry
                    if attempt < config.max_retries - 1:
                        wait_time = 2 ** attempt  # Exponential backoff
                        logger.warning(f"Server error {response.status_code}, retrying in {wait_time}s")
                        time.sleep(wait_time)
                        continue
                    else:
                        raise ServiceUnavailableError(
                            f"{self.service_name} service unavailable",
                            error_code="SERVICE_UNAVAILABLE",
                            details={"status_code": response.status_code, "response": response.text}
                        )
                else:
                    # Client error - don't retry
                    raise SwarmException(
                        f"Request failed with status {response.status_code}",
                        error_code="REQUEST_FAILED",
                        details={"status_code": response.status_code, "response": response.text}
                    )
                    
            except requests.exceptions.Timeout:
                if attempt < config.max_retries - 1:
                    wait_time = 2 ** attempt
                    logger.warning(f"Request timeout, retrying in {wait_time}s")
                    time.sleep(wait_time)
                    continue
                else:
                    raise ServiceUnavailableError(
                        f"Timeout connecting to {self.service_name}",
                        error_code="TIMEOUT",
                        details={"timeout": config.api_timeout}
                    )
                    
            except requests.exceptions.ConnectionError:
                if attempt < config.max_retries - 1:
                    wait_time = 2 ** attempt
                    logger.warning(f"Connection error, retrying in {wait_time}s")
                    time.sleep(wait_time)
                    continue
                else:
                    raise ServiceUnavailableError(
                        f"Cannot connect to {self.service_name}",
                        error_code="CONNECTION_ERROR"
                    )
                    
        # Should never reach here, but just in case
        raise ServiceUnavailableError(f"Max retries exceeded for {self.service_name}")
    
    def get(self, url: str, **kwargs) -> requests.Response:
        """Make GET request with error handling"""
        return self._make_request("GET", url, **kwargs)
    
    def post(self, url: str, **kwargs) -> requests.Response:
        """Make POST request with error handling"""
        return self._make_request("POST", url, **kwargs)
    
    def put(self, url: str, **kwargs) -> requests.Response:
        """Make PUT request with error handling"""
        return self._make_request("PUT", url, **kwargs)
    
    def delete(self, url: str, **kwargs) -> requests.Response:
        """Make DELETE request with error handling"""
        return self._make_request("DELETE", url, **kwargs)

def handle_service_errors(func: Callable) -> Callable:
    """Decorator to handle service errors consistently"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except SwarmException:
            # Re-raise our custom exceptions
            raise
        except Exception as e:
            # Convert unexpected exceptions to SwarmException
            logger.error(f"Unexpected error in {func.__name__}: {str(e)}")
            raise SwarmException(
                f"Unexpected error in {func.__name__}",
                error_code="UNEXPECTED_ERROR",
                details={"original_error": str(e)}
            )
    return wrapper

