"""
Response helpers for consistent API responses
"""

from typing import Dict, Any, Optional
from src.exceptions import SwarmException

def create_success_response(data: Any, message: str = "Success") -> Dict[str, Any]:
    """Create a standardized success response"""
    return {
        "success": True,
        "message": message,
        "data": data
    }

def create_error_response(error: SwarmException, status_code: int = 500) -> Dict[str, Any]:
    """Create a standardized error response"""
    return {
        "success": False,
        "error": {
            "code": error.error_code,
            "message": error.message,
            "details": error.details
        }
    }

def success_response(data: Any, message: str = "Success") -> Dict[str, Any]:
    """Create a standardized success response (alias for create_success_response)"""
    return create_success_response(data, message)

def error_response(message: str, error_code: str = "ERROR", details: Dict[str, Any] = None) -> Dict[str, Any]:
    """Create a standardized error response"""
    return {
        "success": False,
        "error": {
            "code": error_code,
            "message": message,
            "details": details or {}
        }
    }

