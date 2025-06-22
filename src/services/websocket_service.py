"""
WebSocket Service for Real-Time Agent Coordination with Response Streaming
Handles real-time communication between agents and clients including live response streaming
"""

import json
import logging
import uuid
import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Callable, AsyncGenerator
from dataclasses import dataclass, asdict
from enum import Enum

from flask import Flask, request
from flask_socketio import SocketIO, emit, join_room, leave_room, disconnect
from flask_socketio import Namespace

logger = logging.getLogger(__name__)


class MessageType(Enum):
    """WebSocket message types"""

    AGENT_MESSAGE = "agent_message"
    AGENT_THINKING = "agent_thinking"
    AGENT_COLLABORATION = "agent_collaboration"
    AGENT_STATUS = "agent_status"
    USER_MESSAGE = "user_message"
    SYSTEM_MESSAGE = "system_message"
    ERROR = "error"
    HEARTBEAT = "heartbeat"
    STREAM_START = "stream_start"
    STREAM_CHUNK = "stream_chunk"
    STREAM_END = "stream_end"
    STREAM_ERROR = "stream_error"


class AgentStatus(Enum):
    """Agent status types"""

    IDLE = "idle"
    THINKING = "thinking"
    WORKING = "working"
    COLLABORATING = "collaborating"
    ERROR = "error"


@dataclass
class WebSocketMessage:
    """WebSocket message structure"""

    message_id: str
    message_type: MessageType
    timestamp: str
    sender_id: str
    sender_type: str  # 'user', 'agent', 'system'
    content: str
    metadata: Dict[str, Any]
    room_id: Optional[str] = None
    recipient_id: Optional[str] = None


@dataclass
class AgentState:
    """Agent state information"""

    agent_id: str
    agent_name: str
    status: AgentStatus
    current_task: Optional[str]
    progress: float  # 0.0 to 1.0
    last_activity: str
    connected_users: List[str]
    collaboration_room: Optional[str] = None


