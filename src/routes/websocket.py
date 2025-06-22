"""
WebSocket Routes - Real-time communication endpoints
"""

import logging
from flask import Blueprint, request # jsonify removed
from src.services.websocket_service import WebSocketService, AgentStatus, MessageType # Added MessageType
from src.utils.response_helpers import success_response # error_response removed
from src.exceptions import SwarmException, ValidationError # Import exceptions

logger = logging.getLogger(__name__)

websocket_bp = Blueprint("websocket", __name__)

# Global WebSocket service instance (will be initialized in main.py)
websocket_service: WebSocketService = None


def init_websocket_routes(ws_service: WebSocketService):
    """Initialize WebSocket routes with service instance"""
    global websocket_service
    websocket_service = ws_service


@websocket_bp.route("/health", methods=["GET"])
def websocket_health():
    """WebSocket service health check"""
    try:
        if not websocket_service:
            raise SwarmException("WebSocket service not initialized", error_code="WEBSOCKET_SERVICE_UNAVAILABLE", status_code=503)

        connected_clients = websocket_service.get_connected_clients_count()
        active_rooms = len(websocket_service.get_active_rooms())
        agent_states = websocket_service.get_agent_states()

        health_data = {
            "status": "healthy",
            "connected_clients": connected_clients,
            "active_rooms": active_rooms,
            "agents": {
                agent_id: {
                    "status": state.status.value,
                    "connected_users": len(state.connected_users),
                    "last_activity": state.last_activity,
                }
                for agent_id, state in agent_states.items()
            },
        }

        return success_response("WebSocket service is healthy", health_data)

    except Exception as e:
        logger.error(f"WebSocket health check failed: {e}")
        raise SwarmException("WebSocket health check failed", error_code="WEBSOCKET_HEALTH_CHECK_FAILED", details={"original_error": str(e)}, status_code=500)


@websocket_bp.route("/agents/status", methods=["GET"])
def get_agent_statuses():
    """Get current status of all agents"""
    try:
        if not websocket_service:
            raise SwarmException("WebSocket service not initialized", error_code="WEBSOCKET_SERVICE_UNAVAILABLE", status_code=503)

        agent_states = websocket_service.get_agent_states()

        statuses = {}
        for agent_id, state in agent_states.items():
            statuses[agent_id] = {
                "agent_name": state.agent_name,
                "status": state.status.value,
                "current_task": state.current_task,
                "progress": state.progress,
                "last_activity": state.last_activity,
                "connected_users": len(state.connected_users),
                "collaboration_room": state.collaboration_room,
            }

        return success_response("Agent statuses retrieved", {"agents": statuses})

    except Exception as e:
        logger.error(f"Failed to get agent statuses: {e}")
        raise SwarmException("Failed to get agent statuses", error_code="GET_AGENT_STATUSES_FAILED", details={"original_error": str(e)}, status_code=500)


@websocket_bp.route("/agents/<agent_id>/status", methods=["PUT"])
def update_agent_status(agent_id: str):
    """Update agent status (for internal use by agent services)"""
    try:
        if not websocket_service:
            raise SwarmException("WebSocket service not initialized", error_code="WEBSOCKET_SERVICE_UNAVAILABLE", status_code=503)

        data = request.get_json()
        if not data:
            raise ValidationError("Request body is required", error_code="MISSING_BODY")

        # Validate status
        status_str = data.get("status")
        if not status_str:
            raise ValidationError("Status is required", error_code="MISSING_STATUS", details={"field":"status"})

        try:
            status = AgentStatus(status_str)
        except ValueError:
            valid_statuses = [s.value for s in AgentStatus]
            raise ValidationError(f"Invalid status. Valid options: {valid_statuses}", error_code="INVALID_AGENT_STATUS", details={"valid_options": valid_statuses})

        current_task = data.get("current_task")
        progress = data.get("progress", 0.0)

        # Validate progress
        if not isinstance(progress, (int, float)) or not (0 <= progress <= 1):
            raise ValidationError("Progress must be a number between 0 and 1", error_code="INVALID_PROGRESS", details={"field": "progress"})

        # Update agent status
        websocket_service.update_agent_status(agent_id, status, current_task, progress)

        return success_response(
            f"Agent {agent_id} status updated",
            {
                "agent_id": agent_id,
                "status": status.value,
                "current_task": current_task,
                "progress": progress,
            },
        )

    except ValidationError:
        raise
    except Exception as e:
        logger.error(f"Failed to update agent status: {e}")
        raise SwarmException("Failed to update agent status", error_code="UPDATE_AGENT_STATUS_FAILED", details={"original_error": str(e)}, status_code=500)


