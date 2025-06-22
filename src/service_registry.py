"""
Service Registry - Dependency Injection container for managing service singletons

This module implements a centralized service registry that follows the Service Registry pattern
and provides dependency injection capabilities. All services are registered as singletons
to ensure consistent state across the application.

Key Features:
- Singleton pattern for all services
- Lazy initialization of services
- Automatic dependency resolution
- Configuration-driven service enablement
- Error handling and fallback mechanisms
- Health checking and monitoring
"""

import logging
import os
from typing import Any, Dict, Optional, Type, TypeVar, Union

from src.config_flexible import get_config
from src.exceptions import ServiceError

# Import service classes
from src.services.openrouter_service import OpenRouterService
from src.services.supermemory_service import SupermemoryService
from src.services.mcp_filesystem import MCPFilesystemService
from src.services.agent_service import AgentService

logger = logging.getLogger(__name__)

# Type variable for generic service types
T = TypeVar('T')


class ServiceRegistry:
    """
    Centralized service registry implementing dependency injection pattern.
    
    This registry manages service lifecycles, ensures singleton instances,
    and handles service dependencies automatically. Services are lazily
    initialized when first requested.
    """
    
    def __init__(self):
        """Initialize the service registry with empty service cache."""
        self._services: Dict[str, Any] = {}
        self._config = get_config()
        self._initialized = False
        
        logger.info("Service Registry initialized")
    
    def _initialize_services(self) -> None:
        """
        Initialize all service registrations.
        
        This method registers all available services with their dependencies.
        Services are not instantiated here, only registered for lazy loading.
        """
        if self._initialized:
            return
            
        logger.info("Registering services in dependency injection container...")
        
        # Register service factories with their dependencies
        self._service_factories = {
            'openrouter': self._create_openrouter_service,
            'supermemory': self._create_supermemory_service,
            'mcp_filesystem': self._create_mcp_filesystem_service,
            'agent': self._create_agent_service,
        }
        
        self._initialized = True
        logger.info(f"Registered {len(self._service_factories)} service factories")
    
    def _create_openrouter_service(self) -> OpenRouterService:
        """
        Create OpenRouter service instance.
        
        Returns:
            OpenRouterService: Configured OpenRouter service instance
            
        Raises:
            ServiceError: If OpenRouter API key is not configured
        """
        config = self._config
        
        if not config.api.openrouter_api_key:
            raise ServiceError(
                "OpenRouter API key not configured",
                error_code="MISSING_API_KEY",
                details={"service": "openrouter", "required_env": "OPENROUTER_API_KEY"}
            )
        
        logger.info("Creating OpenRouter service instance")
        return OpenRouterService()
    
    def _create_supermemory_service(self) -> Optional[SupermemoryService]:
        """
        Create Supermemory service instance.
        
        This service is optional and will return None if not configured.
        
        Returns:
            Optional[SupermemoryService]: Configured Supermemory service or None
        """
        config = self._config
        
        if not config.api.supermemory_api_key:
            logger.warning("Supermemory API key not configured - service will be unavailable")
            return None
        
        logger.info("Creating Supermemory service instance")
        return SupermemoryService(
            api_key=config.api.supermemory_api_key,
            base_url="https://api.supermemory.ai"
        )
    
    def _create_mcp_filesystem_service(self) -> MCPFilesystemService:
        """
        Create MCP Filesystem service instance.
        
        This service provides secure filesystem access for agents.
        
        Returns:
            MCPFilesystemService: Configured MCP filesystem service
        """
        # Use environment variable for workspace path, with sensible default
        base_path = os.getenv("MCP_WORKSPACE_PATH", "/tmp/swarm_workspace")
        max_file_size = int(os.getenv("MCP_MAX_FILE_SIZE", str(10 * 1024 * 1024)))  # 10MB default
        
        logger.info(f"Creating MCP Filesystem service - workspace: {base_path}")
        return MCPFilesystemService(
            base_path=base_path,
            max_file_size=max_file_size
        )
    
    def _create_agent_service(self) -> AgentService:
        """
        Create Agent service instance with all dependencies.
        
        This method demonstrates dependency resolution by injecting required services.
        
        Returns:
            AgentService: Configured agent service with dependencies
            
        Raises:
            ServiceError: If required dependencies are not available
        """
        logger.info("Creating Agent service with dependencies")
        
        # Get required OpenRouter service
        openrouter_service = self.get_service('openrouter')
        if not openrouter_service:
            raise ServiceError(
                "OpenRouter service is required for Agent service",
                error_code="MISSING_DEPENDENCY",
                details={"service": "agent", "missing_dependency": "openrouter"}
            )
        
        # Get optional services
        supermemory_service = self.get_service('supermemory')
        mcp_filesystem_service = self.get_service('mcp_filesystem')
        
        # Log dependency status
        dependencies_status = {
            "openrouter": "available",
            "supermemory": "available" if supermemory_service else "unavailable",
            "mcp_filesystem": "available" if mcp_filesystem_service else "unavailable"
        }
        logger.info(f"Agent service dependencies: {dependencies_status}")
        
        return AgentService(
            openrouter_service=openrouter_service,
            supermemory_service=supermemory_service,
            mcp_filesystem_service=mcp_filesystem_service
        )
    
    def get_service(self, name: str) -> Optional[Any]:
        """
        Get a service instance by name.
        
        Services are created as singletons - the same instance is returned
        for multiple calls with the same name.
        
        Args:
            name: Service name (openrouter, supermemory, mcp_filesystem, agent)
            
        Returns:
            Optional[Any]: Service instance or None if service unavailable
            
        Raises:
            ServiceError: If service creation fails
        """
        self._initialize_services()
        
        # Return cached instance if available
        if name in self._services:
            return self._services[name]
        
        # Check if service factory exists
        if name not in self._service_factories:
            logger.error(f"Unknown service requested: {name}")
            available_services = list(self._service_factories.keys())
            raise ServiceError(
                f"Unknown service: {name}",
                error_code="UNKNOWN_SERVICE",
                details={"requested_service": name, "available_services": available_services}
            )
        
        try:
            # Create service instance using factory
            logger.info(f"Instantiating service: {name}")
            service_instance = self._service_factories[name]()
            
            # Cache the instance (including None for optional services)
            self._services[name] = service_instance
            
            if service_instance is None:
                logger.warning(f"Service '{name}' is not available (optional service not configured)")
            else:
                logger.info(f"✅ Service '{name}' successfully created and cached")
            
            return service_instance
            
        except Exception as e:
            logger.error(f"❌ Failed to create service '{name}': {str(e)}")
            
            # Cache None to prevent repeated failed attempts
            self._services[name] = None
            
            # Re-raise as ServiceError for consistent error handling
            if isinstance(e, ServiceError):
                raise
            else:
                raise ServiceError(
                    f"Failed to create service '{name}': {str(e)}",
                    error_code="SERVICE_CREATION_FAILED",
                    details={"service": name, "error": str(e)}
                )
    
    def is_service_available(self, name: str) -> bool:
        """
        Check if a service is available without creating it.
        
        Args:
            name: Service name to check
            
        Returns:
            bool: True if service is available, False otherwise
        """
        try:
            service = self.get_service(name)
            return service is not None
        except ServiceError:
            return False
    
    def get_service_status(self) -> Dict[str, Dict[str, Any]]:
        """
        Get status of all registered services.
        
        Returns:
            Dict[str, Dict[str, Any]]: Status information for each service
        """
        self._initialize_services()
        
        status = {}
        
        for service_name in self._service_factories.keys():
            try:
                # Check if service is cached
                is_cached = service_name in self._services
                
                # Try to get service instance
                service_instance = self.get_service(service_name)
                is_available = service_instance is not None
                
                # Get health status if service supports it
                health_status = None
                if service_instance and hasattr(service_instance, 'health_check'):
                    try:
                        health_status = service_instance.health_check()
                    except Exception as e:
                        health_status = {"status": "error", "error": str(e)}
                
                status[service_name] = {
                    "available": is_available,
                    "cached": is_cached,
                    "health": health_status,
                    "type": type(service_instance).__name__ if service_instance else None
                }
                
            except Exception as e:
                status[service_name] = {
                    "available": False,
                    "cached": False,
                    "error": str(e),
                    "health": None,
                    "type": None
                }
        
        return status
    
    def clear_cache(self) -> None:
        """
        Clear the service cache.
        
        This forces all services to be recreated on next access.
        Useful for testing or when configuration changes.
        """
        logger.info("Clearing service cache")
        self._services.clear()
    
    def shutdown(self) -> None:
        """
        Shutdown all services gracefully.
        
        This method calls shutdown methods on services that support it
        and clears the service cache.
        """
        logger.info("Shutting down service registry...")
        
        for service_name, service_instance in self._services.items():
            if service_instance and hasattr(service_instance, 'shutdown'):
                try:
                    logger.info(f"Shutting down service: {service_name}")
                    service_instance.shutdown()
                except Exception as e:
                    logger.error(f"Error shutting down service '{service_name}': {e}")
        
        self.clear_cache()
        logger.info("Service registry shutdown complete")


