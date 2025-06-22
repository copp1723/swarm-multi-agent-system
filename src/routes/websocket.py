"""
WebSocket Routes - Real-time communication endpoints
"""

import logging
from flask import Blueprint, jsonify, request
from src.services.websocket_service import WebSocketService, AgentStatus, MessageType
from src.utils.response_helpers import success_response, error_response

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
            return error_response("WebSocket service not initialized", 503)

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
        return error_response("WebSocket health check failed", 500, {"error": str(e)})


@websocket_bp.route("/agents/status", methods=["GET"])
def get_agent_statuses():
    """Get current status of all agents"""
    try:
        if not websocket_service:
            return error_response("WebSocket service not initialized", 503)

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
        return error_response("Failed to get agent statuses", 500, {"error": str(e)})


@websocket_bp.route("/agents/<agent_id>/status", methods=["PUT"])
def update_agent_status(agent_id: str):
    """Update agent status (for internal use by agent services)"""
    try:
        if not websocket_service:
            return error_response("WebSocket service not initialized", 503)

        data = request.get_json()
        if not data:
            return error_response("Request body required", 400)

        # Validate status
        status_str = data.get("status")
        if not status_str:
            return error_response("Status is required", 400)

        try:
            status = AgentStatus(status_str)
        except ValueError:
            valid_statuses = [s.value for s in AgentStatus]
            return error_response(f"Invalid status. Valid options: {valid_statuses}", 400)

        current_task = data.get("current_task")
        progress = data.get("progress", 0.0)

        # Validate progress
        if not isinstance(progress, (int, float)) or progress < 0 or progress > 1:
            return error_response("Progress must be a number between 0 and 1", 400)

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

    except Exception as e:
        logger.error(f"Failed to update agent status: {e}")
        return error_response("Failed to update agent status", 500, {"error": str(e)})


@websocket_bp.route("/agents/<agent_id>/message", methods=["POST"])
def send_agent_message(agent_id: str):
    """Send message from agent to connected clients"""
    try:
        if not websocket_service:
            return error_response("WebSocket service not initialized", 503)

        data = request.get_json()
        if not data:
            return error_response("Request body required", 400)

        content = data.get("content")
        if not content:
            return error_response("Message content is required", 400)

        # Validate message type
        message_type_str = data.get("message_type", "agent_message")
        try:
            message_type = MessageType(message_type_str)
        except ValueError:
            valid_types = [t.value for t in MessageType]
            return error_response(f"Invalid message type. Valid options: {valid_types}", 400)

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

    except Exception as e:
        logger.error(f"Failed to send agent message: {e}")
        return error_response("Failed to send agent message", 500, {"error": str(e)})


@websocket_bp.route("/rooms", methods=["GET"])
def get_active_rooms():
    """Get list of active collaboration rooms"""
    try:
        if not websocket_service:
            return error_response("WebSocket service not initialized", 503)

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
        return error_response("Failed to get active rooms", 500, {"error": str(e)})


@websocket_bp.route("/stats", methods=["GET"])
def get_websocket_stats():
    """Get WebSocket service statistics"""
    try:
        if not websocket_service:
            return error_response("WebSocket service not initialized", 503)

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
        return error_response("Failed to get WebSocket stats", 500, {"error": str(e)})


@websocket_bp.route("/test", methods=["POST"])
def test_websocket_message():
    """Test WebSocket message sending (for development/testing)"""
    try:
        if not websocket_service:
            return error_response("WebSocket service not initialized", 503)

        data = request.get_json()
        if not data:
            return error_response("Request body required", 400)

        agent_id = data.get("agent_id", "test")
        content = data.get("content", "Test message from WebSocket API")
        message_type = MessageType(data.get("message_type", "system_message"))

        websocket_service.send_agent_message(agent_id, content, message_type)

        return success_response(
            "Test message sent",
            {"agent_id": agent_id, "content": content, "message_type": message_type.value},
        )

    except Exception as e:
        logger.error(f"Failed to send test message: {e}")
        return error_response("Failed to send test message", 500, {"error": str(e)})
