"""
Authentication Routes - Login, logout, registration, and user management endpoints
"""

import logging
from datetime import datetime, timezone

from flask import Blueprint, current_app, jsonify, request # jsonify might be needed for direct returns if not all errors become exceptions

from src.models.user import User, db
from src.services.auth_service import AuthUser, require_auth, require_permission, require_role
from src.utils.response_helpers import create_success_response # error_response will be removed from imports
from src.exceptions import ValidationError, SwarmException, AuthenticationError # Import necessary exceptions

# validation_error_response function will be removed

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
            raise ValidationError("JSON payload required", error_code="JSON_PAYLOAD_REQUIRED")

        username = data.get("username", "").strip()
        password = data.get("password", "")

        if not username or not password:
            raise ValidationError("Username and password required", error_code="MISSING_CREDENTIALS", details={"fields": ["username", "password"]})

        # Find user by username or email
        user = User.query.filter((User.username == username) | (User.email == username)).first()

        if not user:
            logger.warning(f"Login attempt with non-existent username: {username}")
            raise AuthenticationError("Invalid credentials", error_code="INVALID_CREDENTIALS")

        if not user.is_active:
            logger.warning(f"Login attempt for inactive user: {username}")
            raise AuthenticationError("Account is disabled", error_code="ACCOUNT_DISABLED")

        # Verify password
        auth_service = current_app.auth_service
        if not auth_service.verify_password(password, user.password_hash):
            logger.warning(f"Failed login attempt for user: {username}")
            raise AuthenticationError("Invalid credentials", error_code="INVALID_CREDENTIALS")

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

        return create_success_response(
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
    except ValidationError: # Re-raise ValidationErrors to be caught by global handler or specific handler if added
        raise
    except AuthenticationError: # Re-raise AuthenticationErrors
        raise
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise SwarmException("Login failed", error_code="LOGIN_FAILED", details={"original_error": str(e)}, status_code=500)


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
            raise ValidationError("JSON payload required", error_code="JSON_PAYLOAD_REQUIRED")

        username = data.get("username", "").strip()
        email = data.get("email", "").strip().lower()
        password = data.get("password", "")
        confirm_password = data.get("confirm_password", "")

        # Validation
        if not all([username, email, password, confirm_password]):
            raise ValidationError("All fields are required", error_code="MISSING_FIELDS", details={"required_fields": ["username", "email", "password", "confirm_password"]})

        if password != confirm_password:
            raise ValidationError("Passwords do not match", error_code="PASSWORD_MISMATCH", details={"field": "confirm_password"})

        if len(password) < 8:
            raise ValidationError("Password must be at least 8 characters", error_code="PASSWORD_TOO_SHORT", details={"field": "password", "min_length": 8})

        if len(username) < 3:
            raise ValidationError("Username must be at least 3 characters", error_code="USERNAME_TOO_SHORT", details={"field": "username", "min_length": 3})

        if "@" not in email: # Basic email validation
            raise ValidationError("Valid email address required", error_code="INVALID_EMAIL_FORMAT", details={"field": "email"})

        # Check if user already exists
        existing_user = User.query.filter(
            (User.username == username) | (User.email == email)
        ).first()

        if existing_user:
            if existing_user.username == username:
                raise ValidationError("Username already exists", error_code="USERNAME_EXISTS", details={"field": "username"})
            else:
                raise ValidationError("Email already registered", error_code="EMAIL_EXISTS", details={"field": "email"})

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

        return create_success_response(
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
    except ValidationError:
        raise
    except Exception as e:
        logger.error(f"Registration error: {e}")
        db.session.rollback()
        raise SwarmException("Registration failed", error_code="REGISTRATION_FAILED", details={"original_error": str(e)}, status_code=500)


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

        return create_success_response({"message": "Logged out successfully"})
    except SwarmException: # Includes AuthenticationError if token validation fails within @require_auth
        raise
    except Exception as e:
        logger.error(f"Logout error: {e}")
        raise SwarmException("Logout failed", error_code="LOGOUT_FAILED", details={"original_error": str(e)}, status_code=500)


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
            return create_success_response({"token": new_token})
        else:
            # This case implies token was valid enough for @require_auth but refresh logic decided not to issue a new one
            # or an issue occurred within refresh_token not raising an exception but returning None.
            raise SwarmException("Token refresh failed", error_code="TOKEN_REFRESH_FAILED", status_code=401) # Or 400/500 depending on expected cause
    except SwarmException:
        raise
    except Exception as e:
        logger.error(f"Token refresh error: {e}")
        raise SwarmException("Token refresh failed", error_code="TOKEN_REFRESH_UNEXPECTED_FAILED", details={"original_error": str(e)}, status_code=500)


@auth_bp.route("/me", methods=["GET"])
@require_auth
def get_current_user():
    """Get current user information"""
    try:
        # request.current_user comes from @require_auth decorator, which uses TokenPayload from auth_service
        # It has user_id.
        user = User.query.get(request.current_user.user_id)
        if not user:
            # This case should ideally not happen if token belongs to a valid user that was not deleted.
            raise SwarmException("User associated with token not found", error_code="USER_NOT_FOUND", status_code=404)

        auth_service = current_app.auth_service
        user_roles = user.roles.split(",") if user.roles else ["user"]

        return create_success_response(
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
    except SwarmException:
        raise
    except Exception as e:
        logger.error(f"Get current user error: {e}")
        raise SwarmException("Failed to get user information", error_code="GET_USER_INFO_FAILED", details={"original_error": str(e)}, status_code=500)


@auth_bp.route("/change-password", methods=["POST"])
@require_auth
def change_password():
    """Change user password"""
    try:
        data = request.get_json()
        if not data:
            raise ValidationError("JSON payload required", error_code="JSON_PAYLOAD_REQUIRED")

        current_password = data.get("current_password", "")
        new_password = data.get("new_password", "")
        confirm_password = data.get("confirm_password", "")

        if not all([current_password, new_password, confirm_password]):
            raise ValidationError("All fields are required", error_code="MISSING_FIELDS", details={"required_fields": ["current_password", "new_password", "confirm_password"]})

        if new_password != confirm_password:
            raise ValidationError("New passwords do not match", error_code="PASSWORD_MISMATCH", details={"field": "confirm_password"})

        if len(new_password) < 8:
            raise ValidationError("Password must be at least 8 characters", error_code="PASSWORD_TOO_SHORT", details={"field": "new_password", "min_length": 8})

        # Get current user
        user = User.query.get(request.current_user.user_id)
        if not user:
            raise SwarmException("User not found", error_code="USER_NOT_FOUND", status_code=404)

        # Verify current password
        auth_service = current_app.auth_service
        if not auth_service.verify_password(current_password, user.password_hash):
            # Using ValidationError as it's a form of input validation failure from the user.
            raise ValidationError("Current password is incorrect", error_code="CURRENT_PASSWORD_INVALID", details={"field": "current_password"})

        # Update password
        user.password_hash = auth_service.hash_password(new_password)
        db.session.commit()

        logger.info(f"Password changed for user: {user.username}")

        return create_success_response({"message": "Password changed successfully"})
    except ValidationError:
        raise
    except SwarmException:
        raise
    except Exception as e:
        logger.error(f"Change password error: {e}")
        db.session.rollback()
        raise SwarmException("Password change failed", error_code="PASSWORD_CHANGE_FAILED", details={"original_error": str(e)}, status_code=500)


# Admin endpoints
@auth_bp.route("/users", methods=["GET"])
@require_permission("user.read")
def list_users():
    """List all users (admin only)"""
    try:
        users = User.query.all()

        return create_success_response(
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
    except SwarmException: # For @require_permission
        raise
    except Exception as e:
        logger.error(f"List users error: {e}")
        raise SwarmException("Failed to list users", error_code="LIST_USERS_FAILED", details={"original_error": str(e)}, status_code=500)


@auth_bp.route("/users/<int:user_id>/roles", methods=["PUT"])
@require_permission("user.update")
def update_user_roles(user_id):
    """Update user roles (admin only)"""
    try:
        data = request.get_json()
        if not data:
            raise ValidationError("JSON payload required", error_code="JSON_PAYLOAD_REQUIRED")

        roles = data.get("roles", [])
        if not isinstance(roles, list):
            raise ValidationError("Roles must be a list", error_code="INVALID_ROLES_FORMAT", details={"field": "roles"})

        # Validate roles
        auth_service = current_app.auth_service
        valid_roles = list(auth_service.roles.keys())
        invalid_roles = [role for role in roles if role not in valid_roles]

        if invalid_roles:
            raise ValidationError(f"Invalid roles: {invalid_roles}", error_code="INVALID_ROLES_PROVIDED", details={"invalid_roles": invalid_roles, "valid_roles": valid_roles})

        # Update user
        user = User.query.get(user_id)
        if not user:
            raise SwarmException("User not found to update roles", error_code="USER_NOT_FOUND_FOR_ROLE_UPDATE", status_code=404, details={"user_id": user_id})

        user.roles = ",".join(roles)
        db.session.commit()

        logger.info(f"Updated roles for user {user.username}: {roles}")

        return create_success_response(
            {
                "message": "User roles updated successfully",
                "user": {"id": user.id, "username": user.username, "roles": roles},
            }
        )
    except ValidationError:
        raise
    except SwarmException: # For @require_permission or user not found
        raise
    except Exception as e:
        logger.error(f"Update user roles error: {e}")
        db.session.rollback()
        raise SwarmException("Failed to update user roles", error_code="UPDATE_USER_ROLES_FAILED", details={"original_error": str(e)}, status_code=500)


@auth_bp.route("/users/<int:user_id>/status", methods=["PUT"])
@require_permission("user.update")
def update_user_status(user_id):
    """Activate/deactivate user (admin only)"""
    try:
        data = request.get_json()
        if not data:
            raise ValidationError("JSON payload required", error_code="JSON_PAYLOAD_REQUIRED")

        is_active = data.get("is_active")
        if is_active is None: # Note: bool(None) is False. Explicit check for None is better.
            raise ValidationError("is_active field required", error_code="MISSING_FIELD", details={"field": "is_active"})

        user = User.query.get(user_id)
        if not user:
            raise SwarmException("User not found to update status", error_code="USER_NOT_FOUND_FOR_STATUS_UPDATE", status_code=404, details={"user_id": user_id})

        user.is_active = bool(is_active)
        db.session.commit()

        status = "activated" if is_active else "deactivated"
        logger.info(f"User {user.username} {status}")

        return create_success_response(
            {
                "message": f"User {status} successfully",
                "user": {"id": user.id, "username": user.username, "is_active": user.is_active},
            }
        )
    except ValidationError:
        raise
    except SwarmException: # For @require_permission or user not found
        raise
    except Exception as e:
        logger.error(f"Update user status error: {e}")
        db.session.rollback()
        raise SwarmException("Failed to update user status", error_code="UPDATE_USER_STATUS_FAILED", details={"original_error": str(e)}, status_code=500)
