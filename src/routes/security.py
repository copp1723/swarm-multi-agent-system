"""
Security Routes - Security monitoring and management endpoints
"""

from flask import Blueprint, request, jsonify, current_app
from datetime import datetime, timezone, timedelta

from src.services.auth_service import require_auth, require_permission
from src.services.security_service import rate_limit, validate_json, security_headers, ValidationRule
from src.utils.response_helpers import success_response, error_response

security_bp = Blueprint('security', __name__)

@security_bp.route('/health', methods=['GET'])
@security_headers
def security_health():
    """Security service health check"""
    try:
        security_service = current_app.security_service
        
        # Get basic security status
        recent_events = security_service.get_recent_security_events(limit=10)
        blocked_ips_count = len(security_service.blocked_ips)
        
        return success_response({
            'service': 'Security Service',
            'status': 'healthy',
            'recent_events_count': len(recent_events),
            'blocked_ips_count': blocked_ips_count,
            'rate_limit_rules': list(security_service.rate_limit_rules.keys())
        })
    
    except Exception as e:
        return error_response(f"Security service health check failed: {str(e)}", 500)

@security_bp.route('/events', methods=['GET'])
@require_auth
@require_permission('security.read')
@rate_limit('api')
@security_headers
def get_security_events():
    """Get security events (admin only)"""
    try:
        security_service = current_app.security_service
        
        # Get query parameters
        limit = min(int(request.args.get('limit', 100)), 1000)
        severity = request.args.get('severity')
        hours = int(request.args.get('hours', 24))
        
        # Get events
        events = security_service.get_recent_security_events(limit=limit, severity=severity)
        
        # Filter by time if specified
        if hours:
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
            events = [e for e in events if e.timestamp > cutoff_time]
        
        # Convert to dict for JSON response
        events_data = []
        for event in events:
            events_data.append({
                'timestamp': event.timestamp.isoformat(),
                'event_type': event.event_type,
                'user_id': event.user_id,
                'ip_address': event.ip_address,
                'user_agent': event.user_agent,
                'endpoint': event.endpoint,
                'details': event.details,
                'severity': event.severity
            })
        
        return success_response({
            'events': events_data,
            'total_count': len(events_data),
            'filters': {
                'limit': limit,
                'severity': severity,
                'hours': hours
            }
        })
    
    except Exception as e:
        return error_response(f"Failed to get security events: {str(e)}", 500)

@security_bp.route('/blocked-ips', methods=['GET'])
@require_auth
@require_permission('security.read')
@rate_limit('api')
@security_headers
def get_blocked_ips():
    """Get list of blocked IP addresses"""
    try:
        security_service = current_app.security_service
        
        return success_response({
            'blocked_ips': list(security_service.blocked_ips),
            'count': len(security_service.blocked_ips)
        })
    
    except Exception as e:
        return error_response(f"Failed to get blocked IPs: {str(e)}", 500)

@security_bp.route('/blocked-ips', methods=['POST'])
@require_auth
@require_permission('security.write')
@rate_limit('api')
@validate_json([
    ValidationRule('ip_address', required=True, pattern=r'^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$'),
    ValidationRule('reason', required=False, max_length=255)
])
@security_headers
def block_ip():
    """Block an IP address"""
    try:
        from flask import g
        data = g.validated_data
        
        security_service = current_app.security_service
        ip_address = data['ip_address']
        reason = data.get('reason', 'Manually blocked by admin')
        
        security_service.block_ip(ip_address, reason)
        
        return success_response({
            'message': f'IP address {ip_address} has been blocked',
            'ip_address': ip_address,
            'reason': reason
        })
    
    except Exception as e:
        return error_response(f"Failed to block IP: {str(e)}", 500)

@security_bp.route('/blocked-ips/<ip_address>', methods=['DELETE'])
@require_auth
@require_permission('security.write')
@rate_limit('api')
@security_headers
def unblock_ip(ip_address):
    """Unblock an IP address"""
    try:
        security_service = current_app.security_service
        
        if ip_address in security_service.blocked_ips:
            security_service.blocked_ips.remove(ip_address)
            
            # Log the unblock event
            security_service.log_security_event(
                event_type='ip_unblocked',
                user_id=request.current_user.user_id if hasattr(request, 'current_user') else None,
                ip_address=security_service.get_client_ip(request),
                user_agent=request.headers.get('User-Agent', ''),
                endpoint=request.endpoint,
                details={'unblocked_ip': ip_address},
                severity='medium'
            )
            
            return success_response({
                'message': f'IP address {ip_address} has been unblocked',
                'ip_address': ip_address
            })
        else:
            return error_response(f'IP address {ip_address} is not blocked', 404)
    
    except Exception as e:
        return error_response(f"Failed to unblock IP: {str(e)}", 500)

@security_bp.route('/rate-limits', methods=['GET'])
@require_auth
@require_permission('security.read')
@rate_limit('api')
@security_headers
def get_rate_limits():
    """Get current rate limit configuration"""
    try:
        security_service = current_app.security_service
        
        rules_data = {}
        for name, rule in security_service.rate_limit_rules.items():
            rules_data[name] = {
                'requests_per_minute': rule.requests_per_minute,
                'requests_per_hour': rule.requests_per_hour,
                'burst_limit': rule.burst_limit,
                'window_size': rule.window_size
            }
        
        return success_response({
            'rate_limit_rules': rules_data
        })
    
    except Exception as e:
        return error_response(f"Failed to get rate limits: {str(e)}", 500)

@security_bp.route('/stats', methods=['GET'])
@require_auth
@require_permission('security.read')
@rate_limit('api')
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
        
        return success_response({
            'time_period': '24 hours',
            'total_events': len(recent_events),
            'events_by_type': event_counts,
            'events_by_severity': severity_counts,
            'top_ips': [{'ip': ip, 'count': count} for ip, count in top_ips],
            'blocked_ips_count': len(security_service.blocked_ips),
            'rate_limit_rules_count': len(security_service.rate_limit_rules)
        })
    
    except Exception as e:
        return error_response(f"Failed to get security stats: {str(e)}", 500)

@security_bp.route('/validate', methods=['POST'])
@require_auth
@rate_limit('api')
@security_headers
def validate_input_endpoint():
    """Test input validation (for development/testing)"""
    try:
        if not request.is_json:
            return error_response('JSON payload required', 400)
        
        data = request.get_json()
        if not data:
            return error_response('Invalid JSON payload', 400)
        
        # Define test validation rules
        test_rules = [
            ValidationRule('email', required=False, pattern=r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'),
            ValidationRule('username', required=False, pattern=r'^[a-zA-Z0-9_-]{3,30}$'),
            ValidationRule('password', required=False, min_length=8, max_length=128)
        ]
        
        security_service = current_app.security_service
        
        # Sanitize input
        sanitized_data = security_service.sanitize_input(data)
        
        # Validate input
        is_valid, errors = security_service.validate_input(sanitized_data, test_rules)
        
        return success_response({
            'is_valid': is_valid,
            'errors': errors,
            'original_data': data,
            'sanitized_data': sanitized_data
        })
    
    except Exception as e:
        return error_response(f"Validation test failed: {str(e)}", 500)

