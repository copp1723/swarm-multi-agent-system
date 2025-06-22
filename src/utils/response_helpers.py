"""
Response helpers for consistent API responses
"""

from typing import Any, Dict, Optional

from src.exceptions import SwarmException


def create_success_response(data: Any, message: str = "Success") -> Dict[str, Any]:
    """Create a standardized success response"""
    return {"success": True, "message": message, "data": data}


def create_error_response(error: SwarmException) -> Dict[str, Any]:
    """Create a standardized error response from a SwarmException instance."""
    return {
        "success": False,
        "error": {"code": error.error_code, "message": error.message, "details": error.details},
    }

# success_response alias removed.
# create_error_response signature changed (status_code parameter removed).
# The error_response(message, error_code, details) function is now removed.
# All routes should raise SwarmException or its derivatives.
# The global error handler in main.py will use create_error_response(SwarmException)
# or construct the JSON response directly.
