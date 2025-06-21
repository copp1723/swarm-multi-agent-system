import os
import sys

# DON'T CHANGE THIS !!!
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import logging
from datetime import datetime, timezone

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

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

# Import services
from src.services.auth_service import AuthenticationService
from src.services.security_service import SecurityHardeningService
from src.services.websocket_service import WebSocketService

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def create_app(test_config=None):
    """Application factory pattern"""
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

    # Initialize database
    db.init_app(app)

    # Initialize services
    auth_service = AuthenticationService(
        secret_key=config.security.secret_key, token_expiry_hours=config.security.jwt_expiry_hours
    )

    security_service = SecurityHardeningService(config.to_dict())
    
    # Initialize WebSocket service
    websocket_service = WebSocketService(app)

    # Store services in app context
    app.auth_service = auth_service
    app.security_service = security_service
    app.websocket_service = websocket_service
    app.config_manager = config

    # Initialize WebSocket routes with service instance
    init_websocket_routes(websocket_service)

    # Register blueprints
    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(user_bp, url_prefix="/api/users")
    app.register_blueprint(agents_bp, url_prefix="/api/agents")
    app.register_blueprint(memory_bp, url_prefix="/api/memory")
    app.register_blueprint(mcp_bp, url_prefix="/api/mcp")
    app.register_blueprint(email_bp, url_prefix="/api/email")
    app.register_blueprint(security_bp, url_prefix="/api/security")
    app.register_blueprint(websocket_bp, url_prefix="/api/websocket")

    # Create database tables
    with app.app_context():
        try:
            db.create_all()
            logger.info("Database tables created successfully")
        except Exception as e:
            logger.error(f"Failed to create database tables: {e}")

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
                return jsonify({"error": "Access denied"}), 403

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
                db.session.execute("SELECT 1")
                db.session.commit()
            except Exception as e:
                db_status = f"unhealthy: {str(e)}"

            # Get system status
            system_status = config.get_system_status()
            feature_flags = config.get_feature_flags()

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
                    "services": system_status["services"],
                    "features": feature_flags,
                    "system_health": system_status["system_health"],
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
                    "features": config.get_feature_flags(),
                    "system_status": config.get_system_status(),
                    "version": "2.0.0",
                    "environment": "production" if not config.debug else "development",
                },
            }
        )

    logger.info(f"Swarm Multi-Agent System v2.0 initialized")
    logger.info(f"Database: {'PostgreSQL' if config.database.is_postgresql else 'SQLite'}")
    logger.info(f"Available services: {', '.join(config.get_available_services())}")
    logger.info(
        f"Features enabled: {', '.join([k for k, v in config.get_feature_flags().items() if v])}"
    )

    return app


# Create the application instance
app = create_app()

if __name__ == "__main__":
    # Development server
    config = get_config()
    app.run(host=config.host, port=config.port, debug=config.debug)