# Global service registry instance
_registry_instance: Optional[ServiceRegistry] = None


def get_registry() -> ServiceRegistry:
    """
    Get the global service registry instance.
    
    This function implements the singleton pattern for the service registry.
    
    Returns:
        ServiceRegistry: The global service registry instance
    """
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = ServiceRegistry()
    return _registry_instance


def get_service(name: str) -> Optional[Any]:
    """
    Convenience function to get a service from the global registry.
    
    This is the main API that blueprints should use to access services.
    
    Args:
        name: Service name (openrouter, supermemory, mcp_filesystem, agent)
        
    Returns:
        Optional[Any]: Service instance or None if not available
        
    Example:
        >>> from src.service_registry import get_service
        >>> 
        >>> # Get the agent service
        >>> agent_service = get_service('agent')
        >>> if agent_service:
        >>>     response = agent_service.chat_with_agent('email_agent', 'Hello!')
        >>> 
        >>> # Get OpenRouter service directly
        >>> openrouter = get_service('openrouter')
        >>> if openrouter:
        >>>     models = openrouter.get_available_models()
        >>> 
        >>> # Get MCP filesystem service
        >>> mcp_fs = get_service('mcp_filesystem')
        >>> if mcp_fs:
        >>>     files = mcp_fs.list_directory('/', 'agent_123')
    """
    return get_registry().get_service(name)


# Convenience functions for specific services
def get_openrouter_service() -> Optional[OpenRouterService]:
    """Get the OpenRouter service instance."""
    return get_service('openrouter')


def get_supermemory_service() -> Optional[SupermemoryService]:
    """Get the Supermemory service instance."""
    return get_service('supermemory')


def get_mcp_filesystem_service() -> Optional[MCPFilesystemService]:
    """Get the MCP Filesystem service instance."""
    return get_service('mcp_filesystem')


def get_agent_service() -> Optional[AgentService]:
    """Get the Agent service instance."""
    return get_service('agent')


# Service status and management functions
def is_service_available(name: str) -> bool:
    """Check if a service is available."""
    return get_registry().is_service_available(name)


def get_all_service_status() -> Dict[str, Dict[str, Any]]:
    """Get status of all services."""
    return get_registry().get_service_status()


def clear_service_cache() -> None:
    """Clear the service cache."""
    get_registry().clear_cache()


def shutdown_services() -> None:
    """Shutdown all services."""
    get_registry().shutdown()
