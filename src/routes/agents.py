"""
Agent API routes with comprehensive error handling and validation
"""

import logging
from typing import Any, Dict

from flask import Blueprint, jsonify, request

from src.config import config
from src.exceptions import AgentNotFoundError, SwarmException, ValidationError
from src.services.agent_service import AgentService
from src.services.openrouter_service import OpenRouterService
from src.services.supermemory_service import SupermemoryService

logger = logging.getLogger(__name__)

# Initialize services
openrouter_service = OpenRouterService()

# Initialize Supermemory service if API key is available
supermemory_service = None
if config.api.supermemory_api_key:
    try:
        supermemory_service = SupermemoryService(config.api.supermemory_api_key)
        logger.info("Supermemory service initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize Supermemory service: {e}")

agent_service = AgentService(openrouter_service, supermemory_service)

agents_bp = Blueprint("agents", __name__)


def create_error_response(error: SwarmException, status_code: int = 400) -> tuple:
    """Create standardized error response"""
    return (
        jsonify(
            {
                "success": False,
                "error": {
                    "code": error.error_code,
                    "message": error.message,
                    "details": error.details,
                },
            }
        ),
        status_code,
    )


def create_success_response(data: Any, message: str = None) -> Dict[str, Any]:
    """Create standardized success response"""
    response = {"success": True, "data": data}
    if message:
        response["message"] = message
    return response


@agents_bp.route("/", methods=["GET"])
def list_agents():
    """Get list of all available agents"""
    try:
        agents = agent_service.list_all_agents()
        return jsonify(
            create_success_response({"agents": agents}, f"Retrieved {len(agents)} agents")
        )
    except SwarmException as e:
        logger.error(f"Error listing agents: {e}")
        return create_error_response(e, 500)
    except Exception as e:
        logger.error(f"Unexpected error listing agents: {e}")
        return create_error_response(SwarmException("Internal server error", "INTERNAL_ERROR"), 500)


@agents_bp.route("/<agent_id>", methods=["GET"])
def get_agent(agent_id: str):
    """Get specific agent information"""
    try:
        agent_info = agent_service.get_agent_info(agent_id)
        return jsonify(
            create_success_response({"agent": agent_info}, f"Retrieved agent {agent_id}")
        )
    except AgentNotFoundError as e:
        return create_error_response(e, 404)
    except SwarmException as e:
        logger.error(f"Error getting agent {agent_id}: {e}")
        return create_error_response(e, 500)
    except Exception as e:
        logger.error(f"Unexpected error getting agent {agent_id}: {e}")
        return create_error_response(SwarmException("Internal server error", "INTERNAL_ERROR"), 500)


@agents_bp.route("/<agent_id>/chat", methods=["POST"])
def chat_with_agent(agent_id: str):
    """Chat with a specific agent"""
    try:
        # Validate request data
        if not request.is_json:
            raise ValidationError("Request must be JSON", "INVALID_CONTENT_TYPE")

        data = request.get_json()
        if not data:
            raise ValidationError("Request body cannot be empty", "EMPTY_BODY")

        # Extract and validate required fields
        message = data.get("message")
        if not message or not message.strip():
            raise ValidationError("Message is required and cannot be empty", "MISSING_MESSAGE")

        # Optional fields
        conversation_history = data.get("conversation_history", [])
        model = data.get("model")

        # Validate conversation history format
        if conversation_history and not isinstance(conversation_history, list):
            raise ValidationError("Conversation history must be a list", "INVALID_HISTORY_FORMAT")

        for i, msg in enumerate(conversation_history):
            if not isinstance(msg, dict) or "role" not in msg or "content" not in msg:
                raise ValidationError(
                    f"Invalid message format at index {i}",
                    "INVALID_MESSAGE_FORMAT",
                    {"index": i, "required_fields": ["role", "content"]},
                )

        # Chat with agent
        response = agent_service.chat_with_agent(
            agent_id=agent_id,
            message=message,
            conversation_history=conversation_history,
            model=model,
        )

        return jsonify(
            create_success_response(
                {
                    "response": response.content,
                    "model_used": response.model,
                    "agent_id": agent_id,
                    "usage": response.usage,
                },
                "Chat completed successfully",
            )
        )

    except ValidationError as e:
        return create_error_response(e, 400)
    except AgentNotFoundError as e:
        return create_error_response(e, 404)
    except SwarmException as e:
        logger.error(f"Error chatting with agent {agent_id}: {e}")
        return create_error_response(e, 500)
    except Exception as e:
        logger.error(f"Unexpected error chatting with agent {agent_id}: {e}")
        return create_error_response(SwarmException("Internal server error", "INTERNAL_ERROR"), 500)


