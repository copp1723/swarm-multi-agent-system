"""
Security Hardening Service - Rate limiting, input validation, and audit logging
"""

import hashlib
import ipaddress
import logging
import re
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Any, Dict, List, Optional, Tuple

from flask import current_app, g, jsonify, request

from src.exceptions import SwarmException
from src.services.base_service import BaseService, handle_service_errors

logger = logging.getLogger(__name__)


@dataclass
class RateLimitRule:
    """Rate limiting rule configuration"""

    requests_per_minute: int
    requests_per_hour: int
    burst_limit: int
    window_size: int = 60  # seconds


@dataclass
class SecurityEvent:
    """Security event for audit logging"""

    timestamp: datetime
    event_type: str
    user_id: Optional[int]
    ip_address: str
    user_agent: str
    endpoint: str
    details: Dict[str, Any]
    severity: str  # low, medium, high, critical


@dataclass
class ValidationRule:
    """Input validation rule"""

    field_name: str
    required: bool = False
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    pattern: Optional[str] = None
    allowed_values: Optional[List[str]] = None
    custom_validator: Optional[callable] = None


class SecurityHardeningService(BaseService):
    """
    Comprehensive security hardening service

    Features:
    - Rate limiting with configurable rules
    - Input validation and sanitization
    - Audit logging for security events
    - IP blocking and allowlisting
    - Request fingerprinting
    - Attack detection and prevention
    """

    def __init__(self, config: dict):
        super().__init__("security")
        self.config = config

        # Rate limiting storage (in production, use Redis)
        self.rate_limit_storage = defaultdict(lambda: defaultdict(deque))
        self.blocked_ips = set()
        self.allowed_ips = set()

        # Security events storage (in production, use database)
        self.security_events = deque(maxlen=10000)

        # Rate limiting rules
        self.rate_limit_rules = {
            "default": RateLimitRule(
                requests_per_minute=60, requests_per_hour=1000, burst_limit=10
            ),
            "auth": RateLimitRule(requests_per_minute=10, requests_per_hour=100, burst_limit=3),
            "api": RateLimitRule(requests_per_minute=100, requests_per_hour=5000, burst_limit=20),
        }

        # Common validation patterns
        self.validation_patterns = {
            "email": r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$",
            "username": r"^[a-zA-Z0-9_-]{3,30}$",
            "password": r"^.{8,128}$",
            "uuid": r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
            "filename": r"^[a-zA-Z0-9._-]{1,255}$",
            "path": r"^[a-zA-Z0-9/._-]{1,1000}$",
        }

        logger.info("Security hardening service initialized")

    def get_client_identifier(self, request) -> str:
        """Get unique client identifier for rate limiting"""
        # Use IP address as primary identifier
        ip = self.get_client_ip(request)

        # Add user ID if authenticated
        user_id = getattr(request, "current_user", None)
        if user_id:
            return f"user:{user_id.user_id}"

        return f"ip:{ip}"

    def get_client_ip(self, request) -> str:
        """Get client IP address, handling proxies"""
        # Check for forwarded headers (be careful with these in production)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # Take the first IP in the chain
            ip = forwarded_for.split(",")[0].strip()
            try:
                ipaddress.ip_address(ip)
                return ip
            except ValueError:
                pass

        # Check other proxy headers
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            try:
                ipaddress.ip_address(real_ip)
                return real_ip
            except ValueError:
                pass

        # Fall back to remote address
        return request.remote_addr or "127.0.0.1"

    @handle_service_errors
    def check_rate_limit(self, request, rule_name: str = "default") -> Tuple[bool, Dict[str, Any]]:
        """Check if request is within rate limits"""
        client_id = self.get_client_identifier(request)
        rule = self.rate_limit_rules.get(rule_name, self.rate_limit_rules["default"])
        current_time = time.time()

        # Get client's request history
        client_requests = self.rate_limit_storage[client_id]
        minute_requests = client_requests["minute"]
        hour_requests = client_requests["hour"]

        # Clean old requests
        minute_cutoff = current_time - 60
        hour_cutoff = current_time - 3600

        while minute_requests and minute_requests[0] < minute_cutoff:
            minute_requests.popleft()

        while hour_requests and hour_requests[0] < hour_cutoff:
            hour_requests.popleft()

        # Check limits
        minute_count = len(minute_requests)
        hour_count = len(hour_requests)

        # Check burst limit (requests in last 10 seconds)
        burst_cutoff = current_time - 10
        burst_count = sum(1 for req_time in minute_requests if req_time > burst_cutoff)

        rate_limit_info = {
            "requests_per_minute": minute_count,
            "requests_per_hour": hour_count,
            "burst_requests": burst_count,
            "limits": {
                "minute": rule.requests_per_minute,
                "hour": rule.requests_per_hour,
                "burst": rule.burst_limit,
            },
            "reset_time": int(current_time + 60),
        }

        # Check if limits exceeded
        if (
            minute_count >= rule.requests_per_minute
            or hour_count >= rule.requests_per_hour
            or burst_count >= rule.burst_limit
        ):

            # Log rate limit violation
            self.log_security_event(
                event_type="rate_limit_exceeded",
                user_id=getattr(request, "current_user", None),
                ip_address=self.get_client_ip(request),
                user_agent=request.headers.get("User-Agent", ""),
                endpoint=request.endpoint or request.path,
                details={
                    "rule_name": rule_name,
                    "client_id": client_id,
                    "rate_limit_info": rate_limit_info,
                },
                severity="medium",
            )

            return False, rate_limit_info

        # Record this request
        minute_requests.append(current_time)
        hour_requests.append(current_time)

        return True, rate_limit_info

    @handle_service_errors
    def validate_input(
        self, data: Dict[str, Any], rules: List[ValidationRule]
    ) -> Tuple[bool, List[str]]:
        """Validate input data against rules"""
        errors = []

        for rule in rules:
            value = data.get(rule.field_name)

            # Check required fields
            if rule.required and (value is None or value == ""):
                errors.append(f"{rule.field_name} is required")
                continue

            # Skip validation for optional empty fields
            if value is None or value == "":
                continue

            # Convert to string for validation
            str_value = str(value)

            # Length validation
            if rule.min_length and len(str_value) < rule.min_length:
                errors.append(f"{rule.field_name} must be at least {rule.min_length} characters")

            if rule.max_length and len(str_value) > rule.max_length:
                errors.append(
                    f"{rule.field_name} must be no more than {rule.max_length} characters"
                )

            # Pattern validation
            if rule.pattern:
                if not re.match(rule.pattern, str_value):
                    errors.append(f"{rule.field_name} format is invalid")

            # Allowed values validation
            if rule.allowed_values and str_value not in rule.allowed_values:
                errors.append(f"{rule.field_name} must be one of: {', '.join(rule.allowed_values)}")

            # Custom validation
            if rule.custom_validator:
                try:
                    if not rule.custom_validator(value):
                        errors.append(f"{rule.field_name} failed custom validation")
                except Exception as e:
                    errors.append(f"{rule.field_name} validation error: {str(e)}")

        return len(errors) == 0, errors

    def sanitize_input(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize input data to prevent injection attacks"""
        sanitized = {}

        for key, value in data.items():
            if isinstance(value, str):
                # Remove null bytes
                value = value.replace("\x00", "")

                # Limit length to prevent DoS
                if len(value) > 10000:
                    value = value[:10000]

                # Basic HTML entity encoding for display
                value = (
                    value.replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
                    .replace('"', "&quot;")
                    .replace("'", "&#x27;")
                )

            sanitized[key] = value

        return sanitized

    def log_security_event(
        self,
        event_type: str,
        user_id: Optional[int],
        ip_address: str,
        user_agent: str,
        endpoint: str,
        details: Dict[str, Any],
        severity: str = "low",
    ):
        """Log security event for audit trail"""
        event = SecurityEvent(
            timestamp=datetime.now(timezone.utc),
            event_type=event_type,
            user_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
            endpoint=endpoint,
            details=details,
            severity=severity,
        )

        self.security_events.append(event)

        # Log to application logger
        log_level = {
            "low": logging.INFO,
            "medium": logging.WARNING,
            "high": logging.ERROR,
            "critical": logging.CRITICAL,
        }.get(severity, logging.INFO)

        logger.log(log_level, f"Security event: {event_type} from {ip_address} on {endpoint}")

    def check_ip_blocked(self, ip_address: str) -> bool:
        """Check if IP address is blocked"""
        return ip_address in self.blocked_ips

    def block_ip(self, ip_address: str, reason: str = "Security violation"):
        """Block an IP address"""
        self.blocked_ips.add(ip_address)

        self.log_security_event(
            event_type="ip_blocked",
            user_id=None,
            ip_address=ip_address,
            user_agent="",
            endpoint="",
            details={"reason": reason},
            severity="high",
        )

    def get_security_headers(self) -> Dict[str, str]:
        """Get security headers to add to responses"""
        return {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://cdn.tailwindcss.com https://cdn.socket.io; style-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com; connect-src 'self' ws: wss:",
            "Referrer-Policy": "strict-origin-when-cross-origin",
        }

    def get_recent_security_events(
        self, limit: int = 100, severity: Optional[str] = None
    ) -> List[SecurityEvent]:
        """Get recent security events"""
        events = list(self.security_events)

        if severity:
            events = [e for e in events if e.severity == severity]

        # Sort by timestamp (most recent first)
        events.sort(key=lambda x: x.timestamp, reverse=True)

        return events[:limit]


# Security decorators
def rate_limit(rule_name: str = "default"):
    """Decorator to apply rate limiting to routes"""

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            security_service = current_app.security_service

            allowed, rate_info = security_service.check_rate_limit(request, rule_name)

            if not allowed:
                response = jsonify({"error": "Rate limit exceeded", "rate_limit": rate_info})
                response.status_code = 429
                response.headers["Retry-After"] = str(rate_info["reset_time"] - int(time.time()))
                return response

            # Add rate limit info to response headers
            response = f(*args, **kwargs)
            if hasattr(response, "headers"):
                response.headers["X-RateLimit-Limit"] = str(rate_info["limits"]["minute"])
                response.headers["X-RateLimit-Remaining"] = str(
                    rate_info["limits"]["minute"] - rate_info["requests_per_minute"]
                )
                response.headers["X-RateLimit-Reset"] = str(rate_info["reset_time"])

            return response

        return decorated_function

    return decorator


def validate_json(validation_rules: List[ValidationRule]):
    """Decorator to validate JSON input"""

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not request.is_json:
                return jsonify({"error": "JSON payload required"}), 400

            data = request.get_json()
            if not data:
                return jsonify({"error": "Invalid JSON payload"}), 400

            security_service = current_app.security_service

            # Sanitize input
            data = security_service.sanitize_input(data)

            # Validate input
            is_valid, errors = security_service.validate_input(data, validation_rules)

            if not is_valid:
                return jsonify({"error": "Validation failed", "details": errors}), 400

            # Store sanitized data for use in route
            g.validated_data = data

            return f(*args, **kwargs)

        return decorated_function

    return decorator


def security_headers(f):
    """Decorator to add security headers to responses"""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        response = f(*args, **kwargs)

        if hasattr(current_app, "security_service"):
            security_service = current_app.security_service
            headers = security_service.get_security_headers()

            if hasattr(response, "headers"):
                for key, value in headers.items():
                    response.headers[key] = value

        return response

    return decorated_function


def block_suspicious_ips(f):
    """Decorator to block suspicious IP addresses"""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        security_service = current_app.security_service
        client_ip = security_service.get_client_ip(request)

        if security_service.check_ip_blocked(client_ip):
            security_service.log_security_event(
                event_type="blocked_ip_attempt",
                user_id=None,
                ip_address=client_ip,
                user_agent=request.headers.get("User-Agent", ""),
                endpoint=request.endpoint or request.path,
                details={},
                severity="high",
            )

            return jsonify({"error": "Access denied"}), 403

        return f(*args, **kwargs)

    return decorated_function
