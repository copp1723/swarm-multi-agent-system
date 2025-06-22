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
        
        # Create OpenRouter service
        openrouter_service = OpenRouterService()
        
        # Test simple chat completion
        messages = [
            {"role": "user", "content": message}
        ]
        
        # Try streaming
        response_chunks = []
        for chunk in openrouter_service.stream_chat_completion(messages, "openai/gpt-4o"):
            if chunk and "choices" in chunk and len(chunk["choices"]) > 0:
                delta = chunk["choices"][0].get("delta", {})
                content = delta.get("content", "")
                if content:
                    response_chunks.append(content)
        
        full_response = "".join(response_chunks)
        
        return jsonify({
            "success": True,
            "message": "OpenRouter API test successful",
            "response": full_response,
            "chunks_received": len(response_chunks)
        })
        
    except Exception as e:
        logger.error(f"OpenRouter test failed: {e}")
        return jsonify({
            "success": False,
            "error": str(e),
            "message": "OpenRouter API test failed"
        }), 500

