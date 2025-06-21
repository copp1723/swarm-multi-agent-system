"""
Test configuration and fixtures for Swarm Multi-Agent System
"""

import os
import tempfile
from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest

from src.config_flexible import FlexibleConfig
from src.main import create_app
from src.models.user import User, db
from src.services.auth_service import AuthenticationService


@pytest.fixture(scope="session")
def app():
    """Create application for testing"""
    # Create temporary database
    db_fd, db_path = tempfile.mkstemp()

    # Test configuration
    test_config = {
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_path}",
        "SQLALCHEMY_TRACK_MODIFICATIONS": False,
        "SECRET_KEY": "test-secret-key-for-testing-only",
        "WTF_CSRF_ENABLED": False,
    }

    # Set test environment variables
    os.environ.update(
        {
            "DATABASE_URL": f"sqlite:///{db_path}",
            "SECRET_KEY": "test-secret-key-for-testing-only",
            "DEBUG": "False",
            "OPENROUTER_API_KEY": "test-openrouter-key",
            "SUPERMEMORY_API_KEY": "test-supermemory-key",
            "MAILGUN_API_KEY": "test-mailgun-key",
            "MAILGUN_DOMAIN": "test.example.com",
        }
    )

    app = create_app(test_config)

    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()

    os.close(db_fd)
    os.unlink(db_path)


@pytest.fixture
def client(app):
    """Create test client"""
    return app.test_client()


@pytest.fixture
def runner(app):
    """Create test CLI runner"""
    return app.test_cli_runner()


@pytest.fixture
def auth_service():
    """Create authentication service for testing"""
    return AuthenticationService(secret_key="test-secret-key", token_expiry_hours=1)


@pytest.fixture
def test_user_data():
    """Test user data"""
    return {
        "username": "testuser",
        "email": "test@example.com",
        "password": "testpassword123",
        "first_name": "Test",
        "last_name": "User",
    }


@pytest.fixture
def test_admin_data():
    """Test admin user data"""
    return {
        "username": "admin",
        "email": "admin@example.com",
        "password": "adminpassword123",
        "roles": "admin,user",
    }


@pytest.fixture
def create_test_user(app, auth_service, test_user_data):
    """Create a test user in the database"""
    with app.app_context():
        password_hash = auth_service.hash_password(test_user_data["password"])
        user = User(
            username=test_user_data["username"],
            email=test_user_data["email"],
            password_hash=password_hash,
            roles="user",
            is_active=True,
            created_at=datetime.now(timezone.utc),
            first_name=test_user_data["first_name"],
            last_name=test_user_data["last_name"],
        )
        db.session.add(user)
        db.session.commit()
        return user


@pytest.fixture
def create_test_admin(app, auth_service, test_admin_data):
    """Create a test admin user in the database"""
    with app.app_context():
        password_hash = auth_service.hash_password(test_admin_data["password"])
        user = User(
            username=test_admin_data["username"],
            email=test_admin_data["email"],
            password_hash=password_hash,
            roles=test_admin_data["roles"],
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
        db.session.add(user)
        db.session.commit()
        return user


@pytest.fixture
def auth_headers(app, auth_service, create_test_user):
    """Create authentication headers for test requests"""
    with app.app_context():
        from src.services.auth_service import AuthUser

        auth_user = AuthUser(
            id=create_test_user.id,
            username=create_test_user.username,
            email=create_test_user.email,
            roles=["user"],
            is_active=True,
            created_at=create_test_user.created_at,
        )

        token = auth_service.generate_token(auth_user)
        return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_headers(app, auth_service, create_test_admin):
    """Create admin authentication headers for test requests"""
    with app.app_context():
        from src.services.auth_service import AuthUser

        auth_user = AuthUser(
            id=create_test_admin.id,
            username=create_test_admin.username,
            email=create_test_admin.email,
            roles=["admin", "user"],
            is_active=True,
            created_at=create_test_admin.created_at,
        )

        token = auth_service.generate_token(auth_user)
        return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def mock_openrouter_service():
    """Mock OpenRouter service"""
    mock = Mock()
    mock.chat_completion.return_value = {
        "choices": [{"message": {"content": "Test response from mock OpenRouter"}}]
    }
    mock.get_available_models.return_value = [
        {"id": "gpt-4", "name": "GPT-4"},
        {"id": "claude-3", "name": "Claude 3"},
    ]
    return mock


@pytest.fixture
def mock_supermemory_service():
    """Mock Supermemory service"""
    mock = Mock()
    mock.store_conversation.return_value = {"id": "test-conversation-id"}
    mock.retrieve_context.return_value = {"context": "Test context from mock Supermemory"}
    mock.search_memories.return_value = {"results": [{"content": "Test memory", "score": 0.9}]}
    return mock


@pytest.fixture
def mock_mailgun_service():
    """Mock Mailgun service"""
    mock = Mock()
    mock.send_email.return_value = {"id": "test-message-id", "message": "Queued. Thank you."}
    mock.get_domain_stats.return_value = {"delivered": 100, "failed": 0}
    return mock


@pytest.fixture
def mock_mcp_service():
    """Mock MCP filesystem service"""
    mock = Mock()
    mock.read_file.return_value = "Test file content"
    mock.write_file.return_value = True
    mock.list_directory.return_value = ["file1.txt", "file2.txt"]
    mock.create_directory.return_value = True
    return mock


@pytest.fixture
def test_config():
    """Test configuration object"""
    return FlexibleConfig()


# Test utilities
class TestHelpers:
    """Helper methods for testing"""

    @staticmethod
    def login_user(client, username="testuser", password="testpassword123"):
        """Helper to login a user and get token"""
        response = client.post("/api/auth/login", json={"username": username, "password": password})
        if response.status_code == 200:
            return response.get_json()["token"]
        return None

    @staticmethod
    def create_auth_headers(token):
        """Helper to create authorization headers"""
        return {"Authorization": f"Bearer {token}"}

    @staticmethod
    def assert_error_response(response, status_code, error_message=None):
        """Helper to assert error responses"""
        assert response.status_code == status_code
        data = response.get_json()
        assert "error" in data
        if error_message:
            assert error_message in data["error"]

    @staticmethod
    def assert_success_response(response, status_code=200):
        """Helper to assert success responses"""
        assert response.status_code == status_code
        data = response.get_json()
        assert "success" in data
        assert data["success"] is True


@pytest.fixture
def helpers():
    """Test helpers fixture"""
    return TestHelpers
