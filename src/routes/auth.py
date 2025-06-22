"""
Authentication Routes - Login, logout, registration, and user management endpoints
"""

import logging
from datetime import datetime, timezone

from flask import Blueprint, current_app, jsonify, request

from src.models.user import User, db
from src.services.auth_service import AuthUser, require_auth, require_permission, require_role
from src.utils.response_helpers import success_response, error_response


def validation_error_response(message: str, field: str = None):
    """Helper function for validation errors"""
    error_data = {"message": message}
    if field:
        error_data["field"] = field
    return error_response(message, 400, error_data)


logger = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["POST"])
def login():
    """
    User login endpoint

    Expected payload:
    {
        "username": "user@example.com",
        "password": "password123"
    }
    """
    try:
        data = request.get_json()
        if not data:
            return validation_error_response("JSON payload required")

        username = data.get("username", "").strip()
        password = data.get("password", "")

        if not username or not password:
            return validation_error_response("Username and password required")

        # Find user by username or email
        user = User.query.filter((User.username == username) | (User.email == username)).first()

        if not user:
            logger.warning(f"Login attempt with non-existent username: {username}")
            return error_response("Invalid credentials", 401)

        if not user.is_active:
            logger.warning(f"Login attempt for inactive user: {username}")
            return error_response("Account is disabled", 401)

        # Verify password
        auth_service = current_app.auth_service
        if not auth_service.verify_password(password, user.password_hash):
            logger.warning(f"Failed login attempt for user: {username}")
            return error_response("Invalid credentials", 401)

        # Update last login
        user.last_login = datetime.now(timezone.utc)
        db.session.commit()

        # Create auth user object
        auth_user = AuthUser(
            id=user.id,
            username=user.username,
            email=user.email,
            roles=user.roles.split(",") if user.roles else ["user"],
            is_active=user.is_active,
            created_at=user.created_at,
            last_login=user.last_login,
        )

        # Generate JWT token
        token = auth_service.generate_token(auth_user)

        logger.info(f"Successful login for user: {username}")

        return success_response(
            {
                "token": token,
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "roles": auth_user.roles,
                    "permissions": auth_service.get_user_permissions(auth_user.roles),
                },
            }
        )

    except Exception as e:
        logger.error(f"Login error: {e}")
        return error_response("Login failed", 500)


@auth_bp.route("/register", methods=["POST"])
def register():
    """
    User registration endpoint

    Expected payload:
    {
        "username": "newuser",
        "email": "user@example.com",
        "password": "password123",
        "confirm_password": "password123"
    }
    """
    try:
        data = request.get_json()
        if not data:
            return validation_error_response("JSON payload required")

        username = data.get("username", "").strip()
        email = data.get("email", "").strip().lower()
        password = data.get("password", "")
        confirm_password = data.get("confirm_password", "")

        # Validation
        if not all([username, email, password, confirm_password]):
            return validation_error_response("All fields are required")

        if password != confirm_password:
            return validation_error_response("Passwords do not match")

        if len(password) < 8:
            return validation_error_response("Password must be at least 8 characters")

        if len(username) < 3:
            return validation_error_response("Username must be at least 3 characters")

        if "@" not in email:
            return validation_error_response("Valid email address required")

        # Check if user already exists
        existing_user = User.query.filter(
            (User.username == username) | (User.email == email)
        ).first()

        if existing_user:
            if existing_user.username == username:
                return validation_error_response("Username already exists")
            else:
                return validation_error_response("Email already registered")

        # Hash password
        auth_service = current_app.auth_service
        password_hash = auth_service.hash_password(password)

        # Create new user
        new_user = User(
            username=username,
            email=email,
            password_hash=password_hash,
            roles="user",  # Default role
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )

        db.session.add(new_user)
        db.session.commit()

        logger.info(f"New user registered: {username}")

        return success_response(
            {
                "message": "User registered successfully",
                "user": {
                    "id": new_user.id,
                    "username": new_user.username,
                    "email": new_user.email,
                    "roles": ["user"],
                },
            },
            201,
        )

    except Exception as e:
        logger.error(f"Registration error: {e}")
        db.session.rollback()
        return error_response("Registration failed", 500)


@auth_bp.route("/logout", methods=["POST"])
@require_auth
def logout():
    """Logout endpoint - revokes the current token"""
    try:
        auth_header = request.headers.get("Authorization")
        token = auth_header.split(" ")[1]

        auth_service = current_app.auth_service
        auth_service.revoke_token(token)

        logger.info(f"User logged out: {request.current_user.username}")

        return success_response({"message": "Logged out successfully"})

    except Exception as e:
        logger.error(f"Logout error: {e}")
        return error_response("Logout failed", 500)


@auth_bp.route("/refresh", methods=["POST"])
@require_auth
def refresh_token():
    """Refresh JWT token"""
    try:
        auth_header = request.headers.get("Authorization")
        token = auth_header.split(" ")[1]

        auth_service = current_app.auth_service
        new_token = auth_service.refresh_token(token)

        if new_token:
            return success_response({"token": new_token})
        else:
            return error_response("Token refresh failed", 401)

    except Exception as e:
        logger.error(f"Token refresh error: {e}")
        return error_response("Token refresh failed", 500)


