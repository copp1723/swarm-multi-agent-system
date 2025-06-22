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
        )

    def _initialize_services(self):
        """Initialize service configurations"""
        # OpenRouter service
        self.services["openrouter"] = ServiceConfig(
            name="OpenRouter",
            required=True,  # Core functionality
            enabled=bool(self.api.openrouter_api_key),
            config={
                "api_key": self.api.openrouter_api_key,
                "base_url": "https://openrouter.ai/api/v1",
            },
        )

        # Supermemory service
        self.services["supermemory"] = ServiceConfig(
            name="Supermemory",
            required=False,  # Optional - system can work without persistent memory
            enabled=bool(self.api.supermemory_api_key),
            config={
                "api_key": self.api.supermemory_api_key,
                "base_url": os.getenv("SUPERMEMORY_BASE_URL", "https://api.supermemory.ai"),
            },
        )

        # Mailgun service
        self.services["mailgun"] = ServiceConfig(
            name="Mailgun",
            required=False,  # Optional - system can work without email
            enabled=bool(self.api.mailgun_api_key and self.api.mailgun_domain),
            config={
                "api_key": self.api.mailgun_api_key,
                "domain": self.api.mailgun_domain,
                "webhook_signing_key": self.api.mailgun_webhook_signing_key,
                "base_url": f"https://api.mailgun.net/v3/{self.api.mailgun_domain}",
            },
        )

        # MCP Filesystem service
        self.services["mcp_filesystem"] = ServiceConfig(
            name="MCP Filesystem",
            required=False,  # Optional - system can work without file operations
            enabled=True,  # Always enabled as it's internal
            config={
                "base_path": os.getenv("MCP_BASE_PATH", "/tmp/mcp"),
                "max_file_size": int(os.getenv("MCP_MAX_FILE_SIZE", "10485760")),  # 10MB
                "allowed_extensions": os.getenv(
                    "MCP_ALLOWED_EXTENSIONS", ".txt,.md,.json,.csv,.py"
                ).split(","),
            },
        )

    def get_service(self, service_name: str) -> Optional[ServiceConfig]:
        """Get service configuration"""
        return self.services.get(service_name)

    def is_service_available(self, service_name: str) -> bool:
        """Check if service is available"""
        service = self.get_service(service_name)
        return service is not None and service.is_operational()

    def get_available_services(self) -> List[str]:
        """Get list of available services"""
        return [name for name, service in self.services.items() if service.is_operational()]

    def get_unavailable_services(self) -> List[str]:
        """Get list of unavailable services"""
        return [name for name, service in self.services.items() if not service.is_operational()]

    def update_service_status(
        self, service_name: str, status: ServiceStatus, error_message: Optional[str] = None
    ):
        """Update service status"""
        service = self.get_service(service_name)
        if service:
            service.status = status
            service.error_message = error_message
            logger.info(f"Service {service_name} status updated to {status.value}")

    def validate_required_services(self) -> List[str]:
        """Validate that all required services are available"""
        missing_services = []

        for name, service in self.services.items():
            if service.required and not service.enabled:
                missing_services.append(name)

        return missing_services

    def get_system_status(self) -> Dict[str, Any]:
        """Get comprehensive system status"""
        available_services = self.get_available_services()
        unavailable_services = self.get_unavailable_services()
        missing_required = self.validate_required_services()

        return {
            "database": {
                "type": "postgresql" if self.database.is_postgresql else "sqlite",
                "url_masked": self._mask_url(self.database.url),
            },
            "services": {
                "available": available_services,
                "unavailable": unavailable_services,
                "missing_required": missing_required,
            },
            "security": {
                "jwt_configured": bool(self.security.secret_key),
                "email_verification_required": self.security.require_email_verification,
            },
            "system_health": "healthy" if not missing_required else "degraded",
        }

    def _mask_url(self, url: str) -> str:
        """Mask sensitive parts of URL"""
        if "://" in url:
            protocol, rest = url.split("://", 1)
            if "@" in rest:
                credentials, host_part = rest.split("@", 1)
                return f"{protocol}://***:***@{host_part}"
        return url

    def get_feature_flags(self) -> Dict[str, bool]:
        """Get feature availability flags for frontend"""
        return {
            "chat_enabled": self.is_service_available("openrouter"),
            "memory_enabled": self.is_service_available("supermemory"),
            "email_enabled": self.is_service_available("mailgun"),
            "file_operations_enabled": self.is_service_available("mcp_filesystem"),
            "user_registration_enabled": True,  # Always enabled
            "multi_user_enabled": self.database.is_postgresql,
        }

    def to_dict(self, include_sensitive: bool = False) -> Dict[str, Any]:
        """Convert configuration to dictionary"""
        data = {
            "debug": self.debug,
            "host": self.host,
            "port": self.port,
            "database": {
                "type": "postgresql" if self.database.is_postgresql else "sqlite",
                "pool_size": self.database.pool_size,
            },
            "services": {
                name: {
                    "name": service.name,
                    "enabled": service.enabled,
                    "required": service.required,
                    "status": service.status.value,
                    "error_message": service.error_message,
                }
                for name, service in self.services.items()
            },
            "feature_flags": self.get_feature_flags(),
            "system_status": self.get_system_status(),
        }

        if include_sensitive:
            data["security"] = {
                "secret_key": self.security.secret_key,
                "jwt_expiry_hours": self.security.jwt_expiry_hours,
            }
            data["api"] = {
                "openrouter_api_key": self.api.openrouter_api_key,
                "supermemory_api_key": self.api.supermemory_api_key,
                "mailgun_api_key": self.api.mailgun_api_key,
            }

        return data


# Global configuration instance
config = FlexibleConfig()


def get_config() -> FlexibleConfig:
    """Get global configuration instance"""
    return config


def reload_config():
    """Reload configuration from environment"""
    global config
    config = FlexibleConfig()
    logger.info("Configuration reloaded")
    return config
