import os
import sys
# DON'T CHANGE THIS !!!
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from flask import Flask, send_from_directory
from flask_cors import CORS
import logging
from src.models.user import db
from src.routes.user import user_bp
from src.routes.agents import agents_bp
from src.routes.memory import memory_bp
from src.routes.mcp import mcp_bp
from src.routes.email import email_bp
from src.config import config
from src.exceptions import SwarmException

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder=os.path.join(os.path.dirname(__file__), 'static'))
app.config['SECRET_KEY'] = config.secret_key

# Enable CORS for all routes
CORS(app, origins="*")

# Register blueprints
app.register_blueprint(user_bp, url_prefix='/api/users')
app.register_blueprint(agents_bp, url_prefix='/api/agents')
app.register_blueprint(memory_bp, url_prefix='/api/memory')
app.register_blueprint(mcp_bp, url_prefix='/api/mcp')
app.register_blueprint(email_bp, url_prefix='/api/email')

# Database configuration
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{os.path.join(os.path.dirname(__file__), 'database', 'app.db')}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

with app.app_context():
    db.create_all()

@app.errorhandler(SwarmException)
def handle_swarm_exception(error):
    """Global error handler for SwarmException"""
    logger.error(f"SwarmException: {error.message}")
    return {
        "success": False,
        "error": {
            "code": error.error_code,
            "message": error.message,
            "details": error.details
        }
    }, 500

@app.errorhandler(404)
def handle_not_found(error):
    """Handle 404 errors"""
    return {
        "success": False,
        "error": {
            "code": "NOT_FOUND",
            "message": "Resource not found",
            "details": {}
        }
    }, 404

@app.errorhandler(500)
def handle_internal_error(error):
    """Handle 500 errors"""
    logger.error(f"Internal server error: {error}")
    return {
        "success": False,
        "error": {
            "code": "INTERNAL_ERROR",
            "message": "Internal server error",
            "details": {}
        }
    }, 500

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve(path):
    static_folder_path = app.static_folder
    if static_folder_path is None:
        return "Static folder not configured", 404

    if path != "" and os.path.exists(os.path.join(static_folder_path, path)):
        return send_from_directory(static_folder_path, path)
    else:
        index_path = os.path.join(static_folder_path, 'index.html')
        if os.path.exists(index_path):
            return send_from_directory(static_folder_path, 'index.html')
        else:
            return "index.html not found", 404

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return {
        "success": True,
        "status": "healthy",
        "version": "2.0.0"
    }

if __name__ == '__main__':
    logger.info(f"Starting Swarm Multi-Agent System v2.0")
    logger.info(f"Debug mode: {config.debug}")
    app.run(host=config.host, port=config.port, debug=config.debug)