@websocket_bp.route("/agents/<agent_id>/message", methods=["POST"])
def send_agent_message(agent_id: str):
    """Send message from agent to connected clients"""
    try:
        if not websocket_service:
            raise SwarmException("WebSocket service not initialized", error_code="WEBSOCKET_SERVICE_UNAVAILABLE", status_code=503)

        data = request.get_json()
        if not data:
            raise ValidationError("Request body is required", error_code="MISSING_BODY")

        content = data.get("content")
        if not content:
            raise ValidationError("Message content is required", error_code="MISSING_MESSAGE_CONTENT", details={"field": "content"})

        # Validate message type
        message_type_str = data.get("message_type", "agent_message")
        try:
            message_type = MessageType(message_type_str) # Assumes MessageType is imported and is an Enum
        except ValueError:
            # valid_types = [t.value for t in MessageType] # This would fail if MessageType is not an Enum
            raise ValidationError(f"Invalid message type: {message_type_str}", error_code="INVALID_MESSAGE_TYPE")

        metadata = data.get("metadata", {})

        # Send message
        websocket_service.send_agent_message(agent_id, content, message_type, metadata)

        return success_response(
            f"Message sent from agent {agent_id}",
            {
                "agent_id": agent_id,
                "content": content,
                "message_type": message_type.value,
                "metadata": metadata,
            },
        )

    except ValidationError:
        raise
    except Exception as e:
        logger.error(f"Failed to send agent message: {e}")
        raise SwarmException("Failed to send agent message", error_code="SEND_AGENT_MESSAGE_FAILED", details={"original_error": str(e)}, status_code=500)


@websocket_bp.route("/rooms", methods=["GET"])
def get_active_rooms():
    """Get list of active collaboration rooms"""
    try:
        if not websocket_service:
            raise SwarmException("WebSocket service not initialized", error_code="WEBSOCKET_SERVICE_UNAVAILABLE", status_code=503)

        active_rooms = websocket_service.get_active_rooms()

        rooms_data = {}
        for room_id, room_info in active_rooms.items():
            rooms_data[room_id] = {
                "created_at": room_info["created_at"],
                "participant_count": len(room_info["participants"]),
                "participants": room_info["participants"],
                "agent_count": len(room_info.get("agents", [])),
                "agents": room_info.get("agents", []),
                "message_count": room_info.get("message_count", 0),
            }

        return success_response(
            "Active rooms retrieved", {"room_count": len(rooms_data), "rooms": rooms_data}
        )

    except Exception as e:
        logger.error(f"Failed to get active rooms: {e}")
        raise SwarmException("Failed to get active rooms", error_code="GET_ACTIVE_ROOMS_FAILED", details={"original_error": str(e)}, status_code=500)


@websocket_bp.route("/stats", methods=["GET"])
def get_websocket_stats():
    """Get WebSocket service statistics"""
    try:
        if not websocket_service:
            raise SwarmException("WebSocket service not initialized", error_code="WEBSOCKET_SERVICE_UNAVAILABLE", status_code=503)

        connected_clients = websocket_service.get_connected_clients_count()
        active_rooms = websocket_service.get_active_rooms()
        agent_states = websocket_service.get_agent_states()

        # Calculate statistics
        total_participants = sum(len(room["participants"]) for room in active_rooms.values())

        agent_status_counts = {}
        for state in agent_states.values():
            status = state.status.value
            agent_status_counts[status] = agent_status_counts.get(status, 0) + 1

        stats = {
            "connected_clients": connected_clients,
            "active_rooms": len(active_rooms),
            "total_room_participants": total_participants,
            "total_agents": len(agent_states),
            "agent_status_distribution": agent_status_counts,
            "average_participants_per_room": (
                total_participants / len(active_rooms) if active_rooms else 0
            ),
        }

        return success_response("WebSocket statistics retrieved", stats)

    except Exception as e:
        logger.error(f"Failed to get WebSocket stats: {e}")
        raise SwarmException("Failed to get WebSocket stats", error_code="GET_WEBSOCKET_STATS_FAILED", details={"original_error": str(e)}, status_code=500)


@websocket_bp.route("/test", methods=["POST"])
def test_websocket_message():
    """Test WebSocket message sending (for development/testing)"""
    try:
        if not websocket_service:
            raise SwarmException("WebSocket service not initialized", error_code="WEBSOCKET_SERVICE_UNAVAILABLE", status_code=503)

        data = request.get_json()
        if not data:
            raise ValidationError("Request body is required", error_code="MISSING_BODY")

        agent_id = data.get("agent_id", "test")
        content = data.get("content", "Test message from WebSocket API")

        message_type_str = data.get("message_type", "system_message")
        try:
            message_type = MessageType(message_type_str) # Assumes MessageType is imported and is an Enum
        except ValueError:
            # valid_types = [t.value for t in MessageType] # This would fail if MessageType is not an Enum
            raise ValidationError(f"Invalid message type for test: {message_type_str}", error_code="INVALID_MESSAGE_TYPE_TEST")

        websocket_service.send_agent_message(agent_id, content, message_type)

        return success_response(
            "Test message sent",
            {"agent_id": agent_id, "content": content, "message_type": message_type.value},
        )

    except ValidationError:
        raise
    except Exception as e:
        logger.error(f"Failed to send test message: {e}")
        raise SwarmException("Failed to send test message", error_code="WEBSOCKET_TEST_SEND_FAILED", details={"original_error": str(e)}, status_code=500)
