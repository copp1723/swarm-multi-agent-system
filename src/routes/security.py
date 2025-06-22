"""
Security Routes - Security monitoring and management endpoints
"""

from datetime import datetime, timedelta, timezone

from flask import Blueprint, current_app, request # jsonify and error_response removed from imports

from src.services.auth_service import require_auth, require_permission
from src.services.security_service import (
    ValidationRule, # Keep this if used directly, or if @validate_json uses it
    rate_limit,
    security_headers,
    validate_json,
)
from src.utils.response_helpers import success_response # error_response removed
from src.exceptions import SwarmException, ValidationError # Import SwarmException

security_bp = Blueprint("security", __name__)


@security_bp.route("/health", methods=["GET"])
@security_headers
def security_health():
    """Security service health check"""
    try:
        security_service = current_app.security_service

        # Get basic security status
        recent_events = security_service.get_recent_security_events(limit=10)
        blocked_ips_count = len(security_service.blocked_ips)

        return success_response(
            {
                "service": "Security Service",
                "status": "healthy",
                "recent_events_count": len(recent_events),
                "blocked_ips_count": blocked_ips_count,
                "rate_limit_rules": list(security_service.rate_limit_rules.keys()),
            }
        )

    except Exception as e:
        # Log the original error for debugging
        current_app.logger.error(f"Security service health check failed: {e}")
        raise SwarmException("Security service health check failed.", error_code="SECURITY_HEALTH_CHECK_FAILED", details={"original_error": str(e)}, status_code=500)


@security_bp.route("/events", methods=["GET"])
@require_auth
@require_permission("security.read")
@rate_limit("api")
@security_headers
def get_security_events():
    """Get security events (admin only)"""
    try:
        security_service = current_app.security_service

        # Get query parameters
        limit = min(int(request.args.get("limit", 100)), 1000)
        severity = request.args.get("severity")
        hours = int(request.args.get("hours", 24))

        # Get events
        events = security_service.get_recent_security_events(limit=limit, severity=severity)

        # Filter by time if specified
        if hours:
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
            events = [e for e in events if e.timestamp > cutoff_time]

        # Convert to dict for JSON response
        events_data = []
        for event in events:
            events_data.append(
                {
                    "timestamp": event.timestamp.isoformat(),
                    "event_type": event.event_type,
                    "user_id": event.user_id,
                    "ip_address": event.ip_address,
                    "user_agent": event.user_agent,
                    "endpoint": event.endpoint,
                    "details": event.details,
                    "severity": event.severity,
                }
            )

        return success_response(
            {
                "events": events_data,
                "total_count": len(events_data),
                "filters": {"limit": limit, "severity": severity, "hours": hours},
            }
        )

    except Exception as e:
        current_app.logger.error(f"Failed to get security events: {e}")
        raise SwarmException("Failed to get security events.", error_code="GET_SECURITY_EVENTS_FAILED", details={"original_error": str(e)}, status_code=500)


@security_bp.route("/blocked-ips", methods=["GET"])
@require_auth
@require_permission("security.read")
@rate_limit("api")
@security_headers
def get_blocked_ips():
    """Get list of blocked IP addresses"""
    try:
        security_service = current_app.security_service

        return success_response(
            {
                "blocked_ips": list(security_service.blocked_ips),
                "count": len(security_service.blocked_ips),
            }
        )

    except Exception as e:
        current_app.logger.error(f"Failed to get blocked IPs: {e}")
        raise SwarmException("Failed to get blocked IPs.", error_code="GET_BLOCKED_IPS_FAILED", details={"original_error": str(e)}, status_code=500)


@security_bp.route("/blocked-ips", methods=["POST"])
@require_auth
@require_permission("security.write")
@rate_limit("api")
@validate_json(
    [
        ValidationRule("ip_address", required=True, pattern=r"^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$"),
        ValidationRule("reason", required=False, max_length=255),
    ]
)
@security_headers
def block_ip():
    """Block an IP address"""
    try:
        from flask import g

        data = g.validated_data

        security_service = current_app.security_service
        ip_address = data["ip_address"]
        reason = data.get("reason", "Manually blocked by admin")

        security_service.block_ip(ip_address, reason)

        return success_response(
            {
                "message": f"IP address {ip_address} has been blocked",
                "ip_address": ip_address,
                "reason": reason,
            }
        )
    # @validate_json decorator should raise ValidationError if input is bad.
    # That will be caught by the global SwarmException handler.
    except ValidationError:
        raise
    except Exception as e:
        current_app.logger.error(f"Failed to block IP: {e}")
        raise SwarmException("Failed to block IP.", error_code="BLOCK_IP_FAILED", details={"original_error": str(e)}, status_code=500)


