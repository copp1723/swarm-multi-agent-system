"""
Integration tests for Authentication Routes
"""

import json
from datetime import datetime, timezone

import pytest

from src.models.user import User, db


@pytest.mark.integration
@pytest.mark.auth
class TestAuthenticationRoutes:
    """Integration tests for authentication endpoints"""

    def test_user_registration(self, client):
        """Test user registration endpoint"""
        user_data = {
            "username": "newuser",
            "email": "newuser@example.com",
            "password": "password123",
            "confirm_password": "password123",
        }

        response = client.post(
            "/api/auth/register", data=json.dumps(user_data), content_type="application/json"
        )

        assert response.status_code == 201
        data = response.get_json()
        assert data["success"] is True
        assert "user" in data
        assert data["user"]["username"] == user_data["username"]
        assert data["user"]["email"] == user_data["email"]
        assert "password" not in data["user"]

    def test_registration_validation(self, client):
        """Test registration input validation"""
        # Test missing fields
        response = client.post(
            "/api/auth/register", data=json.dumps({}), content_type="application/json"
        )
        assert response.status_code == 400

        # Test password mismatch
        user_data = {
            "username": "testuser",
            "email": "test@example.com",
            "password": "password123",
            "confirm_password": "different123",
        }
        response = client.post(
            "/api/auth/register", data=json.dumps(user_data), content_type="application/json"
        )
        assert response.status_code == 400

        # Test short password
        user_data["confirm_password"] = "short"
        user_data["password"] = "short"
        response = client.post(
            "/api/auth/register", data=json.dumps(user_data), content_type="application/json"
        )
        assert response.status_code == 400

    def test_duplicate_registration(self, client, create_test_user):
        """Test registration with existing username/email"""
        # Try to register with existing username
        user_data = {
            "username": create_test_user.username,
            "email": "different@example.com",
            "password": "password123",
            "confirm_password": "password123",
        }

        response = client.post(
            "/api/auth/register", data=json.dumps(user_data), content_type="application/json"
        )
        assert response.status_code == 400

        # Try to register with existing email
        user_data["username"] = "differentuser"
        user_data["email"] = create_test_user.email

        response = client.post(
            "/api/auth/register", data=json.dumps(user_data), content_type="application/json"
        )
        assert response.status_code == 400

    def test_user_login(self, client, create_test_user, test_user_data):
        """Test user login endpoint"""
        login_data = {
            "username": test_user_data["username"],
            "password": test_user_data["password"],
        }

        response = client.post(
            "/api/auth/login", data=json.dumps(login_data), content_type="application/json"
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "token" in data
        assert "user" in data
        assert data["user"]["username"] == test_user_data["username"]
        assert "permissions" in data["user"]

    def test_login_with_email(self, client, create_test_user, test_user_data):
        """Test login using email instead of username"""
        login_data = {
            "username": test_user_data["email"],  # Using email as username
            "password": test_user_data["password"],
        }

        response = client.post(
            "/api/auth/login", data=json.dumps(login_data), content_type="application/json"
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "token" in data

    def test_login_validation(self, client):
        """Test login input validation"""
        # Test missing credentials
        response = client.post(
            "/api/auth/login", data=json.dumps({}), content_type="application/json"
        )
        assert response.status_code == 400

        # Test invalid credentials
        login_data = {"username": "nonexistent", "password": "wrongpassword"}
        response = client.post(
            "/api/auth/login", data=json.dumps(login_data), content_type="application/json"
        )
        assert response.status_code == 401

    def test_login_inactive_user(self, app, client, auth_service, test_user_data):
        """Test login with inactive user account"""
        with app.app_context():
            # Create inactive user
            password_hash = auth_service.hash_password(test_user_data["password"])
            user = User(
                username="inactive_user",
                email="inactive@example.com",
                password_hash=password_hash,
                roles="user",
                is_active=False,  # Inactive user
                created_at=datetime.now(timezone.utc),
            )
            db.session.add(user)
            db.session.commit()

        login_data = {"username": "inactive_user", "password": test_user_data["password"]}

        response = client.post(
            "/api/auth/login", data=json.dumps(login_data), content_type="application/json"
        )
        assert response.status_code == 401

    def test_get_current_user(self, client, auth_headers):
        """Test getting current user information"""
        response = client.get("/api/auth/me", headers=auth_headers)

        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "user" in data
        assert "permissions" in data["user"]
        assert "roles" in data["user"]

    def test_get_current_user_unauthorized(self, client):
        """Test getting current user without authentication"""
        response = client.get("/api/auth/me")
        assert response.status_code == 401

    def test_logout(self, client, auth_headers):
        """Test user logout"""
        response = client.post("/api/auth/logout", headers=auth_headers)

        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True

        # Token should be invalid after logout
        response = client.get("/api/auth/me", headers=auth_headers)
        assert response.status_code == 401

    def test_change_password(self, client, auth_headers, test_user_data):
        """Test password change"""
        password_data = {
            "current_password": test_user_data["password"],
            "new_password": "newpassword123",
            "confirm_password": "newpassword123",
        }

        response = client.post(
            "/api/auth/change-password",
            data=json.dumps(password_data),
            content_type="application/json",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True

    def test_change_password_validation(self, client, auth_headers):
        """Test password change validation"""
        # Test wrong current password
        password_data = {
            "current_password": "wrongpassword",
            "new_password": "newpassword123",
            "confirm_password": "newpassword123",
        }

        response = client.post(
            "/api/auth/change-password",
            data=json.dumps(password_data),
            content_type="application/json",
            headers=auth_headers,
        )
        assert response.status_code == 400

        # Test password mismatch
        password_data["current_password"] = "testpassword123"
        password_data["confirm_password"] = "different123"

        response = client.post(
            "/api/auth/change-password",
            data=json.dumps(password_data),
            content_type="application/json",
            headers=auth_headers,
        )
        assert response.status_code == 400

    def test_token_refresh(self, client, auth_headers):
        """Test token refresh"""
        response = client.post("/api/auth/refresh", headers=auth_headers)

        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "token" in data


@pytest.mark.integration
@pytest.mark.auth
class TestAdminRoutes:
    """Integration tests for admin authentication endpoints"""

    def test_list_users_admin(self, client, admin_headers, create_test_user, create_test_admin):
        """Test listing users as admin"""
        response = client.get("/api/auth/users", headers=admin_headers)

        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "users" in data
        assert len(data["users"]) >= 2  # At least test user and admin

    def test_list_users_unauthorized(self, client, auth_headers):
        """Test listing users without admin privileges"""
        response = client.get("/api/auth/users", headers=auth_headers)
        assert response.status_code == 403

    def test_update_user_roles(self, client, admin_headers, create_test_user):
        """Test updating user roles as admin"""
        role_data = {"roles": ["user", "api"]}

        response = client.put(
            f"/api/auth/users/{create_test_user.id}/roles",
            data=json.dumps(role_data),
            content_type="application/json",
            headers=admin_headers,
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["user"]["roles"] == role_data["roles"]

    def test_update_user_roles_invalid(self, client, admin_headers, create_test_user):
        """Test updating user roles with invalid roles"""
        role_data = {"roles": ["invalid_role"]}

        response = client.put(
            f"/api/auth/users/{create_test_user.id}/roles",
            data=json.dumps(role_data),
            content_type="application/json",
            headers=admin_headers,
        )
        assert response.status_code == 400

    def test_update_user_status(self, client, admin_headers, create_test_user):
        """Test updating user active status"""
        status_data = {"is_active": False}

        response = client.put(
            f"/api/auth/users/{create_test_user.id}/status",
            data=json.dumps(status_data),
            content_type="application/json",
            headers=admin_headers,
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["user"]["is_active"] is False

    def test_admin_operations_unauthorized(self, client, auth_headers, create_test_user):
        """Test admin operations without admin privileges"""
        # Test role update
        role_data = {"roles": ["admin"]}
        response = client.put(
            f"/api/auth/users/{create_test_user.id}/roles",
            data=json.dumps(role_data),
            content_type="application/json",
            headers=auth_headers,
        )
        assert response.status_code == 403

        # Test status update
        status_data = {"is_active": False}
        response = client.put(
            f"/api/auth/users/{create_test_user.id}/status",
            data=json.dumps(status_data),
            content_type="application/json",
            headers=auth_headers,
        )
        assert response.status_code == 403


@pytest.mark.integration
class TestAuthenticationMiddleware:
    """Test authentication middleware and decorators"""

    def test_require_auth_decorator(self, client, auth_headers):
        """Test @require_auth decorator"""
        # Test with valid token
        response = client.get("/api/auth/me", headers=auth_headers)
        assert response.status_code == 200

        # Test without token
        response = client.get("/api/auth/me")
        assert response.status_code == 401

        # Test with invalid token
        invalid_headers = {"Authorization": "Bearer invalid.token.here"}
        response = client.get("/api/auth/me", headers=invalid_headers)
        assert response.status_code == 401

    def test_require_permission_decorator(self, client, auth_headers, admin_headers):
        """Test @require_permission decorator"""
        # Test user trying to access admin endpoint
        response = client.get("/api/auth/users", headers=auth_headers)
        assert response.status_code == 403

        # Test admin accessing admin endpoint
        response = client.get("/api/auth/users", headers=admin_headers)
        assert response.status_code == 200
