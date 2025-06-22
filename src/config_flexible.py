"""
Flexible Configuration System - Support for optional services and graceful degradation
"""

import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ServiceStatus(Enum):
    """Service availability status"""

    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    DEGRADED = "degraded"
    ERROR = "error"


@dataclass
class ServiceConfig:
    """Configuration for an external service"""

    name: str
    required: bool = False
    enabled: bool = True
    config: Dict[str, Any] = field(default_factory=dict)
    status: ServiceStatus = ServiceStatus.UNAVAILABLE
    error_message: Optional[str] = None

    def is_operational(self) -> bool:
        """Check if service is operational"""
        return self.enabled and self.status == ServiceStatus.AVAILABLE


@dataclass
class DatabaseConfig:
    """Database configuration with fallback support"""

    url: str
    pool_size: int = 5
    pool_timeout: int = 30
    pool_recycle: int = 3600
    echo: bool = False

    @property
    def is_postgresql(self) -> bool:
        return self.url.startswith("postgresql://")

    @property
    def is_sqlite(self) -> bool:
        return self.url.startswith("sqlite://")


@dataclass
class SecurityConfig:
    """Security configuration"""

    secret_key: str
    jwt_expiry_hours: int = 24
    password_min_length: int = 8
    max_login_attempts: int = 5
    lockout_duration_minutes: int = 15
    require_email_verification: bool = False


@dataclass
class APIConfig:
    """API configuration"""

    openrouter_api_key: Optional[str] = None
    supermemory_api_key: Optional[str] = None
    mailgun_api_key: Optional[str] = None
    mailgun_domain: Optional[str] = None
    mailgun_webhook_signing_key: Optional[str] = None
    rate_limit_per_minute: int = 60
    cors_origins: List[str] = field(default_factory=lambda: ["*"])
    api_timeout: int = 30
    max_retries: int = 3