@auth_bp.route("/me", methods=["GET"])
@require_auth
def get_current_user():
    """Get current user information"""
    try:
        user = User.query.get(request.current_user.user_id)
        if not user:
            return error_response("User not found", 404)

        auth_service = current_app.auth_service
        user_roles = user.roles.split(",") if user.roles else ["user"]

        return success_response(
            {
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "roles": user_roles,
                    "permissions": auth_service.get_user_permissions(user_roles),
                    "is_active": user.is_active,
                    "created_at": user.created_at.isoformat(),
                    "last_login": user.last_login.isoformat() if user.last_login else None,
                }
            }
        )

    except Exception as e:
        logger.error(f"Get current user error: {e}")
        return error_response("Failed to get user information", 500)


@auth_bp.route("/change-password", methods=["POST"])
@require_auth
def change_password():
    """Change user password"""
    try:
        data = request.get_json()
        if not data:
            return validation_error_response("JSON payload required")

        current_password = data.get("current_password", "")
        new_password = data.get("new_password", "")
        confirm_password = data.get("confirm_password", "")

        if not all([current_password, new_password, confirm_password]):
            return validation_error_response("All fields are required")

        if new_password != confirm_password:
            return validation_error_response("New passwords do not match")

        if len(new_password) < 8:
            return validation_error_response("Password must be at least 8 characters")

        # Get current user
        user = User.query.get(request.current_user.user_id)
        if not user:
            return error_response("User not found", 404)

        # Verify current password
        auth_service = current_app.auth_service
        if not auth_service.verify_password(current_password, user.password_hash):
            return error_response("Current password is incorrect", 400)

        # Update password
        user.password_hash = auth_service.hash_password(new_password)
        db.session.commit()

        logger.info(f"Password changed for user: {user.username}")

        return success_response({"message": "Password changed successfully"})

    except Exception as e:
        logger.error(f"Change password error: {e}")
        db.session.rollback()
        return error_response("Password change failed", 500)


# Admin endpoints
@auth_bp.route("/users", methods=["GET"])
@require_permission("user.read")
def list_users():
    """List all users (admin only)"""
    try:
        users = User.query.all()

        return success_response(
            {
                "users": [
                    {
                        "id": user.id,
                        "username": user.username,
                        "email": user.email,
                        "roles": user.roles.split(",") if user.roles else ["user"],
                        "is_active": user.is_active,
                        "created_at": user.created_at.isoformat(),
                        "last_login": user.last_login.isoformat() if user.last_login else None,
                    }
                    for user in users
                ]
            }
        )

    except Exception as e:
        logger.error(f"List users error: {e}")
        return error_response("Failed to list users", 500)


@auth_bp.route("/users/<int:user_id>/roles", methods=["PUT"])
@require_permission("user.update")
def update_user_roles(user_id):
    """Update user roles (admin only)"""
    try:
        data = request.get_json()
        if not data:
            return validation_error_response("JSON payload required")

        roles = data.get("roles", [])
        if not isinstance(roles, list):
            return validation_error_response("Roles must be a list")

        # Validate roles
        auth_service = current_app.auth_service
        valid_roles = list(auth_service.roles.keys())
        invalid_roles = [role for role in roles if role not in valid_roles]

        if invalid_roles:
            return validation_error_response(f"Invalid roles: {invalid_roles}")

        # Update user
        user = User.query.get(user_id)
        if not user:
            return error_response("User not found", 404)

        user.roles = ",".join(roles)
        db.session.commit()

        logger.info(f"Updated roles for user {user.username}: {roles}")

        return success_response(
            {
                "message": "User roles updated successfully",
                "user": {"id": user.id, "username": user.username, "roles": roles},
            }
        )

    except Exception as e:
        logger.error(f"Update user roles error: {e}")
        db.session.rollback()
        return error_response("Failed to update user roles", 500)


@auth_bp.route("/users/<int:user_id>/status", methods=["PUT"])
@require_permission("user.update")
def update_user_status(user_id):
    """Activate/deactivate user (admin only)"""
    try:
        data = request.get_json()
        if not data:
            return validation_error_response("JSON payload required")

        is_active = data.get("is_active")
        if is_active is None:
            return validation_error_response("is_active field required")

        user = User.query.get(user_id)
        if not user:
            return error_response("User not found", 404)

        user.is_active = bool(is_active)
        db.session.commit()

        status = "activated" if is_active else "deactivated"
        logger.info(f"User {user.username} {status}")

        return success_response(
            {
                "message": f"User {status} successfully",
                "user": {"id": user.id, "username": user.username, "is_active": user.is_active},
            }
        )

    except Exception as e:
        logger.error(f"Update user status error: {e}")
        db.session.rollback()
        return error_response("Failed to update user status", 500)