@security_bp.route("/blocked-ips/<ip_address>", methods=["DELETE"])
@require_auth
@require_permission("security.write")
@rate_limit("api")
@security_headers
def unblock_ip(ip_address):
    """Unblock an IP address"""
    try:
        security_service = current_app.security_service

        unblocked = security_service.unblock_ip(ip_address)

        if unblocked:
            # The log_security_event is now handled by the service method.
            return success_response(
                {"message": f"IP address {ip_address} has been unblocked", "ip_address": ip_address}
            )
        else:
            # Specific error for resource not found (IP was not in the blocked list)
            raise SwarmException(f"IP address {ip_address} was not found in the blocked list or could not be unblocked.", error_code="IP_NOT_UNBLOCKED", status_code=404)
    except SwarmException: # Re-raise SwarmExceptions (like the one for IP_NOT_UNBLOCKED)
        raise
    except Exception as e:
        current_app.logger.error(f"Failed to unblock IP: {e}")
        raise SwarmException("Failed to unblock IP.", error_code="UNBLOCK_IP_FAILED", details={"original_error": str(e)}, status_code=500)


@security_bp.route("/rate-limits", methods=["GET"])
@require_auth
@require_permission("security.read")
@rate_limit("api")
@security_headers
def get_rate_limits():
    """Get current rate limit configuration"""
    try:
        security_service = current_app.security_service

        rules_data = {}
        for name, rule in security_service.rate_limit_rules.items():
            rules_data[name] = {
                "requests_per_minute": rule.requests_per_minute,
                "requests_per_hour": rule.requests_per_hour,
                "burst_limit": rule.burst_limit,
                "window_size": rule.window_size,
            }

        return success_response({"rate_limit_rules": rules_data})

    except Exception as e:
        current_app.logger.error(f"Failed to get rate limits: {e}")
        raise SwarmException("Failed to get rate limits.", error_code="GET_RATE_LIMITS_FAILED", details={"original_error": str(e)}, status_code=500)


@security_bp.route("/stats", methods=["GET"])
@require_auth
@require_permission("security.read")
@rate_limit("api")
@security_headers
def get_security_stats():
    """Get security statistics"""
    try:
        security_service = current_app.security_service

        # Get events from last 24 hours
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=24)
        recent_events = [e for e in security_service.security_events if e.timestamp > cutoff_time]

        # Count events by type
        event_counts = {}
        severity_counts = {}

        for event in recent_events:
            event_counts[event.event_type] = event_counts.get(event.event_type, 0) + 1
            severity_counts[event.severity] = severity_counts.get(event.severity, 0) + 1

        # Get top IP addresses
        ip_counts = {}
        for event in recent_events:
            ip_counts[event.ip_address] = ip_counts.get(event.ip_address, 0) + 1

        top_ips = sorted(ip_counts.items(), key=lambda x: x[1], reverse=True)[:10]

        return success_response(
            {
                "time_period": "24 hours",
                "total_events": len(recent_events),
                "events_by_type": event_counts,
                "events_by_severity": severity_counts,
                "top_ips": [{"ip": ip, "count": count} for ip, count in top_ips],
                "blocked_ips_count": len(security_service.blocked_ips),
                "rate_limit_rules_count": len(security_service.rate_limit_rules),
            }
        )

    except Exception as e:
        current_app.logger.error(f"Failed to get security stats: {e}")
        raise SwarmException("Failed to get security stats.", error_code="GET_SECURITY_STATS_FAILED", details={"original_error": str(e)}, status_code=500)


@security_bp.route("/validate", methods=["POST"])
@require_auth
@rate_limit("api")
@security_headers
def validate_input_endpoint():
    """Test input validation (for development/testing)"""
    try:
        # Basic JSON checks, though @validate_json decorator in security_service might handle this.
        # However, this route doesn't use @validate_json.
        if not request.is_json:
            raise ValidationError("JSON payload required", error_code="JSON_PAYLOAD_REQUIRED")

        data = request.get_json()
        if data is None: # Check if get_json() returned None (e.g. for empty or malformed body)
            raise ValidationError("Invalid JSON payload or empty body", error_code="JSON_INVALID")

        # Define test validation rules
        test_rules = [
            ValidationRule(
                "email", required=False, pattern=r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
            ),
            ValidationRule("username", required=False, pattern=r"^[a-zA-Z0-9_-]{3,30}$"),
            ValidationRule("password", required=False, min_length=8, max_length=128),
        ]

        security_service = current_app.security_service

        # Sanitize input
        sanitized_data = security_service.sanitize_input(data)

        # Validate input
        is_valid, errors = security_service.validate_input(sanitized_data, test_rules)

        return success_response(
            {
                "is_valid": is_valid,
                "errors": errors,
                "original_data": data,
                "sanitized_data": sanitized_data,
            }
        )
    except ValidationError: # Re-raise validation errors
        raise
    except Exception as e:
        current_app.logger.error(f"Validation test failed: {e}")
        raise SwarmException("Validation test failed.", error_code="VALIDATION_TEST_FAILED", details={"original_error": str(e)}, status_code=500)