class SwarmWebSocketNamespace(Namespace):
    """Custom namespace for Swarm Multi-Agent System with streaming support"""

    def __init__(self, namespace: str = "/swarm", app: Flask = None):
        super().__init__(namespace)
        self.app = app  # Store Flask app reference
        self.connected_clients: Dict[str, Dict[str, Any]] = {}
        self.agent_states: Dict[str, AgentState] = {}
        self.active_rooms: Dict[str, Dict[str, Any]] = {}
        self.message_handlers: Dict[MessageType, List[Callable]] = {}
        self.streaming_sessions: Dict[str, Dict[str, Any]] = {}  # Track active streaming sessions

        # Initialize default agents
        self._initialize_agents()

    def _initialize_agents(self):
        """Initialize default agent states"""
        default_agents = [
            ("email", "Email Agent"),
            ("calendar", "Calendar Agent"),
            ("code", "Code Agent"),
            ("debug", "Debug Agent"),
            ("general", "General Agent"),
        ]

        for agent_id, agent_name in default_agents:
            self.agent_states[agent_id] = AgentState(
                agent_id=agent_id,
                agent_name=agent_name,
                status=AgentStatus.IDLE,
                current_task=None,
                progress=0.0,
                last_activity=datetime.now(timezone.utc).isoformat(),
                connected_users=[],
            )

    def on_connect(self, auth):
        """Handle client connection"""
        try:
            client_id = request.sid
            user_id = auth.get("user_id") if auth else f"anonymous_{client_id[:8]}"

            # Store client information
            self.connected_clients[client_id] = {
                "user_id": user_id,
                "connected_at": datetime.now(timezone.utc).isoformat(),
                "rooms": [],
                "agent_subscriptions": [],
            }

            logger.info(f"🔌 Client connected: {user_id} ({client_id})")

            # Send welcome message with current system state
            self._send_system_state(client_id)

            # Emit connection success
            emit(
                "connection_status",
                {
                    "status": "connected",
                    "client_id": client_id,
                    "user_id": user_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )

        except Exception as e:
            logger.error(f"❌ Connection error: {e}")
            emit("error", {"message": "Connection failed", "error": str(e)})
            disconnect()

    def on_disconnect(self):
        """Handle client disconnection"""
        try:
            client_id = request.sid

            if client_id in self.connected_clients:
                client_info = self.connected_clients[client_id]
                user_id = client_info["user_id"]

                # Clean up any active streaming sessions
                self._cleanup_streaming_sessions(client_id)

                # Leave all rooms
                for room_id in client_info["rooms"]:
                    self._leave_room_internal(client_id, room_id)

                # Remove from agent subscriptions
                for agent_id in client_info["agent_subscriptions"]:
                    if agent_id in self.agent_states:
                        agent_state = self.agent_states[agent_id]
                        if user_id in agent_state.connected_users:
                            agent_state.connected_users.remove(user_id)

                # Remove client
                del self.connected_clients[client_id]

                logger.info(f"🔌 Client disconnected: {user_id} ({client_id})")

        except Exception as e:
            logger.error(f"❌ Disconnection error: {e}")

    def on_subscribe_agent(self, data):
        """Subscribe to agent updates"""
        try:
            client_id = request.sid
            agent_id = data.get("agent_id")

            if not agent_id or agent_id not in self.agent_states:
                emit("error", {"message": f"Invalid agent ID: {agent_id}"})
                return

            if client_id not in self.connected_clients:
                emit("error", {"message": "Client not found"})
                return

            client_info = self.connected_clients[client_id]
            user_id = client_info["user_id"]

            # Add to subscriptions
            if agent_id not in client_info["agent_subscriptions"]:
                client_info["agent_subscriptions"].append(agent_id)
                self.agent_states[agent_id].connected_users.append(user_id)

            # Send current agent state
            agent_state = self.agent_states[agent_id]

            # Convert AgentState to dict with proper serialization
            state_dict = asdict(agent_state)
            state_dict["status"] = agent_state.status.value  # Convert enum to string

            emit(
                "agent_state_update",
                {
                    "agent_id": agent_id,
                    "state": state_dict,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )

            logger.info(f"📡 {user_id} subscribed to agent: {agent_id}")

        except Exception as e:
            logger.error(f"❌ Subscribe error: {e}")
            emit("error", {"message": "Subscription failed", "error": str(e)})

    def on_unsubscribe_agent(self, data):
        """Unsubscribe from agent updates"""
        try:
            client_id = request.sid
            agent_id = data.get("agent_id")

            if client_id not in self.connected_clients:
                return

            client_info = self.connected_clients[client_id]
            user_id = client_info["user_id"]

            # Remove from subscriptions
            if agent_id in client_info["agent_subscriptions"]:
                client_info["agent_subscriptions"].remove(agent_id)

                if agent_id in self.agent_states:
                    agent_state = self.agent_states[agent_id]
                    if user_id in agent_state.connected_users:
                        agent_state.connected_users.remove(user_id)

            logger.info(f"📡 {user_id} unsubscribed from agent: {agent_id}")

        except Exception as e:
            logger.error(f"❌ Unsubscribe error: {e}")

    def on_send_message(self, data):
        """Send a message to agents or collaboration room with optional streaming"""
        try:
            client_id = request.sid

            if client_id not in self.connected_clients:
                emit("error", {"message": "Client not found"})
                return

            user_id = self.connected_clients[client_id]["user_id"]

            # Create message
            message = WebSocketMessage(
                message_id=str(uuid.uuid4()),
                message_type=MessageType.USER_MESSAGE,
                timestamp=datetime.now(timezone.utc).isoformat(),
                sender_id=user_id,
                sender_type="user",
                content=data.get("content", ""),
                metadata=data.get("metadata", {}),
                room_id=data.get("room_id"),
                recipient_id=data.get("recipient_id"),
            )

            # Check if streaming is requested
            stream_enabled = data.get("stream", False)
            model = data.get("model", "openai/gpt-4o")

            # Handle different message targets
            if message.room_id:
                # Send to collaboration room
                self._send_to_room(message)
            elif message.recipient_id:
                # Send to specific agent with optional streaming
                if stream_enabled:
                    self._send_to_agent_with_streaming(message, model, client_id)
                else:
                    self._send_to_agent(message)
            else:
                # Broadcast to all subscribed agents
                self._broadcast_to_agents(message)

        except Exception as e:
            logger.error(f"❌ Send message error: {e}")
            emit("error", {"message": "Failed to send message", "error": str(e)})

    def on_join_collaboration(self, data):
        """Join a collaboration room"""
        try:
            client_id = request.sid
            room_id = data.get("room_id")

            if not room_id:
                room_id = f"collab_{uuid.uuid4().hex[:8]}"

            # Join the room
            join_room(room_id)

            # Update client info
            if client_id in self.connected_clients:
                self.connected_clients[client_id]["rooms"].append(room_id)

            # Update room info
            if room_id not in self.active_rooms:
                self.active_rooms[room_id] = {
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "participants": [],
                    "agents": [],
                    "message_count": 0,
                }

            user_id = self.connected_clients[client_id]["user_id"]
            if user_id not in self.active_rooms[room_id]["participants"]:
                self.active_rooms[room_id]["participants"].append(user_id)

            emit(
                "collaboration_joined",
                {
                    "room_id": room_id,
                    "participants": self.active_rooms[room_id]["participants"],
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )

            # Notify other participants
            emit(
                "participant_joined",
                {
                    "user_id": user_id,
                    "room_id": room_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
                room=room_id,
                include_self=False,
            )

            logger.info(f"🤝 {user_id} joined collaboration room: {room_id}")

        except Exception as e:
            logger.error(f"❌ Join collaboration error: {e}")
            emit("error", {"message": "Failed to join collaboration", "error": str(e)})

    def on_leave_collaboration(self, data):
        """Leave a collaboration room"""
        try:
            client_id = request.sid
            room_id = data.get("room_id")

            self._leave_room_internal(client_id, room_id)

        except Exception as e:
            logger.error(f"❌ Leave collaboration error: {e}")

    def on_heartbeat(self, data):
        """Handle heartbeat from client"""
        emit(
            "heartbeat_response",
            {"timestamp": datetime.now(timezone.utc).isoformat(), "status": "alive"},
        )

    def _send_to_agent_with_streaming(self, message: WebSocketMessage, model: str, client_id: str):
        """Send message to agent with streaming response"""
        try:
            agent_id = message.recipient_id
            if agent_id not in self.agent_states:
                emit("error", {"message": f"Agent {agent_id} not found"}, room=client_id)
                return

            # Update agent status
            self.update_agent_status(agent_id, AgentStatus.THINKING, "Processing user message")

            # Create streaming session
            session_id = str(uuid.uuid4())
            self.streaming_sessions[session_id] = {
                "client_id": client_id,
                "agent_id": agent_id,
                "message_id": message.message_id,
                "model": model,
                "original_message": message.content,  # Store original message for fallback
                "started_at": datetime.now(timezone.utc).isoformat(),
                "active": True,
            }

            # Start streaming response
            self._start_streaming_response(session_id, message, model)

        except Exception as e:
            logger.error(f"❌ Send to agent with streaming error: {e}")
            emit(
                "error",
                {"message": "Failed to start streaming response", "error": str(e)},
                room=client_id,
            )

    def _start_streaming_response(self, session_id: str, message: WebSocketMessage, model: str):
        """Start streaming response from agent"""
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

            # Import here to avoid circular imports
            from ..services.openrouter_service import OpenRouterService
            from flask import current_app

            # Get OpenRouter service instance
            openrouter_service = OpenRouterService()

            # Create agent context based on agent type
            agent_context = self._get_agent_context(agent_id)

            # Prepare messages for the model
            messages = [
                {"role": "system", "content": agent_context},
                {"role": "user", "content": message.content},
            ]

            # Start streaming in a separate thread with Flask app context
            import threading

            thread = threading.Thread(
                target=self._stream_agent_response,
                args=(session_id, messages, model, openrouter_service),
            )
            thread.daemon = True
            thread.start()

        except Exception as e:
            logger.error(f"❌ Start streaming response error: {e}")
            self._handle_streaming_error(session_id, str(e))

    def _stream_agent_response(
        self, session_id: str, messages: List[Dict], model: str, openrouter_service
    ):
        """Stream agent response in separate thread"""
        try:
            # Use the stored Flask app reference
            if not self.app:
                logger.error("❌ No Flask app reference available for streaming")
                self._handle_streaming_error(session_id, "No Flask app reference available")
                return

            with self.app.app_context():
                session = self.streaming_sessions.get(session_id)
                if not session or not session["active"]:
                    return

                client_id = session["client_id"]
                agent_id = session["agent_id"]

                logger.info(f"🔄 Starting streaming response for session {session_id}")

                # Stream response from OpenRouter
                full_response = ""
                chunk_count = 0
                
                try:
                    for chunk in openrouter_service.stream_chat_completion(messages, model):
                        if not session.get("active", False):
                            logger.info(f"⏹️ Streaming session {session_id} deactivated, stopping")
                            break

                        # Extract content from chunk
                        if chunk and "choices" in chunk and len(chunk["choices"]) > 0:
                            delta = chunk["choices"][0].get("delta", {})
                            content = delta.get("content", "")

                            if content:
                                chunk_count += 1
                                full_response += content
                                
                                # Emit chunk to client
                                self.socketio.emit(
                                    "response_stream_chunk",
                                    {
                                        "session_id": session_id,
                                        "chunk": content,
                                        "timestamp": datetime.now(timezone.utc).isoformat(),
                                    },
                                    room=client_id,
                                    namespace="/swarm",
                                )
                                
                                logger.debug(f"📤 Sent chunk {chunk_count} to client {client_id}")

                    logger.info(f"✅ Streaming completed for session {session_id}. Total chunks: {chunk_count}, Response length: {len(full_response)}")
                    
                    # If we got a response, end streaming normally
                    if full_response.strip():
                        self._end_streaming_response(session_id)
                    else:
                        logger.warning(f"⚠️ Empty response received for session {session_id}")
                        self._handle_streaming_error(session_id, "Empty response from OpenRouter API")
                        
                except Exception as streaming_error:
                    logger.error(f"❌ OpenRouter streaming error for session {session_id}: {streaming_error}")
                    self._handle_streaming_error(session_id, f"OpenRouter API error: {str(streaming_error)}")

        except Exception as e:
            logger.error(f"❌ Stream agent response error for session {session_id}: {e}")
            self._handle_streaming_error(session_id, f"Streaming thread error: {str(e)}")

    def _end_streaming_response(self, session_id: str):
        """End streaming response"""
        try:
            session = self.streaming_sessions.get(session_id)
            if not session:
                return

            client_id = session["client_id"]
            agent_id = session["agent_id"]

            # Mark session as inactive
            session["active"] = False
            session["ended_at"] = datetime.now(timezone.utc).isoformat()

            # Emit stream end
            self.socketio.emit(
                "response_stream_end",
                {
                    "session_id": session_id,
                    "agent_id": agent_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
                room=client_id,
                namespace="/swarm",
            )

            # Update agent status back to idle
            self.update_agent_status(agent_id, AgentStatus.IDLE)

            # Clean up session after a delay
            import threading

            def cleanup():
                import time

                time.sleep(30)  # Keep session for 30 seconds for debugging
                if session_id in self.streaming_sessions:
                    del self.streaming_sessions[session_id]

            thread = threading.Thread(target=cleanup)
            thread.daemon = True
            thread.start()

        except Exception as e:
            logger.error(f"❌ End streaming response error: {e}")

    def _handle_streaming_error(self, session_id: str, error_message: str):
        """Handle streaming error with fallback to non-streaming response"""
        try:
            session = self.streaming_sessions.get(session_id)
            if not session:
                return

            client_id = session["client_id"]
            agent_id = session["agent_id"]

            # Mark session as inactive
            session["active"] = False
            session["error"] = error_message
            session["ended_at"] = datetime.now(timezone.utc).isoformat()

            logger.error(f"❌ Streaming error for session {session_id}: {error_message}")

            # Try fallback to non-streaming response
            try:
                logger.info(f"🔄 Attempting fallback non-streaming response for session {session_id}")
                
                # Get the original message from session metadata
                original_message = session.get("original_message", "Hello")
                
                # Import here to avoid circular imports
                from ..services.openrouter_service import OpenRouterService
                
                # Get OpenRouter service instance
                openrouter_service = OpenRouterService()
                
                # Create agent context
                agent_context = self._get_agent_context(agent_id)
                
                # Prepare messages for non-streaming
                messages = [
                    {"role": "system", "content": agent_context},
                    {"role": "user", "content": original_message},
                ]
                
                # Get non-streaming response
                response = openrouter_service.chat_completion_with_messages(messages, session.get("model", "openai/gpt-4o"), stream=False)
                
                if response and response.content:
                    # Send the complete response as a single message
                    self.socketio.emit(
                        "agent_message",
                        {
                            "message_id": str(uuid.uuid4()),
                            "message_type": "agent_message",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "sender_id": agent_id,
                            "sender_type": "agent",
                            "content": response.content,
                            "metadata": {"fallback_response": True, "original_error": error_message},
                        },
                        room=client_id,
                        namespace="/swarm",
                    )
                    
                    logger.info(f"✅ Fallback response sent successfully for session {session_id}")
                else:
                    raise Exception("Empty fallback response")
                    
            except Exception as fallback_error:
                logger.error(f"❌ Fallback response also failed for session {session_id}: {fallback_error}")
                
                # Send error message to client
                self.socketio.emit(
                    "agent_message",
                    {
                        "message_id": str(uuid.uuid4()),
                        "message_type": "agent_message",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "sender_id": agent_id,
                        "sender_type": "agent",
                        "content": "Sorry, I encountered an error while processing your request. Please try again.",
                        "metadata": {"error": True, "error_message": error_message},
                    },
                    room=client_id,
                    namespace="/swarm",
                )

            # Update agent status back to idle
            self.update_agent_status(agent_id, AgentStatus.IDLE)

        except Exception as e:
            logger.error(f"❌ Handle streaming error failed: {e}")

    def _cleanup_streaming_sessions(self, client_id: str):
        """Clean up streaming sessions for disconnected client"""
        try:
            sessions_to_remove = []
            for session_id, session in self.streaming_sessions.items():
                if session["client_id"] == client_id:
                    session["active"] = False
                    sessions_to_remove.append(session_id)

            for session_id in sessions_to_remove:
                del self.streaming_sessions[session_id]

        except Exception as e:
            logger.error(f"❌ Cleanup streaming sessions error: {e}")

    def _get_agent_context(self, agent_id: str) -> str:
        """Get agent-specific context for responses"""
        agent_contexts = {
            "email": """You are an Email Agent specialized in professional email composition, management, and workflow automation. 
            You help users write effective emails, manage their inbox, set up email automation, and handle email-related tasks. 
            Be professional, concise, and helpful in your responses.""",
            "calendar": """You are a Calendar Agent specialized in scheduling, time management, and calendar operations.
            You help users schedule meetings, manage their calendar, find optimal meeting times, and organize their schedule.
            Be efficient and considerate of time zones and scheduling conflicts.""",
            "code": """You are a Code Agent specialized in software development, programming, and technical implementation.
            You help users write code, debug issues, review code quality, and implement technical solutions.
            Provide clear, well-commented code examples and explain your reasoning.""",
            "debug": """You are a Debug Agent specialized in troubleshooting, system diagnostics, and problem-solving.
            You help users identify issues, analyze error logs, debug problems, and find solutions.
            Be systematic in your approach and provide step-by-step debugging guidance.""",
            "general": """You are a General Agent capable of handling a wide variety of tasks and coordination.
            You help users with general questions, task coordination, and can collaborate with other specialized agents.
            Be helpful, versatile, and ready to coordinate with other agents when needed.""",
        }

        return agent_contexts.get(agent_id, agent_contexts["general"])

    def _send_system_state(self, client_id: str):
        """Send current system state to client"""
        try:
            # Convert agent states to serializable format
            serializable_agents = {}
            for agent_id, state in self.agent_states.items():
                state_dict = asdict(state)
                state_dict["status"] = state.status.value  # Convert enum to string
                serializable_agents[agent_id] = state_dict

            system_state = {
                "agents": serializable_agents,
                "active_rooms": self.active_rooms,
                "connected_clients": len(self.connected_clients),
                "streaming_sessions": len(self.streaming_sessions),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            emit("system_state", system_state, room=client_id)

        except Exception as e:
            logger.error(f"❌ Send system state error: {e}")

    def _leave_room_internal(self, client_id: str, room_id: str):
        """Internal method to leave a room"""
        try:
            leave_room(room_id)

            if client_id in self.connected_clients:
                client_info = self.connected_clients[client_id]
                user_id = client_info["user_id"]

                if room_id in client_info["rooms"]:
                    client_info["rooms"].remove(room_id)

                # Update room info
                if room_id in self.active_rooms:
                    room_info = self.active_rooms[room_id]
                    if user_id in room_info["participants"]:
                        room_info["participants"].remove(user_id)

                    # Remove room if empty
                    if not room_info["participants"]:
                        del self.active_rooms[room_id]
                    else:
                        # Notify other participants
                        emit(
                            "participant_left",
                            {
                                "user_id": user_id,
                                "room_id": room_id,
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                            },
                            room=room_id,
                        )

                emit(
                    "collaboration_left",
                    {"room_id": room_id, "timestamp": datetime.now(timezone.utc).isoformat()},
                    room=client_id,
                )

                logger.info(f"🤝 {user_id} left collaboration room: {room_id}")

        except Exception as e:
            logger.error(f"❌ Leave room error: {e}")

    def _send_to_room(self, message: WebSocketMessage):
        """Send message to collaboration room"""
        try:
            emit("message_received", asdict(message), room=message.room_id)

            # Update room message count
            if message.room_id in self.active_rooms:
                self.active_rooms[message.room_id]["message_count"] += 1

        except Exception as e:
            logger.error(f"❌ Send to room error: {e}")

    def _send_to_agent(self, message: WebSocketMessage):
        """Send message to specific agent (non-streaming)"""
        try:
            agent_id = message.recipient_id
            if agent_id in self.agent_states:
                # Update agent status
                self.update_agent_status(agent_id, AgentStatus.THINKING, "Processing user message")

                # Emit to agent subscribers
                emit("agent_message_received", asdict(message), room=f"agent_{agent_id}")

        except Exception as e:
            logger.error(f"❌ Send to agent error: {e}")

    def _broadcast_to_agents(self, message: WebSocketMessage):
        """Broadcast message to all agents"""
        try:
            emit("broadcast_message", asdict(message), broadcast=True)

        except Exception as e:
            logger.error(f"❌ Broadcast error: {e}")

    def update_agent_status(
        self,
        agent_id: str,
        status: AgentStatus,
        current_task: Optional[str] = None,
        progress: float = 0.0,
    ):
        """Update agent status and notify subscribers"""
        try:
            if agent_id not in self.agent_states:
                return

            agent_state = self.agent_states[agent_id]
            agent_state.status = status
            agent_state.last_activity = datetime.now(timezone.utc).isoformat()

            if current_task is not None:
                agent_state.current_task = current_task

            agent_state.progress = progress

            # Notify subscribers
            emit(
                "agent_status_update",
                {
                    "agent_id": agent_id,
                    "status": status.value,
                    "current_task": current_task,
                    "progress": progress,
                    "timestamp": agent_state.last_activity,
                },
                broadcast=True,
            )

        except Exception as e:
            logger.error(f"❌ Update agent status error: {e}")

    def send_agent_message(
        self,
        agent_id: str,
        content: str,
        message_type: MessageType = MessageType.AGENT_MESSAGE,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """Send message from agent to clients"""
        try:
            message = WebSocketMessage(
                message_id=str(uuid.uuid4()),
                message_type=message_type,
                timestamp=datetime.now(timezone.utc).isoformat(),
                sender_id=agent_id,
                sender_type="agent",
                content=content,
                metadata=metadata or {},
            )

            emit("agent_message", asdict(message), broadcast=True)

        except Exception as e:
            logger.error(f"❌ Send agent message error: {e}")


class WebSocketService:
    """WebSocket service for real-time agent coordination with streaming support"""

    def __init__(self, app: Flask):
        self.app = app
        self.socketio = SocketIO(
            app,
            cors_allowed_origins="*",
            async_mode='threading',
            logger=False,
            engineio_logger=False,
            ping_timeout=60,
            ping_interval=25
        )

        # Register namespace with app reference
        self.namespace = SwarmWebSocketNamespace("/swarm", app)
        self.namespace.socketio = self.socketio  # Add socketio reference
        self.socketio.on_namespace(self.namespace)

        logger.info("🔌 WebSocket service with streaming support initialized")

    def get_agent_states(self) -> Dict[str, AgentState]:
        """Get current agent states"""
        return self.namespace.agent_states

    def update_agent_status(
        self,
        agent_id: str,
        status: AgentStatus,
        current_task: Optional[str] = None,
        progress: float = 0.0,
    ):
        """Update agent status"""
        self.namespace.update_agent_status(agent_id, status, current_task, progress)

    def send_agent_message(
        self,
        agent_id: str,
        content: str,
        message_type: MessageType = MessageType.AGENT_MESSAGE,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """Send message from agent"""
        self.namespace.send_agent_message(agent_id, content, message_type, metadata)

    def get_connected_clients_count(self) -> int:
        """Get number of connected clients"""
        return len(self.namespace.connected_clients)

    def get_active_rooms(self) -> Dict[str, Dict[str, Any]]:
        """Get active collaboration rooms"""
        return self.namespace.active_rooms

    def get_streaming_sessions(self) -> Dict[str, Dict[str, Any]]:
        """Get active streaming sessions"""
        return self.namespace.streaming_sessions
