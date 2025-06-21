"""
Memory Routes - API endpoints for conversation persistence and memory management
"""

import logging

from flask import Blueprint, jsonify, request

from src.config import config
from src.exceptions import ServiceError, SwarmException, ValidationError
from src.services.supermemory_service import MemoryQuery, SupermemoryService
from src.utils.response_helpers import create_error_response, create_success_response

logger = logging.getLogger(__name__)

# Create blueprint
memory_bp = Blueprint("memory", __name__)

# Initialize Supermemory service
try:
    supermemory_service = SupermemoryService(
        api_key=config.api.supermemory_api_key, base_url="https://api.supermemory.ai"
    )
    logger.info("Supermemory service initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize Supermemory service: {e}")
    supermemory_service = None


@memory_bp.route("/health", methods=["GET"])
def memory_health():
    """Check memory service health"""
    if not supermemory_service:
        return create_error_response(
            ServiceError("Supermemory service not initialized", "SERVICE_NOT_INITIALIZED"), 503
        )

    try:
        health_status = supermemory_service.health_check()
        return jsonify(create_success_response(health_status, "Memory service health check"))
    except Exception as e:
        logger.error(f"Memory health check failed: {e}")
        return create_error_response(
            ServiceError("Memory health check failed", "HEALTH_CHECK_FAILED"), 500
        )


@memory_bp.route("/conversations/<agent_id>", methods=["GET"])
def get_conversation_history(agent_id: str):
    """Get conversation history for a specific agent"""
    if not supermemory_service:
        return create_error_response(
            ServiceError("Supermemory service not initialized", "SERVICE_NOT_INITIALIZED"), 503
        )

    try:
        # Get optional limit parameter
        limit = request.args.get("limit", 20, type=int)
        if limit < 1 or limit > 100:
            raise ValidationError("Limit must be between 1 and 100", "INVALID_LIMIT")

        conversations = supermemory_service.get_conversation_history(agent_id, limit)

        # Convert to JSON-serializable format
        conversation_data = []
        for conv in conversations:
            conversation_data.append(
                {
                    "id": conv.id,
                    "agent_id": conv.agent_id,
                    "user_message": conv.user_message,
                    "agent_response": conv.agent_response,
                    "timestamp": conv.timestamp,
                    "model_used": conv.model_used,
                    "metadata": conv.metadata,
                }
            )

        return jsonify(
            create_success_response(
                {
                    "conversations": conversation_data,
                    "agent_id": agent_id,
                    "total": len(conversation_data),
                },
                f"Retrieved {len(conversation_data)} conversations for {agent_id}",
            )
        )

    except ValidationError as e:
        return create_error_response(e, 400)
    except ServiceError as e:
        logger.error(f"Error retrieving conversation history for {agent_id}: {e}")
        return create_error_response(e, 500)
    except Exception as e:
        logger.error(f"Unexpected error retrieving conversation history for {agent_id}: {e}")
        return create_error_response(SwarmException("Internal server error", "INTERNAL_ERROR"), 500)


@memory_bp.route("/conversations/<agent_id>", methods=["POST"])
def store_conversation(agent_id: str):
    """Store a new conversation entry"""
    if not supermemory_service:
        return create_error_response(
            ServiceError("Supermemory service not initialized", "SERVICE_NOT_INITIALIZED"), 503
        )

    try:
        # Validate request data
        if not request.is_json:
            raise ValidationError("Request must be JSON", "INVALID_CONTENT_TYPE")

        data = request.get_json()
        if not data:
            raise ValidationError("Request body cannot be empty", "EMPTY_BODY")

        # Extract required fields
        user_message = data.get("user_message")
        agent_response = data.get("agent_response")

        if not user_message or not user_message.strip():
            raise ValidationError(
                "user_message is required and cannot be empty", "MISSING_USER_MESSAGE"
            )

        if not agent_response or not agent_response.strip():
            raise ValidationError(
                "agent_response is required and cannot be empty", "MISSING_AGENT_RESPONSE"
            )

        # Extract optional fields
        model_used = data.get("model_used")
        metadata = data.get("metadata", {})

        # Store the conversation
        conversation_id = supermemory_service.store_conversation(
            agent_id=agent_id,
            user_message=user_message.strip(),
            agent_response=agent_response.strip(),
            model_used=model_used,
            metadata=metadata,
        )

        return (
            jsonify(
                create_success_response(
                    {"conversation_id": conversation_id, "agent_id": agent_id, "stored": True},
                    "Conversation stored successfully",
                )
            ),
            201,
        )

    except ValidationError as e:
        return create_error_response(e, 400)
    except ServiceError as e:
        logger.error(f"Error storing conversation for {agent_id}: {e}")
        return create_error_response(e, 500)
    except Exception as e:
        logger.error(f"Unexpected error storing conversation for {agent_id}: {e}")
        return create_error_response(SwarmException("Internal server error", "INTERNAL_ERROR"), 500)


