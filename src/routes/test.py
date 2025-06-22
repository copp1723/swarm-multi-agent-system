"""
Test route for OpenRouter API functionality
"""

from flask import Blueprint, jsonify, request
from src.services.openrouter_service import OpenRouterService
import logging

logger = logging.getLogger(__name__)

test_bp = Blueprint("test", __name__)


@test_bp.route("/test-openrouter", methods=["POST"])
def test_openrouter():
    """Test OpenRouter API functionality"""
    try:
        data = request.get_json()
        message = data.get("message", "Hello, can you respond with a simple greeting?")
        
        logger.info(f"Testing OpenRouter API with message: {message}")
        
        # Create OpenRouter service
        openrouter_service = OpenRouterService()
        
        # Test simple non-streaming chat completion first
        messages = [
            {"role": "user", "content": message}
        ]
        
        logger.info("Testing non-streaming chat completion")
        response = openrouter_service.chat_completion_with_messages(
            messages, 
            model="openai/gpt-4o", 
            stream=False
        )
        
        logger.info(f"Non-streaming response: {response}")
        
        return jsonify({
            "success": True,
            "message": "OpenRouter API test successful",
            "response": response.content,
            "model": response.model,
            "usage": response.usage
        })
        
    except Exception as e:
        logger.error(f"OpenRouter test failed: {e}")
        return jsonify({
            "success": False,
            "error": str(e),
            "error_type": type(e).__name__,
            "message": "OpenRouter API test failed"
        }), 500

