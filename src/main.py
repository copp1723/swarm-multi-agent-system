import os
import sys
import logging
from datetime import datetime, timezone

# DON'T CHANGE THIS !!!
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Initialize Sentry before Flask app
import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration
from sentry_sdk.integrations.logging import LoggingIntegration

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO, emit # Namespace is no longer used directly here

# Import configuration
from src.config_flexible import get_config
from src.exceptions import SwarmException

# Import models
from src.models.user import db

# Import routes
from src.routes.user import user_bp
from src.routes.agents import agents_bp
from src.routes.auth import auth_bp
from src.routes.email import email_bp
from src.routes.mcp import mcp_bp
from src.routes.memory import memory_bp
from src.routes.security import security_bp
from src.routes.websocket import websocket_bp, init_websocket_routes
from src.routes.test import test_bp

# Import services
from src.services.auth_service import AuthenticationService
from src.services.security_service import SecurityHardeningService
from src.services.websocket_service import WebSocketService, SwarmWebSocketNamespace # Import the namespace

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def create_app(test_config=None):
    """Application factory pattern"""

    # Initialize Sentry for error tracking and performance monitoring
    sentry_logging = LoggingIntegration(
        level=logging.INFO,  # Capture info and above as breadcrumbs
        event_level=logging.ERROR,  # Send errors as events
    )

    sentry_sdk.init(
        dsn="https://2a6537a86356e27f4f6d4c351738cc25@o4509531702624256.ingest.us.sentry.io/4509539992862720",
        integrations=[
            FlaskIntegration(transaction_style="endpoint"),
            sentry_logging,
        ],
        # Performance Monitoring
        traces_sample_rate=0.1,  # Capture 10% of transactions for performance monitoring
        # Release tracking
        release="swarm-multi-agent-system@2.0.0",
        environment="production",
        # Add data like request headers and IP for users
        send_default_pii=True,
        # Additional options
        attach_stacktrace=True,
        max_breadcrumbs=50,
    )

    app = Flask(__name__, static_folder=os.path.join(os.path.dirname(__file__), "static"))

    # Load configuration
    config = get_config()

    # Apply test configuration if provided
    if test_config:
        app.config.update(test_config)
    else:
        # Production configuration
        app.config["SECRET_KEY"] = config.security.secret_key
        app.config["SQLALCHEMY_DATABASE_URI"] = config.database.url
        app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
            "pool_size": config.database.pool_size,
            "pool_timeout": config.database.pool_timeout,
            "pool_recycle": config.database.pool_recycle,
            "echo": config.database.echo,
        }

    # Enable CORS for all routes
    CORS(app, origins=config.api.cors_origins)

    # Initialize SocketIO with proper CORS handling
    # For production, we need to handle both HTTP and WebSocket origins
    cors_origins = config.api.cors_origins
    if cors_origins == ["*"]:
        # Allow all origins for development
        socketio_cors = "*"
    else:
        # For production, include both http and https versions
        socketio_cors = []
        for origin in cors_origins:
            socketio_cors.append(origin)
            # Also add the production domain if not already included
            if "swarm-multi-agent-system.onrender.com" not in origin:
                socketio_cors.extend([
                    "https://swarm-multi-agent-system.onrender.com",
                    "http://swarm-multi-agent-system.onrender.com"
                ])
        # Remove duplicates
        socketio_cors = list(set(socketio_cors))
    
    socketio = SocketIO(app, cors_allowed_origins=socketio_cors, 
                       async_mode='threading', logger=True, engineio_logger=True)

    # Initialize database
    db.init_app(app)

    # Initialize services
    auth_service = AuthenticationService(
        secret_key=config.security.secret_key, token_expiry_hours=config.security.jwt_expiry_hours
    )

    security_service = SecurityHardeningService(config.to_dict())

    # Initialize MCP Filesystem service
    from src.services.mcp_filesystem import MCPFilesystemService
    mcp_filesystem_service = MCPFilesystemService(
        base_path="/tmp/swarm_workspace",  # Secure workspace path
        max_file_size=10 * 1024 * 1024  # 10MB limit
    )

    # Initialize WebSocket service with MCP filesystem
    websocket_service = WebSocketService(app, mcp_filesystem_service=mcp_filesystem_service)

    # Store services in app context
    app.websocket_service = websocket_service # Ensure this is before SwarmWebSocketNamespace instantiation
    app.auth_service = auth_service
    app.security_service = security_service
    app.websocket_service = websocket_service
    app.mcp_filesystem_service = mcp_filesystem_service
    app.config_manager = config

    # Initialize WebSocket routes with service instance
    init_websocket_routes(websocket_service)

    # Register blueprints
    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(user_bp, url_prefix="/api/users")
    app.register_blueprint(agents_bp, url_prefix="/api/agents")
    app.register_blueprint(memory_bp, url_prefix="/api/memory")
    app.register_blueprint(email_bp, url_prefix="/api/email")
    app.register_blueprint(security_bp, url_prefix="/api/security")
    app.register_blueprint(websocket_bp, url_prefix="/api/websocket")
    app.register_blueprint(test_bp, url_prefix="/api/test")
    
    # Import and register MCP blueprint
    from src.routes.mcp import mcp_bp
    app.register_blueprint(mcp_bp)

    # Create database tables with retry logic for Render deployment
    with app.app_context():
        database_ready = False
        try:
            # Check if we're using PostgreSQL (production) or SQLite (development)
            if config.database.is_postgresql:
                logger.info(f"Using PostgreSQL database: {config.database.url[:50]}...")
                # For PostgreSQL, try to connect with retries
                import time
                from sqlalchemy import text

                max_retries = 5
                for attempt in range(max_retries):
                    try:
                        # Test database connection first
                        db.session.execute(text("SELECT 1"))
                        db.session.commit()
                        # If connection works, create tables
                        db.create_all()
                        logger.info("PostgreSQL database tables created successfully")
                        database_ready = True
                        break
                    except Exception as e:
                        if attempt < max_retries - 1:
                            logger.warning(
                                f"Database connection attempt {attempt + 1} failed, retrying in 3 seconds: {e}"
                            )
                            time.sleep(3)
                        else:
                            logger.error(
                                f"Failed to connect to PostgreSQL database after {max_retries} attempts: {e}"
                            )
                            logger.warning(
                                "Application will start without database - some features may not work"
                            )
            else:
                # SQLite for development
                db.create_all()
                logger.info("SQLite database tables created successfully")
                database_ready = True
        except Exception as e:
            logger.error(f"Failed to create database tables: {e}")
            logger.warning("Application will start without database - some features may not work")

        # Store database status in app context
        app.database_ready = database_ready

    # Global error handlers
    @app.errorhandler(SwarmException)
    def handle_swarm_exception(error):
        """Global error handler for SwarmException"""
        logger.error(f"SwarmException: {error.message}")
        return (
            jsonify({"success": False, "error": error.message, "error_code": error.error_code}),
            error.status_code,
        )

    @app.errorhandler(404)
    def handle_not_found(error):
        """Handle 404 errors"""
        return (
            jsonify({"success": False, "error": "Resource not found", "error_code": "NOT_FOUND"}),
            404,
        )

    @app.errorhandler(500)
    def handle_internal_error(error):
        """Handle 500 errors"""
        logger.error(f"Internal server error: {error}")
        return (
            jsonify(
                {"success": False, "error": "Internal server error", "error_code": "INTERNAL_ERROR"}
            ),
            500,
        )

    # Security middleware
    @app.before_request
    def security_middleware():
        """Apply security checks to all requests"""
        try:
            # Skip security checks for health endpoints
            if request.endpoint and "health" in request.endpoint:
                return

            # Check if IP is blocked
            client_ip = security_service.get_client_ip(request)
            if security_service.check_ip_blocked(client_ip):
                security_service.log_security_event(
                    event_type="blocked_ip_attempt",
                    user_id=None,
                    ip_address=client_ip,
                    user_agent=request.headers.get("User-Agent", ""),
                    endpoint=request.endpoint or request.path,
                    details={},
                    severity="high",
                )
                # Use SwarmException for standardized error handling
                raise SwarmException("Access denied", "ACCESS_DENIED", status_code=403)

        except SwarmException: # Re-raise SwarmExceptions to be caught by global handler
            raise
        except Exception as e:
            logger.error(f"Security middleware error: {e}")
            # Don't block requests on security middleware errors
            pass

    @app.after_request
    def after_request(response):
        """Add security headers to all responses"""
        try:
            headers = security_service.get_security_headers()
            for key, value in headers.items():
                response.headers[key] = value
        except Exception as e:
            logger.error(f"Failed to add security headers: {e}")

        return response

    # Health check endpoint
    @app.route("/health")
    def health_check():
        """Application health check"""
        try:
            # Check database connection
            db_status = "healthy"
            try:
                from sqlalchemy import text

                db.session.execute(text("SELECT 1"))
                db.session.commit()
            except Exception as e:
                db_status = f"unhealthy: {str(e)}"

            # Get enabled services
            enabled_services = config.get_enabled_services()

            return jsonify(
                {
                    "success": True,
                    "status": "healthy",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "version": "2.0.0",
                    "database": {
                        "status": db_status,
                        "type": "postgresql" if config.database.is_postgresql else "sqlite",
                    },
                    "services": {"enabled": enabled_services, "count": len(enabled_services)},
                    "features": {
                        "user_registration": True,
                        "websocket_support": True,
                        "streaming_responses": True,
                    },
                    "system_health": "operational",
                }
            )

        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return (
                jsonify(
                    {
                        "success": False,
                        "status": "unhealthy",
                        "error": str(e),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                ),
                500,
            )

    # Sentry test endpoint (remove in production)
    @app.route("/sentry-debug")
    def trigger_error():
        """Test endpoint to verify Sentry integration"""
        logger.info("Sentry test endpoint triggered")
        division_by_zero = 1 / 0  # This will trigger a Sentry error
        return "This should not be reached"

    # Serve static files
    @app.route("/")
    def serve_index():
        """Serve the main application"""
        return send_from_directory(app.static_folder, "index.html")

    @app.route("/<path:path>")
    def serve_static(path):
        """Serve static files"""
        try:
            return send_from_directory(app.static_folder, path)
        except FileNotFoundError:
            # For SPA routing, return index.html for unknown routes
            return send_from_directory(app.static_folder, "index.html")

    # Configuration endpoint
    @app.route("/api/config")
    def get_config_endpoint():
        """Get public configuration"""
        return jsonify(
            {
                "success": True,
                "config": {
                    "features": {
                        "user_registration": True,
                        "websocket_support": True,
                        "streaming_responses": True,
                    },
                    "services": {
                        "enabled": config.get_enabled_services(),
                        "count": len(config.get_enabled_services()),
                    },
                    "version": "2.0.0",
                    "environment": "production" if not config.debug else "development",
                },
            }
        )

    logger.info(f"Swarm Multi-Agent System v2.0 initialized")
    logger.info(f"Database: {'PostgreSQL' if config.database.is_postgresql else 'SQLite'}")
    logger.info(f"Available services: {', '.join(config.get_enabled_services())}")
    logger.info(f"Features enabled: user_registration_enabled")

    # Store socketio in app context for access in other modules
    app.socketio = socketio

    return app, socketio


# Create the application instance
app, socketio = create_app()

# Register the Swarm namespace using the one from websocket_service
# Ensure app.websocket_service is set before this in create_app()
socketio.on_namespace(SwarmWebSocketNamespace(app.websocket_service))

if __name__ == "__main__":
    # Development server
    config = get_config()
    socketio.run(app, host=config.host, port=config.port, debug=config.debug)