@memory_bp.route("/search", methods=["POST"])
def search_memory():
    """Search memory for relevant context"""
    if not supermemory_service:
        return create_error_response(
            ServiceError("Supermemory service not initialized", "SERVICE_NOT_INITIALIZED"), 503
        )

    try:
        # Validate request data
        if not request.is_json:
            raise ValidationError("Request must be JSON", "INVALID_CONTENT_TYPE")

        data = request.get_json()
        if not data:
            raise ValidationError("Request body cannot be empty", "EMPTY_BODY")

        # Extract required fields
        query_text = data.get("query")
        if not query_text or not query_text.strip():
            raise ValidationError("query is required and cannot be empty", "MISSING_QUERY")

        # Extract optional fields
        agent_id = data.get("agent_id")
        limit = data.get("limit", 10)
        similarity_threshold = data.get("similarity_threshold", 0.7)

        # Validate optional fields
        if limit < 1 or limit > 50:
            raise ValidationError("limit must be between 1 and 50", "INVALID_LIMIT")

        if similarity_threshold < 0 or similarity_threshold > 1:
            raise ValidationError(
                "similarity_threshold must be between 0 and 1", "INVALID_THRESHOLD"
            )

        # Create memory query
        memory_query = MemoryQuery(
            query=query_text.strip(),
            agent_id=agent_id,
            limit=limit,
            similarity_threshold=similarity_threshold,
        )

        # Search memory
        results = supermemory_service.search_memory(memory_query)

        return jsonify(
            create_success_response(
                {
                    "results": results,
                    "query": query_text,
                    "agent_id": agent_id,
                    "total": len(results),
                },
                f"Found {len(results)} relevant memory items",
            )
        )

    except ValidationError as e:
        return create_error_response(e, 400)
    except ServiceError as e:
        logger.error(f"Error searching memory: {e}")
        return create_error_response(e, 500)
    except Exception as e:
        logger.error(f"Unexpected error searching memory: {e}")
        return create_error_response(SwarmException("Internal server error", "INTERNAL_ERROR"), 500)


@memory_bp.route("/context/<agent_id>", methods=["POST"])
def get_agent_context(agent_id: str):
    """Get relevant context for an agent based on current message"""
    if not supermemory_service:
        return create_error_response(
            ServiceError("Supermemory service not initialized", "SERVICE_NOT_INITIALIZED"), 503
        )

    try:
        # Validate request data
        if not request.is_json:
            raise ValidationError("Request must be JSON", "INVALID_CONTENT_TYPE")

        data = request.get_json()
        if not data:
            raise ValidationError("Request body cannot be empty", "EMPTY_BODY")

        # Extract required fields
        current_message = data.get("message")
        if not current_message or not current_message.strip():
            raise ValidationError("message is required and cannot be empty", "MISSING_MESSAGE")

        # Extract optional fields
        context_limit = data.get("context_limit", 5)

        # Validate optional fields
        if context_limit < 1 or context_limit > 20:
            raise ValidationError("context_limit must be between 1 and 20", "INVALID_CONTEXT_LIMIT")

        # Get agent context
        context = supermemory_service.get_agent_context(
            agent_id=agent_id, current_message=current_message.strip(), context_limit=context_limit
        )

        return jsonify(
            create_success_response(
                {
                    "context": context,
                    "agent_id": agent_id,
                    "message": current_message,
                    "has_context": bool(context.strip()),
                },
                "Agent context retrieved successfully",
            )
        )

    except ValidationError as e:
        return create_error_response(e, 400)
    except ServiceError as e:
        logger.error(f"Error getting agent context for {agent_id}: {e}")
        return create_error_response(e, 500)
    except Exception as e:
        logger.error(f"Unexpected error getting agent context for {agent_id}: {e}")
        return create_error_response(SwarmException("Internal server error", "INTERNAL_ERROR"), 500)


@memory_bp.route("/conversations/<agent_id>", methods=["DELETE"])
def clear_agent_memory(agent_id: str):
    """Clear all memory for a specific agent"""
    if not supermemory_service:
        return create_error_response(
            ServiceError("Supermemory service not initialized", "SERVICE_NOT_INITIALIZED"), 503
        )

    try:
        # Clear agent memory
        success = supermemory_service.clear_agent_memory(agent_id)

        if success:
            return jsonify(
                create_success_response(
                    {"agent_id": agent_id, "cleared": True}, f"Memory cleared for agent {agent_id}"
                )
            )
        else:
            return jsonify(
                create_success_response(
                    {"agent_id": agent_id, "cleared": False, "message": "No memory found to clear"},
                    f"No memory found for agent {agent_id}",
                )
            )

    except ServiceError as e:
        logger.error(f"Error clearing memory for {agent_id}: {e}")
        return create_error_response(e, 500)
    except Exception as e:
        logger.error(f"Unexpected error clearing memory for {agent_id}: {e}")
        return create_error_response(SwarmException("Internal server error", "INTERNAL_ERROR"), 500)
