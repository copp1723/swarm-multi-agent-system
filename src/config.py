"""
Configuration management for Swarm Multi-Agent System
Centralized configuration with environment variable support and validation
"""
import os
from typing import Optional
from dataclasses import dataclass
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

@dataclass
class APIConfig:
    """Configuration for external API services"""
    openrouter_api_key: str
    supermemory_api_key: str
    mailgun_api_key: str
    mailgun_domain: str
    mailgun_webhook_signing_key: str
    
    def __post_init__(self):
        """Validate required configuration"""
        missing = []
        if not self.openrouter_api_key:
            missing.append("OPENROUTER_API_KEY")
        if not self.supermemory_api_key:
            missing.append("SUPERMEMORY_API_KEY")
        if not self.mailgun_api_key:
            missing.append("MAILGUN_API_KEY")
        if not self.mailgun_domain:
            missing.append("MAILGUN_DOMAIN")
            
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

@dataclass
class AppConfig:
    """Main application configuration"""
    secret_key: str
    debug: bool
    host: str
    port: int
    database_url: str
    
    # API configurations
    api: APIConfig
    
    # Service timeouts and limits
    api_timeout: int = 30
    max_retries: int = 3
    rate_limit_per_minute: int = 60
    max_conversation_context: int = 20
    
    @classmethod
    def from_environment(cls) -> 'AppConfig':
        """Create configuration from environment variables"""
        
        # Get API configuration
        api_config = APIConfig(
            openrouter_api_key=os.getenv('OPENROUTER_API_KEY', ''),
            supermemory_api_key=os.getenv('SUPERMEMORY_API_KEY', ''),
            mailgun_api_key=os.getenv('MAILGUN_API_KEY', ''),
            mailgun_domain=os.getenv('MAILGUN_DOMAIN', ''),
            mailgun_webhook_signing_key=os.getenv('MAILGUN_WEBHOOK_SIGNING_KEY', '')
        )
        
        return cls(
            secret_key=os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production'),
            debug=os.getenv('DEBUG', 'True').lower() == 'true',
            host=os.getenv('HOST', '0.0.0.0'),
            port=int(os.getenv('PORT', '5000')),
            database_url=os.getenv('DATABASE_URL', 'sqlite:///database/app.db'),
            api=api_config,
            api_timeout=int(os.getenv('API_TIMEOUT', '30')),
            max_retries=int(os.getenv('MAX_RETRIES', '3')),
            rate_limit_per_minute=int(os.getenv('RATE_LIMIT_PER_MINUTE', '60')),
            max_conversation_context=int(os.getenv('MAX_CONVERSATION_CONTEXT', '20'))
        )

    @property
    def openrouter_api_key(self) -> str:
        """Get OpenRouter API key"""
        return self.api.openrouter_api_key
    
    @property
    def supermemory_api_key(self) -> str:
        """Get Supermemory API key"""
        return self.api.supermemory_api_key
    
    @property
    def mailgun_api_key(self) -> str:
        """Get Mailgun API key"""
        return self.api.mailgun_api_key
    
    @property
    def mailgun_domain(self) -> str:
        """Get Mailgun domain"""
        return self.api.mailgun_domain
    
    @property
    def mailgun_webhook_signing_key(self) -> str:
        """Get Mailgun webhook signing key"""
        return self.api.mailgun_webhook_signing_key

# Global configuration instance
config = AppConfig.from_environment()

