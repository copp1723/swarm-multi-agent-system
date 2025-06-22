"""
Simple test server to run the UI without requiring API keys
"""

import os
from flask import Flask, send_from_directory, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# Serve static files
@app.route("/")
def serve_index():
    """Serve the main application"""
    return send_from_directory(os.path.join(os.path.dirname(__file__), "static"), "index.html")

@app.route("/<path:path>")
def serve_static(path):
    """Serve static files"""
    try:
        return send_from_directory(os.path.join(os.path.dirname(__file__), "static"), path)
    except FileNotFoundError:
        # For SPA routing, return index.html for unknown routes
        return send_from_directory(os.path.join(os.path.dirname(__file__), "static"), "index.html")

# Mock API endpoints for UI testing
@app.route("/api/agents/", methods=["GET"])
def list_agents():
    """Mock agent list endpoint"""
    return jsonify({
        "success": True,
        "data": {
            "agents": {
                "email_agent": {
                    "agent_id": "email_agent",
                    "name": "Email Agent",
                    "description": "Professional email composition and management",
                    "capabilities": ["email_composition", "email_analysis", "professional_writing"],
                    "status": "available"
                },
                "calendar_agent": {
                    "agent_id": "calendar_agent",
                    "name": "Calendar Agent",
                    "description": "Scheduling and time management",
                    "capabilities": ["scheduling", "meeting_management", "time_optimization"],
                    "status": "available"
                },
                "code_agent": {
                    "agent_id": "code_agent",
                    "name": "Code Agent",
                    "description": "Software development and debugging assistance",
                    "capabilities": ["code_generation", "debugging", "technical_analysis"],
                    "status": "available"
                },
                "debug_agent": {
                    "agent_id": "debug_agent",
                    "name": "Debug Agent",
                    "description": "Troubleshooting and system diagnostics",
                    "capabilities": ["error_analysis", "troubleshooting", "system_diagnostics"],
                    "status": "available"
                },
                "general_agent": {
                    "agent_id": "general_agent",
                    "name": "General Agent",
                    "description": "Task coordination and general assistance",
                    "capabilities": ["task_coordination", "general_assistance", "information_synthesis"],
                    "status": "available"
                }
            },
            "total_count": 5,
            "timestamp": "2025-01-01T00:00:00Z"
        }
    })

@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint"""
    return jsonify({
        "success": True,
        "status": "healthy",
        "message": "UI test server running"
    })

if __name__ == "__main__":
    print("\n🚀 Starting UI test server...")
    print("📍 Navigate to: http://localhost:5002")
    print("⚠️  This is a test server for UI development only - no actual API functionality\n")
    app.run(host="0.0.0.0", port=5002, debug=True)