@agents_bp.route("/models", methods=["GET"])
def get_available_models():
    """Get list of available AI models"""
    try:
        models = openrouter_service.get_available_models()

        # Convert to simple format for frontend
        model_list = []
        for model in models:
            model_list.append(
                {
                    "id": model.id,
                    "name": model.name,
                    "description": (
                        model.description[:200] + "..."
                        if len(model.description) > 200
                        else model.description
                    ),
                    "context_length": model.context_length,
                }
            )

        return jsonify(
            create_success_response({"models": model_list}, f"Retrieved {len(model_list)} models")
        )

    except SwarmException as e:
        logger.error(f"Error getting models: {e}")
        return create_error_response(e, 500)
    except Exception as e:
        logger.error(f"Unexpected error getting models: {e}")
        return create_error_response(SwarmException("Internal server error", "INTERNAL_ERROR"), 500)


@agents_bp.route("/suggest", methods=["POST"])
def suggest_agents():
    """Suggest appropriate agents for a task"""
    try:
        if not request.is_json:
            raise ValidationError("Request must be JSON", "INVALID_CONTENT_TYPE")

        data = request.get_json()
        if not data:
            raise ValidationError("Request body cannot be empty", "EMPTY_BODY")

        task_description = data.get("task_description")
        if not task_description or not task_description.strip():
            raise ValidationError("Task description is required", "MISSING_TASK_DESCRIPTION")

        suggestions = agent_service.suggest_agent_for_task(task_description)

        # Get full agent info for suggestions
        suggested_agents = []
        for agent_id in suggestions:
            try:
                agent_info = agent_service.get_agent_info(agent_id)
                suggested_agents.append(agent_info)
            except AgentNotFoundError:
                continue

        return jsonify(
            create_success_response(
                {"suggested_agents": suggested_agents},
                f"Found {len(suggested_agents)} suitable agents",
            )
        )

    except ValidationError as e:
        return create_error_response(e, 400)
    except SwarmException as e:
        logger.error(f"Error suggesting agents: {e}")
        return create_error_response(e, 500)
    except Exception as e:
        logger.error(f"Unexpected error suggesting agents: {e}")
        return create_error_response(SwarmException("Internal server error", "INTERNAL_ERROR"), 500)


