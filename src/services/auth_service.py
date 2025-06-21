"""
JWT Authentication Service - Secure authentication and authorization for Swarm Multi-Agent System
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Any, Dict, List, Optional

import bcrypt
import jwt
from flask import current_app, jsonify, request

from src.exceptions import AuthenticationError, SwarmException
from src.services.base_service import BaseService, handle_service_errors

logger = logging.getLogger(__name__)


@dataclass
class UserRole:
    """User role definition with permissions"""

    name: str
    permissions: List[str]
    description: str


@dataclass
class AuthUser:
    """Authenticated user information"""

    id: int
    username: str
    email: str
    roles: List[str]
    is_active: bool
    created_at: datetime
    last_login: Optional[datetime] = None


@dataclass
class TokenPayload:
    """JWT token payload structure"""

    user_id: int
    username: str
    roles: List[str]
    exp: datetime
    iat: datetime
    jti: str  # JWT ID for token revocation


class AuthenticationService(BaseService):
    """
    Comprehensive authentication and authorization service

    Features:
    - JWT token generation and validation
    - Password hashing and verification
    - Role-based access control
    - Token refresh and revocation
    - Session management
    """

    def __init__(self, secret_key: str, token_expiry_hours: int = 24):
        super().__init__("authentication")
        self.secret_key = secret_key
        self.token_expiry_hours = token_expiry_hours
        self.algorithm = "HS256"
        self.revoked_tokens = set()  # In production, use Redis or database

        # Define default roles and permissions
        self.roles = {
            "admin": UserRole(
                name="admin",
                permissions=[
                    "user.create",
                    "user.read",
                    "user.update",
                    "user.delete",
                    "agent.create",
                    "agent.read",
                    "agent.update",
                    "agent.delete",
                    "system.configure",
                    "system.monitor",
                    "system.backup",
                    "memory.read",
                    "memory.write",
                    "memory.delete",
                    "mcp.read",
                    "mcp.write",
                    "mcp.execute",
                    "email.send",
                    "email.configure",
                ],
                description="Full system access",
            ),
            "user": UserRole(
                name="user",
                permissions=[
                    "agent.read",
                    "agent.chat",
                    "memory.read",
                    "memory.write",
                    "mcp.read",
                    "mcp.write",
                    "email.send",
                ],
                description="Standard user access",
            ),
            "readonly": UserRole(
                name="readonly",
                permissions=["agent.read", "memory.read"],
                description="Read-only access",
            ),
            "api": UserRole(
                name="api",
                permissions=["agent.read", "agent.chat", "memory.read", "memory.write"],
                description="API access for external integrations",
            ),
        }

        logger.info("Authentication service initialized with JWT support")

    @handle_service_errors
    def hash_password(self, password: str) -> str:
        """Hash password using bcrypt"""
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
        return hashed.decode("utf-8")

    @handle_service_errors
    def verify_password(self, password: str, hashed: str) -> bool:
        """Verify password against hash"""
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))

    @handle_service_errors
    def generate_token(self, user: AuthUser) -> str:
        """Generate JWT token for authenticated user"""
        now = datetime.now(timezone.utc)
        exp = now + timedelta(hours=self.token_expiry_hours)

        payload = {
            "user_id": user.id,
            "username": user.username,
            "roles": user.roles,
            "exp": exp,
            "iat": now,
            "jti": f"{user.id}_{int(now.timestamp())}",  # Unique token ID
        }

        token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
        logger.info(f"Generated JWT token for user {user.username}")
        return token

    @handle_service_errors
    def validate_token(self, token: str) -> Optional[TokenPayload]:
        """Validate JWT token and return payload"""
        try:
            # Check if token is revoked
            if token in self.revoked_tokens:
                logger.warning("Attempted use of revoked token")
                return None

            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])

            return TokenPayload(
                user_id=payload["user_id"],
                username=payload["username"],
                roles=payload["roles"],
                exp=datetime.fromtimestamp(payload["exp"], timezone.utc),
                iat=datetime.fromtimestamp(payload["iat"], timezone.utc),
                jti=payload["jti"],
            )

        except jwt.ExpiredSignatureError:
            logger.warning("Token has expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token: {e}")
            return None

    @handle_service_errors
    def revoke_token(self, token: str) -> bool:
        """Revoke a JWT token"""
        payload = self.validate_token(token)
        if payload:
            self.revoked_tokens.add(token)
            logger.info(f"Revoked token for user {payload.username}")
            return True
        return False

    @handle_service_errors
    def refresh_token(self, token: str) -> Optional[str]:
        """Refresh JWT token if valid and not expired"""
        payload = self.validate_token(token)
        if not payload:
            return None

        # Check if token is close to expiry (within 1 hour)
        time_to_expiry = payload.exp - datetime.now(timezone.utc)
        if time_to_expiry.total_seconds() > 3600:  # More than 1 hour left
            return token  # No need to refresh

        # Create new token (would need user data from database)
        # This is a simplified version - in practice, fetch user from DB
        logger.info(f"Refreshing token for user {payload.username}")
        return token  # Placeholder - implement with actual user lookup

    def check_permission(self, user_roles: List[str], required_permission: str) -> bool:
        """Check if user has required permission"""
        for role_name in user_roles:
            role = self.roles.get(role_name)
            if role and required_permission in role.permissions:
                return True
        return False

    def get_user_permissions(self, user_roles: List[str]) -> List[str]:
        """Get all permissions for user roles"""
        permissions = set()
        for role_name in user_roles:
            role = self.roles.get(role_name)
            if role:
                permissions.update(role.permissions)
        return list(permissions)


# Authentication decorators
def require_auth(f):
    """Decorator to require authentication for route"""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return jsonify({"error": "Missing or invalid authorization header"}), 401

        token = auth_header.split(" ")[1]
        auth_service = current_app.auth_service
        payload = auth_service.validate_token(token)

        if not payload:
            return jsonify({"error": "Invalid or expired token"}), 401

        # Add user info to request context
        request.current_user = payload
        return f(*args, **kwargs)

    return decorated_function


def require_permission(permission: str):
    """Decorator to require specific permission"""

    def decorator(f):
        @wraps(f)
        @require_auth
        def decorated_function(*args, **kwargs):
            auth_service = current_app.auth_service
            user_roles = request.current_user.roles

            if not auth_service.check_permission(user_roles, permission):
                return jsonify({"error": f"Permission denied: {permission} required"}), 403

            return f(*args, **kwargs)

        return decorated_function

    return decorator


def require_role(role: str):
    """Decorator to require specific role"""

    def decorator(f):
        @wraps(f)
        @require_auth
        def decorated_function(*args, **kwargs):
            user_roles = request.current_user.roles

            if role not in user_roles:
                return jsonify({"error": f"Role required: {role}"}), 403

            return f(*args, **kwargs)

        return decorated_function

    return decorator


# API Key authentication for external services
def require_api_key(f):
    """Decorator to require API key authentication"""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get("X-API-Key")
        if not api_key:
            return jsonify({"error": "API key required"}), 401

        # In production, validate against database
        # For now, check against environment variable
        valid_api_keys = current_app.config.get("VALID_API_KEYS", [])
        if api_key not in valid_api_keys:
            return jsonify({"error": "Invalid API key"}), 401

        # Set API user context
        request.current_user = TokenPayload(
            user_id=0,
            username="api_user",
            roles=["api"],
            exp=datetime.now(timezone.utc) + timedelta(hours=1),
            iat=datetime.now(timezone.utc),
            jti="api_key",
        )

        return f(*args, **kwargs)

    return decorated_function
