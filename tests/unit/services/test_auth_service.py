"""
Unit tests for Authentication Service
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from src.services.auth_service import AuthenticationService, AuthUser, TokenPayload


class TestAuthenticationService:
    """Test cases for AuthenticationService"""

    def test_password_hashing(self, auth_service):
        """Test password hashing and verification"""
        password = "testpassword123"

        # Hash password
        hashed = auth_service.hash_password(password)
        assert hashed != password
        assert len(hashed) > 50  # bcrypt hashes are long

        # Verify correct password
        assert auth_service.verify_password(password, hashed) is True

        # Verify incorrect password
        assert auth_service.verify_password("wrongpassword", hashed) is False

    def test_token_generation(self, auth_service):
        """Test JWT token generation"""
        user = AuthUser(
            id=1,
            username="testuser",
            email="test@example.com",
            roles=["user"],
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )

        token = auth_service.generate_token(user)
        assert isinstance(token, str)
        assert len(token) > 100  # JWT tokens are long
        assert token.count(".") == 2  # JWT has 3 parts separated by dots

    def test_token_validation(self, auth_service):
        """Test JWT token validation"""
        user = AuthUser(
            id=1,
            username="testuser",
            email="test@example.com",
            roles=["user"],
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )

        # Generate and validate token
        token = auth_service.generate_token(user)
        payload = auth_service.validate_token(token)

        assert payload is not None
        assert isinstance(payload, TokenPayload)
        assert payload.user_id == user.id
        assert payload.username == user.username
        assert payload.roles == user.roles

    def test_invalid_token_validation(self, auth_service):
        """Test validation of invalid tokens"""
        # Test invalid token
        invalid_token = "invalid.token.here"
        payload = auth_service.validate_token(invalid_token)
        assert payload is None

        # Test empty token
        payload = auth_service.validate_token("")
        assert payload is None

    def test_expired_token_validation(self, auth_service):
        """Test validation of expired tokens"""
        # Create service with very short expiry
        short_auth_service = AuthenticationService(
            secret_key="test-key", token_expiry_hours=0  # Immediate expiry
        )

        user = AuthUser(
            id=1,
            username="testuser",
            email="test@example.com",
            roles=["user"],
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )

        token = short_auth_service.generate_token(user)

        # Token should be immediately expired
        payload = short_auth_service.validate_token(token)
        assert payload is None

    def test_token_revocation(self, auth_service):
        """Test token revocation"""
        user = AuthUser(
            id=1,
            username="testuser",
            email="test@example.com",
            roles=["user"],
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )

        token = auth_service.generate_token(user)

        # Token should be valid initially
        payload = auth_service.validate_token(token)
        assert payload is not None

        # Revoke token
        result = auth_service.revoke_token(token)
        assert result is True

        # Token should be invalid after revocation
        payload = auth_service.validate_token(token)
        assert payload is None

    def test_permission_checking(self, auth_service):
        """Test permission checking functionality"""
        # Test admin permissions
        admin_roles = ["admin"]
        assert auth_service.check_permission(admin_roles, "user.create") is True
        assert auth_service.check_permission(admin_roles, "system.configure") is True

        # Test user permissions
        user_roles = ["user"]
        assert auth_service.check_permission(user_roles, "agent.read") is True
        assert auth_service.check_permission(user_roles, "user.create") is False

        # Test readonly permissions
        readonly_roles = ["readonly"]
        assert auth_service.check_permission(readonly_roles, "agent.read") is True
        assert auth_service.check_permission(readonly_roles, "memory.write") is False

    def test_get_user_permissions(self, auth_service):
        """Test getting all permissions for user roles"""
        # Test admin permissions
        admin_permissions = auth_service.get_user_permissions(["admin"])
        assert "user.create" in admin_permissions
        assert "system.configure" in admin_permissions
        assert len(admin_permissions) > 10

        # Test user permissions
        user_permissions = auth_service.get_user_permissions(["user"])
        assert "agent.read" in user_permissions
        assert "memory.write" in user_permissions
        assert "user.create" not in user_permissions

        # Test multiple roles
        multi_permissions = auth_service.get_user_permissions(["user", "api"])
        assert "agent.read" in multi_permissions
        assert "memory.write" in multi_permissions

    def test_role_definitions(self, auth_service):
        """Test that all required roles are defined"""
        required_roles = ["admin", "user", "readonly", "api"]

        for role in required_roles:
            assert role in auth_service.roles
            role_obj = auth_service.roles[role]
            assert role_obj.name == role
            assert isinstance(role_obj.permissions, list)
            assert len(role_obj.permissions) > 0
            assert isinstance(role_obj.description, str)

    def test_token_refresh(self, auth_service):
        """Test token refresh functionality"""
        user = AuthUser(
            id=1,
            username="testuser",
            email="test@example.com",
            roles=["user"],
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )

        token = auth_service.generate_token(user)

        # Test refresh (should return same token if not close to expiry)
        refreshed_token = auth_service.refresh_token(token)
        assert refreshed_token == token

        # Test refresh with invalid token
        invalid_refresh = auth_service.refresh_token("invalid.token")
        assert invalid_refresh is None


@pytest.mark.auth
class TestAuthenticationIntegration:
    """Integration tests for authentication system"""

    def test_full_authentication_flow(self, auth_service):
        """Test complete authentication flow"""
        # Create user
        user = AuthUser(
            id=1,
            username="testuser",
            email="test@example.com",
            roles=["user"],
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )

        # Generate token
        token = auth_service.generate_token(user)
        assert token is not None

        # Validate token
        payload = auth_service.validate_token(token)
        assert payload is not None
        assert payload.user_id == user.id

        # Check permissions
        assert auth_service.check_permission(payload.roles, "agent.read") is True
        assert auth_service.check_permission(payload.roles, "user.create") is False

        # Revoke token
        auth_service.revoke_token(token)

        # Validate revoked token
        payload = auth_service.validate_token(token)
        assert payload is None

    def test_multiple_user_tokens(self, auth_service):
        """Test handling multiple user tokens"""
        users = [
            AuthUser(
                id=i,
                username=f"user{i}",
                email=f"user{i}@example.com",
                roles=["user"],
                is_active=True,
                created_at=datetime.now(timezone.utc),
            )
            for i in range(1, 4)
        ]

        tokens = [auth_service.generate_token(user) for user in users]

        # All tokens should be valid
        for i, token in enumerate(tokens):
            payload = auth_service.validate_token(token)
            assert payload is not None
            assert payload.user_id == users[i].id

        # Revoke one token
        auth_service.revoke_token(tokens[1])

        # Check token validity
        assert auth_service.validate_token(tokens[0]) is not None
        assert auth_service.validate_token(tokens[1]) is None
        assert auth_service.validate_token(tokens[2]) is not None