@agents_bp.route("/collaborate", methods=["POST"])
def collaborate_with_agents():
    """Chat with multiple agents simultaneously using @mentions"""
    try:
        if not request.is_json:
            raise ValidationError("Request must be JSON", "INVALID_CONTENT_TYPE")

        data = request.get_json()
        if not data:
            raise ValidationError("Request body cannot be empty", "EMPTY_BODY")

        # Extract and validate required fields
        message = data.get("message")
        if not message or not message.strip():
            raise ValidationError("Message is required and cannot be empty", "MISSING_MESSAGE")

        mentioned_agents = data.get("mentioned_agents", [])
        if not mentioned_agents or not isinstance(mentioned_agents, list):
            raise ValidationError("Mentioned agents list is required", "MISSING_MENTIONED_AGENTS")

        # Optional fields
        conversation_history = data.get("conversation_history", [])
        model = data.get("model")

        # Validate mentioned agents exist
        all_agents = agent_service.list_all_agents()
        valid_agent_ids = [agent["agent_id"] for agent in all_agents]

        invalid_agents = [
            agent_id for agent_id in mentioned_agents if agent_id not in valid_agent_ids
        ]
        if invalid_agents:
            raise ValidationError(
                f"Invalid agent IDs: {', '.join(invalid_agents)}",
                "INVALID_AGENT_IDS",
                {"invalid_agents": invalid_agents, "valid_agents": valid_agent_ids},
            )

        # Chat with all mentioned agents
        responses = []
        for agent_id in mentioned_agents:
            try:
                response = agent_service.chat_with_agent(
                    agent_id=agent_id,
                    message=message,
                    conversation_history=conversation_history,
                    model=model,
                )

                agent_info = agent_service.get_agent_info(agent_id)
                responses.append(
                    {
                        "agent_id": agent_id,
                        "agent_name": agent_info["name"],
                        "response": response.content,
                        "model_used": response.model,
                        "usage": response.usage,
                    }
                )

            except Exception as e:
                logger.error(f"Error getting response from agent {agent_id}: {e}")
                responses.append(
                    {
                        "agent_id": agent_id,
                        "agent_name": agent_info.get("name", agent_id),
                        "response": f"Sorry, I encountered an error: {str(e)}",
                        "model_used": None,
                        "usage": None,
                        "error": True,
                    }
                )

        return jsonify(
            create_success_response(
                {
                    "responses": responses,
                    "message": message,
                    "mentioned_agents": mentioned_agents,
                    "total_responses": len(responses),
                },
                f"Collaboration completed with {len(responses)} agents",
            )
        )

    except ValidationError as e:
        return create_error_response(e, 400)
    except SwarmException as e:
        logger.error(f"Error in agent collaboration: {e}")
        return create_error_response(e, 500)
    except Exception as e:
        logger.error(f"Unexpected error in agent collaboration: {e}")
        return create_error_response(SwarmException("Internal server error", "INTERNAL_ERROR"), 500)


@agents_bp.route("/<agent_id>/history", methods=["GET"])
def get_agent_conversation_history(agent_id: str):
    """Get conversation history for a specific agent"""
    try:
        # Get optional limit parameter
        limit = request.args.get("limit", 20, type=int)
        if limit < 1 or limit > 100:
            raise ValidationError("Limit must be between 1 and 100", "INVALID_LIMIT")

        # Get conversation history
        history = agent_service.get_conversation_history(agent_id, limit)

        return jsonify(
            create_success_response(
                {"history": history, "agent_id": agent_id, "total": len(history)},
                f"Retrieved {len(history)} conversation entries for {agent_id}",
            )
        )

    except ValidationError as e:
        return create_error_response(e, 400)
    except AgentNotFoundError as e:
        return create_error_response(e, 404)
    except SwarmException as e:
        logger.error(f"Error getting conversation history for {agent_id}: {e}")
        return create_error_response(e, 500)
    except Exception as e:
        logger.error(f"Unexpected error getting conversation history for {agent_id}: {e}")
        return create_error_response(SwarmException("Internal server error", "INTERNAL_ERROR"), 500)


@agents_bp.route("/<agent_id>/clear-memory", methods=["DELETE"])
def clear_agent_memory_route(agent_id: str):
    """Clear memory for a specific agent"""
    try:
        # Clear agent memory
        success = agent_service.clear_agent_memory(agent_id)

        return jsonify(
            create_success_response(
                {"agent_id": agent_id, "cleared": success},
                (
                    f"Memory cleared for agent {agent_id}"
                    if success
                    else f"No memory found for agent {agent_id}"
                ),
            )
        )

    except AgentNotFoundError as e:
        return create_error_response(e, 404)
    except SwarmException as e:
        logger.error(f"Error clearing memory for {agent_id}: {e}")
        return create_error_response(e, 500)
    except Exception as e:
        logger.error(f"Unexpected error clearing memory for {agent_id}: {e}")
        return create_error_response(SwarmException("Internal server error", "INTERNAL_ERROR"), 500)
