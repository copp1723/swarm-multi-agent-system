"""
Custom exceptions for the Swarm Multi-Agent System
Provides specific exception types for different failure modes
"""


class SwarmException(Exception):
    """Base exception for all Swarm system errors"""

    def __init__(self, message: str, error_code: str = None, details: dict = None):
        super().__init__(message)
        self.message = message
        self.error_code = error_code or self.__class__.__name__
        self.details = details or {}


class ConfigurationError(SwarmException):
    """Raised when configuration is invalid or missing"""

    pass


class ServiceUnavailableError(SwarmException):
    """Raised when an external service is unavailable"""

    pass


class ServiceError(SwarmException):
    """Raised when service operations fail"""

    pass


class AuthenticationError(SwarmException):
    """Raised when API authentication fails"""

    pass


class ValidationError(SwarmException):
    """Raised when input validation fails"""

    pass


class AgentNotFoundError(SwarmException):
    """Raised when a requested agent doesn't exist"""

    pass


class ConversationError(SwarmException):
    """Raised when conversation operations fail"""

    pass


class FileSystemError(SwarmException):
    """Raised when file system operations fail"""

    pass


class EmailError(SwarmException):
    """Raised when email operations fail"""

    pass


class RateLimitError(SwarmException):
    """Raised when rate limits are exceeded"""

    pass


class ModelError(SwarmException):
    """Raised when AI model operations fail"""

    pass
