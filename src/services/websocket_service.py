"""
WebSocket Service for Real-Time Agent Coordination with Enhanced MCP Integration
"""

import json
import logging
import threading
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from flask import current_app, request
from flask_socketio import Namespace, emit, join_room, leave_room

from src.exceptions import ServiceError, SwarmException
from src.services.base_service import BaseService

logger = logging.getLogger(__name__)


class AgentStatus(Enum):
    """Agent status enumeration"""
    IDLE = "idle"
    THINKING = "thinking"
    PROCESSING = "processing"
    RESPONDING = "responding"
    ERROR = "error"


class WebSocketMessage:
    """WebSocket message structure"""
    def __init__(self, message_id: str, message_type: str, content: str, 
                 sender_id: str, recipient_id: str = None, room_id: str = None,
                 metadata: Dict[str, Any] = None):
        self.message_id = message_id
        self.message_type = message_type
        self.content = content
        self.sender_id = sender_id
        self.recipient_id = recipient_id
        self.room_id = room_id
        self.metadata = metadata or {}
        self.timestamp = datetime.now(timezone.utc)


class WebSocketService(BaseService):
    """Enhanced WebSocket service with proper MCP filesystem integration"""

    def __init__(self, app, mcp_filesystem_service=None):
        super().__init__("WebSocket")
        self.app = app
        self.mcp_filesystem_service = mcp_filesystem_service
        self.connected_clients = {}
        self.agent_states = {}
        self.active_rooms = {}
        self.streaming_sessions = {}
        
        # Verify MCP filesystem service
        if self.mcp_filesystem_service:
            health = self.mcp_filesystem_service.health_check()
            if health.get("status") == "healthy":
                logger.info("✅ MCP Filesystem service connected and healthy")
            else:
                logger.error(f"❌ MCP Filesystem service unhealthy: {health}")
        else:
            logger.warning("⚠️ MCP Filesystem service not provided")

    def _start_streaming_response(self, session_id: str, message: WebSocketMessage, model: str):
        """Start streaming response from agent with proper Flask context"""
        try:
            session = self.streaming_sessions.get(session_id)
            if not session or not session["active"]:
                return

            client_id = session["client_id"]
            agent_id = session["agent_id"]

            # Emit stream start
            emit(
                "response_stream_start",
                {
                    "session_id": session_id,
                    "agent_id": agent_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
                room=client_id,
            )

            # CRITICAL FIX: Use Flask app context for threading
            with self.app.app_context():
                # Import here to avoid circular imports
                from ..services.openrouter_service import OpenRouterService
                from ..services.agent_service import AgentService
                from ..services.supermemory_service import SupermemoryService

                # Get services with proper error handling
                try:
                    openrouter_service = OpenRouterService()
                    supermemory_service = SupermemoryService() if hasattr(current_app, 'config_manager') else None
                    
                    # CRITICAL FIX: Ensure MCP filesystem service is passed correctly
                    if not self.mcp_filesystem_service:
                        logger.error("❌ MCP Filesystem service not available for agent")
                        # Try to get from app context as fallback
                        self.mcp_filesystem_service = getattr(current_app, 'mcp_filesystem_service', None)
                    
                    # Create agent service with MCP filesystem
                    agent_service = AgentService(
                        openrouter_service=openrouter_service,
                        supermemory_service=supermemory_service,
                        mcp_filesystem_service=self.mcp_filesystem_service
                    )

                    # Log MCP filesystem status
                    if agent_service.mcp_filesystem:
                        logger.info(f"✅ Agent {agent_id} has MCP filesystem access")
                    else:
                        logger.error(f"❌ Agent {agent_id} missing MCP filesystem access")

                    # Use agent service for proper MCP filesystem integration
                    response = agent_service.chat_with_agent(
                        agent_id=agent_id,
                        message=message.content,
                        model=model
                    )
                    
                    # Stream the response content
                    if response and response.content:
                        # Split response into chunks for streaming
                        chunk_size = 50
                        content = response.content
                        
                        for i in range(0, len(content), chunk_size):
                            if not session.get("active", False):
                                break
                                
                            chunk = content[i:i + chunk_size]
                            
                            emit(
                                "response_stream_chunk",
                                {
                                    "session_id": session_id,
                                    "agent_id": agent_id,
                                    "chunk": chunk,
                                    "chunk_index": i // chunk_size,
                                    "is_final": i + chunk_size >= len(content),
                                    "timestamp": datetime.now(timezone.utc).isoformat(),
                                },
                                room=client_id,
                                namespace="/swarm",
                            )
                            
                            # Small delay for streaming effect
                            import time
                            time.sleep(0.1)
                    
                    # Emit stream complete
                    emit(
                        "response_stream_complete",
                        {
                            "session_id": session_id,
                            "agent_id": agent_id,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        },
                        room=client_id,
                        namespace="/swarm",
                    )
                    
                except Exception as service_error:
                    logger.error(f"❌ Service error in streaming: {service_error}")
                    
                    # Send fallback error response
                    emit(
                        "response_stream_chunk",
                        {
                            "session_id": session_id,
                            "agent_id": agent_id,
                            "chunk": f"I apologize, but I encountered a technical issue: {str(service_error)}. Please try again.",
                            "chunk_index": 0,
                            "is_final": True,
                            "error": True,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        },
                        room=client_id,
                        namespace="/swarm",
                    )

        except Exception as e:
            logger.error(f"❌ Critical error in streaming response: {e}")
            
            # Emit error to client
            emit(
                "response_stream_error",
                {
                    "session_id": session_id,
                    "error": str(e),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
                room=client_id,
                namespace="/swarm",
            )
        finally:
            # Clean up session
            if session_id in self.streaming_sessions:
                self.streaming_sessions[session_id]["active"] = False

    def get_mcp_status(self) -> Dict[str, Any]:
        """Get MCP filesystem service status"""
        if not self.mcp_filesystem_service:
            return {
                "status": "disconnected",
                "error": "MCP filesystem service not initialized"
            }
        
        try:
            health = self.mcp_filesystem_service.health_check()
            stats = self.mcp_filesystem_service.get_workspace_stats()
            
            return {
                "status": health.get("status", "unknown"),
                "health": health,
                "stats": stats,
                "service_name": "mcp_filesystem"
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e)
            }


class SwarmWebSocketNamespace(Namespace):
    """Enhanced WebSocket namespace with MCP status tracking"""

    def __init__(self, websocket_service: WebSocketService):
        super().__init__("/swarm")
        self.websocket_service = websocket_service
        self.connected_clients = {}
        self.agent_states = {
            "email_agent": {"status": AgentStatus.IDLE, "connected_users": []},
            "calendar_agent": {"status": AgentStatus.IDLE, "connected_users": []},
            "code_agent": {"status": AgentStatus.IDLE, "connected_users": []},
            "debug_agent": {"status": AgentStatus.IDLE, "connected_users": []},
            "general_agent": {"status": AgentStatus.IDLE, "connected_users": []},
        }

    def on_connect(self):
        """Handle client connection with MCP status"""
        client_id = request.sid
        user_id = request.args.get("user_id", f"user_{client_id[:8]}")
        
        self.connected_clients[client_id] = {
            "user_id": user_id,
            "connected_at": datetime.now(timezone.utc).isoformat(),
            "agent_subscriptions": [],
        }
        
        # Get MCP status
        mcp_status = self.websocket_service.get_mcp_status()
        
        emit("connection_established", {
            "client_id": client_id,
            "user_id": user_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "mcp_status": mcp_status,
        })
        
        logger.info(f"✅ Client connected: {user_id} (MCP: {mcp_status.get('status', 'unknown')})")

    def on_send_message(self, data):
        """Enhanced message handling with MCP filesystem support"""
        try:
            client_id = request.sid
            
            if client_id not in self.connected_clients:
                emit("error", {"message": "Client not found"})
                return

            user_id = self.connected_clients[client_id]["user_id"]
            
            # Create message
            message = WebSocketMessage(
                message_id=str(uuid.uuid4()),
                message_type="USER_MESSAGE",
                content=data.get("content", ""),
                sender_id=user_id,
                recipient_id=data.get("recipient_id"),
                room_id=data.get("room_id"),
                metadata=data.get("metadata", {}),
            )
            
            # Get model
            model = data.get("model", "openai/gpt-4o")
            
            # Handle different message targets
            if message.room_id:
                # Send to collaboration room
                self._send_to_room(message)
            elif message.recipient_id:
                # Send to specific agent with optional streaming
                if data.get("stream_enabled"):
                    self._send_to_agent_with_streaming(message, model, client_id)
                else:
                    self._send_to_agent(message)
            else:
                # Broadcast to all subscribed agents
                self._broadcast_to_agents(message)

        except Exception as e:
            logger.error(f"❌ Send message error: {e}")
            emit("error", {"message": "Failed to send message", "error": str(e)})

    def _send_to_agent_with_streaming(self, message: WebSocketMessage, model: str, client_id: str):
        """Send message to agent with streaming response and MCP support"""
        try:
            agent_id = message.recipient_id
            if agent_id not in self.agent_states:
                emit("error", {"message": f"Agent {agent_id} not found"}, room=client_id)
                return

            # Update agent status
            self.update_agent_status(agent_id, AgentStatus.THINKING, "Processing user message")

            # Create streaming session
            session_id = str(uuid.uuid4())
            self.websocket_service.streaming_sessions[session_id] = {
                "client_id": client_id,
                "agent_id": agent_id,
                "message_id": message.message_id,
                "model": model,
                "original_message": message.content,  # Store original message for fallback
                "started_at": datetime.now(timezone.utc).isoformat(),
                "active": True,
            }

            # Start streaming response in background thread with Flask context
            thread = threading.Thread(
                target=self.websocket_service._start_streaming_response,
                args=(session_id, message, model)
            )
            thread.daemon = True
            thread.start()

        except Exception as e:
            logger.error(f"❌ Send to agent with streaming error: {e}")
            emit("error", {"message": "Failed to send message", "error": str(e)})

    def update_agent_status(self, agent_id: str, status: AgentStatus, message: str = ""):
        """Update agent status and broadcast to connected clients"""
        if agent_id in self.agent_states:
            self.agent_states[agent_id]["status"] = status
            
            # Include MCP status for agents
            mcp_status = self.websocket_service.get_mcp_status()
            
            emit("agent_status_update", {
                "agent_id": agent_id,
                "status": status.value,
                "message": message,
                "mcp_status": mcp_status.get("status", "unknown"),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }, broadcast=True)

    def on_get_mcp_status(self):
        """Handle MCP status request"""
        try:
            status = self.websocket_service.get_mcp_status()
            emit("mcp_status_response", status)
        except Exception as e:
            emit("mcp_status_response", {
                "status": "error",
                "error": str(e)
            })