class FlexibleConfig:
    """
    Flexible configuration system that supports optional services
    and graceful degradation when services are unavailable
    """

    def __init__(self):
        self.services: Dict[str, ServiceConfig] = {}
        self.database: DatabaseConfig = self._load_database_config()
        self.security: SecurityConfig = self._load_security_config()
        self.api: APIConfig = self._load_api_config()
        self.debug: bool = os.getenv("DEBUG", "False").lower() == "true"
        self.port: int = int(os.getenv("PORT", "5002"))
        self.host: str = os.getenv("HOST", "0.0.0.0")

        # Initialize service configurations
        self._initialize_services()

        logger.info("Configuration system initialized")

    def _load_database_config(self) -> DatabaseConfig:
        """Load database configuration with fallback to SQLite"""
        database_url = os.getenv("DATABASE_URL")

        if database_url:
            logger.info(f"Using DATABASE_URL from environment: {database_url[:50]}...")
        else:
            # Fallback to SQLite in a writable location
            import tempfile

            sqlite_dir = os.path.join(tempfile.gettempdir(), "swarm_agents")
            os.makedirs(sqlite_dir, exist_ok=True)
            sqlite_path = os.path.join(sqlite_dir, "app.db")
            database_url = f"sqlite:///{sqlite_path}"
            logger.info(f"No DATABASE_URL provided, using SQLite fallback at {sqlite_path}")

        return DatabaseConfig(
            url=database_url,
            pool_size=int(os.getenv("DB_POOL_SIZE", "5")),
            pool_timeout=int(os.getenv("DB_POOL_TIMEOUT", "30")),
            pool_recycle=int(os.getenv("DB_POOL_RECYCLE", "3600")),
            echo=os.getenv("DB_ECHO", "False").lower() == "true",
        )

    def _load_security_config(self) -> SecurityConfig:
        """Load security configuration"""
        secret_key = os.getenv("SECRET_KEY")
        if not secret_key:
            # Generate a default secret key for development
            import secrets

            secret_key = secrets.token_hex(32)
            logger.warning(
                "No SECRET_KEY provided, using generated key (not suitable for production)"
            )

        return SecurityConfig(
            secret_key=secret_key,
            jwt_expiry_hours=int(os.getenv("JWT_EXPIRY_HOURS", "24")),
            password_min_length=int(os.getenv("PASSWORD_MIN_LENGTH", "8")),
            max_login_attempts=int(os.getenv("MAX_LOGIN_ATTEMPTS", "5")),
            lockout_duration_minutes=int(os.getenv("LOCKOUT_DURATION_MINUTES", "15")),
            require_email_verification=os.getenv("REQUIRE_EMAIL_VERIFICATION", "False").lower()
            == "true",
        )

    def _load_api_config(self) -> APIConfig:
        """Load API configuration"""
        cors_origins = os.getenv("CORS_ORIGINS", "*").split(",")

        return APIConfig(
            openrouter_api_key=os.getenv("OPENROUTER_API_KEY"),
            supermemory_api_key=os.getenv("SUPERMEMORY_API_KEY"),
            mailgun_api_key=os.getenv("MAILGUN_API_KEY"),
            mailgun_domain=os.getenv("MAILGUN_DOMAIN"),
            mailgun_webhook_signing_key=os.getenv("MAILGUN_WEBHOOK_SIGNING_KEY"),
            rate_limit_per_minute=int(os.getenv("RATE_LIMIT_PER_MINUTE", "60")),
            cors_origins=cors_origins,
            api_timeout=int(os.getenv("API_TIMEOUT", "30")),
            max_retries=int(os.getenv("MAX_RETRIES", "3")),
        )

    def _initialize_services(self):
        """Initialize service configurations"""
        # OpenRouter service
        self.services["openrouter"] = ServiceConfig(
            name="OpenRouter",
            required=True,
            enabled=bool(self.api.openrouter_api_key),
            config={"api_key": self.api.openrouter_api_key},
        )

        # Supermemory service
        self.services["supermemory"] = ServiceConfig(
            name="Supermemory",
            required=False,
            enabled=bool(self.api.supermemory_api_key),
            config={"api_key": self.api.supermemory_api_key},
        )

        # Mailgun service
        self.services["mailgun"] = ServiceConfig(
            name="Mailgun",
            required=False,
            enabled=bool(self.api.mailgun_api_key and self.api.mailgun_domain),
            config={
                "api_key": self.api.mailgun_api_key,
                "domain": self.api.mailgun_domain,
                "webhook_signing_key": self.api.mailgun_webhook_signing_key,
            },
        )

    def get_service_config(self, service_name: str) -> Optional[ServiceConfig]:
        """Get configuration for a specific service"""
        return self.services.get(service_name)

    def is_service_enabled(self, service_name: str) -> bool:
        """Check if a service is enabled and operational"""
        service = self.get_service_config(service_name)
        return service.is_operational() if service else False

    def get_enabled_services(self) -> List[str]:
        """Get list of enabled service names"""
        return [name for name, service in self.services.items() if service.enabled]

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary"""
        return {
            "database": {
                "url": self.database.url,
                "pool_size": self.database.pool_size,
                "is_postgresql": self.database.is_postgresql,
                "is_sqlite": self.database.is_sqlite,
            },
            "security": {
                "jwt_expiry_hours": self.security.jwt_expiry_hours,
                "password_min_length": self.security.password_min_length,
                "max_login_attempts": self.security.max_login_attempts,
                "lockout_duration_minutes": self.security.lockout_duration_minutes,
                "require_email_verification": self.security.require_email_verification,
            },
            "api": {
                "rate_limit_per_minute": self.api.rate_limit_per_minute,
                "cors_origins": self.api.cors_origins,
                "api_timeout": self.api.api_timeout,
                "max_retries": self.api.max_retries,
            },
            "services": {
                name: {
                    "enabled": service.enabled,
                    "status": service.status.value,
                    "required": service.required,
                }
                for name, service in self.services.items()
            },
            "debug": self.debug,
            "port": self.port,
            "host": self.host,
        }


# Global configuration instance
_config_instance = None


def get_config() -> FlexibleConfig:
    """Get the global configuration instance"""
    global _config_instance
    if _config_instance is None:
        _config_instance = FlexibleConfig()
    return _config_instance


# For backward compatibility
config = get_config()
