"""
WebSocket Service for Real-Time Agent Coordination
Handles real-time communication between agents and clients
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Callable
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
    """Custom namespace for Swarm Multi-Agent System"""
    
    def __init__(self, namespace: str = '/swarm'):
        super().__init__(namespace)
        self.connected_clients: Dict[str, Dict[str, Any]] = {}
        self.agent_states: Dict[str, AgentState] = {}
        self.active_rooms: Dict[str, Dict[str, Any]] = {}
        self.message_handlers: Dict[MessageType, List[Callable]] = {}
        
        # Initialize default agents
        self._initialize_agents()
    
    def _initialize_agents(self):
        """Initialize default agent states"""
        default_agents = [
            ("email", "Email Agent"),
            ("calendar", "Calendar Agent"),
            ("code", "Code Agent"),
            ("debug", "Debug Agent"),
            ("general", "General Agent")
        ]
        
        for agent_id, agent_name in default_agents:
            self.agent_states[agent_id] = AgentState(
                agent_id=agent_id,
                agent_name=agent_name,
                status=AgentStatus.IDLE,
                current_task=None,
                progress=0.0,
                last_activity=datetime.now(timezone.utc).isoformat(),
                connected_users=[]
            )
    
    def on_connect(self, auth):
        """Handle client connection"""
        try:
            client_id = request.sid
            user_id = auth.get('user_id') if auth else f"anonymous_{client_id[:8]}"
            
            # Store client information
            self.connected_clients[client_id] = {
                'user_id': user_id,
                'connected_at': datetime.now(timezone.utc).isoformat(),
                'rooms': [],
                'agent_subscriptions': []
            }
            
            logger.info(f"🔌 Client connected: {user_id} ({client_id})")
            
            # Send welcome message with current system state
            self._send_system_state(client_id)
            
            # Emit connection success
            emit('connection_status', {
                'status': 'connected',
                'client_id': client_id,
                'user_id': user_id,
                'timestamp': datetime.now(timezone.utc).isoformat()
            })
            
        except Exception as e:
            logger.error(f"❌ Connection error: {e}")
            emit('error', {'message': 'Connection failed', 'error': str(e)})
            disconnect()
    
    def on_disconnect(self):
        """Handle client disconnection"""
        try:
            client_id = request.sid
            
            if client_id in self.connected_clients:
                client_info = self.connected_clients[client_id]
                user_id = client_info['user_id']
                
                # Leave all rooms
                for room_id in client_info['rooms']:
                    self._leave_room_internal(client_id, room_id)
                
                # Remove from agent subscriptions
                for agent_id in client_info['agent_subscriptions']:
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
            agent_id = data.get('agent_id')
            
            if not agent_id or agent_id not in self.agent_states:
                emit('error', {'message': f'Invalid agent ID: {agent_id}'})
                return
            
            if client_id not in self.connected_clients:
                emit('error', {'message': 'Client not found'})
                return
            
            client_info = self.connected_clients[client_id]
            user_id = client_info['user_id']
            
            # Add to subscriptions
            if agent_id not in client_info['agent_subscriptions']:
                client_info['agent_subscriptions'].append(agent_id)
                self.agent_states[agent_id].connected_users.append(user_id)
            
            # Send current agent state
            agent_state = self.agent_states[agent_id]
            
            # Convert AgentState to dict with proper serialization
            state_dict = asdict(agent_state)
            state_dict['status'] = agent_state.status.value  # Convert enum to string
            
            emit('agent_state_update', {
                'agent_id': agent_id,
                'state': state_dict,
                'timestamp': datetime.now(timezone.utc).isoformat()
            })
            
            logger.info(f"📡 {user_id} subscribed to agent: {agent_id}")
            
        except Exception as e:
            logger.error(f"❌ Subscribe error: {e}")
            emit('error', {'message': 'Subscription failed', 'error': str(e)})
    
    def on_unsubscribe_agent(self, data):
        """Unsubscribe from agent updates"""
        try:
            client_id = request.sid
            agent_id = data.get('agent_id')
            
            if client_id not in self.connected_clients:
                return
            
            client_info = self.connected_clients[client_id]
            user_id = client_info['user_id']
            
            # Remove from subscriptions
            if agent_id in client_info['agent_subscriptions']:
                client_info['agent_subscriptions'].remove(agent_id)
                
                if agent_id in self.agent_states:
                    agent_state = self.agent_states[agent_id]
                    if user_id in agent_state.connected_users:
                        agent_state.connected_users.remove(user_id)
            
            logger.info(f"📡 {user_id} unsubscribed from agent: {agent_id}")
            
        except Exception as e:
            logger.error(f"❌ Unsubscribe error: {e}")
    
    def on_join_collaboration(self, data):
        """Join a collaboration room"""
        try:
            client_id = request.sid
            room_id = data.get('room_id')
            
            if not room_id:
                room_id = f"collab_{uuid.uuid4().hex[:8]}"
            
            # Join the room
            join_room(room_id)
            
            # Update client info
            if client_id in self.connected_clients:
                self.connected_clients[client_id]['rooms'].append(room_id)
            
            # Update room info
            if room_id not in self.active_rooms:
                self.active_rooms[room_id] = {
                    'created_at': datetime.now(timezone.utc).isoformat(),
                    'participants': [],
                    'agents': [],
                    'message_count': 0
                }
            
            user_id = self.connected_clients[client_id]['user_id']
            if user_id not in self.active_rooms[room_id]['participants']:
                self.active_rooms[room_id]['participants'].append(user_id)
            
            emit('collaboration_joined', {
                'room_id': room_id,
                'participants': self.active_rooms[room_id]['participants'],
                'timestamp': datetime.now(timezone.utc).isoformat()
            })
            
            # Notify other participants
            emit('participant_joined', {
                'user_id': user_id,
                'room_id': room_id,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }, room=room_id, include_self=False)
            
            logger.info(f"🤝 {user_id} joined collaboration room: {room_id}")
            
        except Exception as e:
            logger.error(f"❌ Join collaboration error: {e}")
            emit('error', {'message': 'Failed to join collaboration', 'error': str(e)})
    
    def on_leave_collaboration(self, data):
        """Leave a collaboration room"""
        try:
            client_id = request.sid
            room_id = data.get('room_id')
            
            self._leave_room_internal(client_id, room_id)
            
        except Exception as e:
            logger.error(f"❌ Leave collaboration error: {e}")
    
    def on_send_message(self, data):
        """Send a message to agents or collaboration room"""
        try:
            client_id = request.sid
            
            if client_id not in self.connected_clients:
                emit('error', {'message': 'Client not found'})
                return
            
            user_id = self.connected_clients[client_id]['user_id']
            
            # Create message
            message = WebSocketMessage(
                message_id=str(uuid.uuid4()),
                message_type=MessageType.USER_MESSAGE,
                timestamp=datetime.now(timezone.utc).isoformat(),
                sender_id=user_id,
                sender_type='user',
                content=data.get('content', ''),
                metadata=data.get('metadata', {}),
                room_id=data.get('room_id'),
                recipient_id=data.get('recipient_id')
            )
            
            # Handle different message targets
            if message.room_id:
                # Send to collaboration room
                self._send_to_room(message)
            elif message.recipient_id:
                # Send to specific agent
                self._send_to_agent(message)
            else:
                # Broadcast to all subscribed agents
                self._broadcast_to_agents(message)
            
        except Exception as e:
            logger.error(f"❌ Send message error: {e}")
            emit('error', {'message': 'Failed to send message', 'error': str(e)})
    
    def on_heartbeat(self, data):
        """Handle heartbeat from client"""
        emit('heartbeat_response', {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'status': 'alive'
        })
    
    def _send_system_state(self, client_id: str):
        """Send current system state to client"""
        try:
            system_state = {
                'agents': {agent_id: asdict(state) for agent_id, state in self.agent_states.items()},
                'active_rooms': self.active_rooms,
                'connected_clients': len(self.connected_clients),
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
            
            emit('system_state', system_state, room=client_id)
            
        except Exception as e:
            logger.error(f"❌ Send system state error: {e}")
    
    def _leave_room_internal(self, client_id: str, room_id: str):
        """Internal method to leave a room"""
        try:
            leave_room(room_id)
            
            if client_id in self.connected_clients:
                client_info = self.connected_clients[client_id]
                user_id = client_info['user_id']
                
                if room_id in client_info['rooms']:
                    client_info['rooms'].remove(room_id)
                
                # Update room info
                if room_id in self.active_rooms:
                    room_info = self.active_rooms[room_id]
                    if user_id in room_info['participants']:
                        room_info['participants'].remove(user_id)
                    
                    # Remove room if empty
                    if not room_info['participants']:
                        del self.active_rooms[room_id]
                    else:
                        # Notify other participants
                        emit('participant_left', {
                            'user_id': user_id,
                            'room_id': room_id,
                            'timestamp': datetime.now(timezone.utc).isoformat()
                        }, room=room_id)
                
                emit('collaboration_left', {
                    'room_id': room_id,
                    'timestamp': datetime.now(timezone.utc).isoformat()
                }, room=client_id)
                
                logger.info(f"🤝 {user_id} left collaboration room: {room_id}")
                
        except Exception as e:
            logger.error(f"❌ Leave room error: {e}")
    
    def _send_to_room(self, message: WebSocketMessage):
        """Send message to collaboration room"""
        try:
            emit('message_received', asdict(message), room=message.room_id)
            
            # Update room message count
            if message.room_id in self.active_rooms:
                self.active_rooms[message.room_id]['message_count'] += 1
                
        except Exception as e:
            logger.error(f"❌ Send to room error: {e}")
    
    def _send_to_agent(self, message: WebSocketMessage):
        """Send message to specific agent"""
        try:
            # This would integrate with the agent service
            # For now, we'll emit to all subscribers of the agent
            
            agent_id = message.recipient_id
            if agent_id in self.agent_states:
                # Update agent status
                self.update_agent_status(agent_id, AgentStatus.THINKING, "Processing user message")
                
                # Emit to agent subscribers
                emit('agent_message_received', asdict(message), 
                     room=f"agent_{agent_id}")
                
        except Exception as e:
            logger.error(f"❌ Send to agent error: {e}")
    
    def _broadcast_to_agents(self, message: WebSocketMessage):
        """Broadcast message to all agents"""
        try:
            emit('broadcast_message', asdict(message), broadcast=True)
            
        except Exception as e:
            logger.error(f"❌ Broadcast error: {e}")
    
    def update_agent_status(self, agent_id: str, status: AgentStatus, 
                          current_task: Optional[str] = None, progress: float = 0.0):
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
            emit('agent_status_update', {
                'agent_id': agent_id,
                'status': status.value,
                'current_task': current_task,
                'progress': progress,
                'timestamp': agent_state.last_activity
            }, broadcast=True)
            
        except Exception as e:
            logger.error(f"❌ Update agent status error: {e}")
    
    def send_agent_message(self, agent_id: str, content: str, 
                          message_type: MessageType = MessageType.AGENT_MESSAGE,
                          metadata: Optional[Dict[str, Any]] = None):
        """Send message from agent to clients"""
        try:
            message = WebSocketMessage(
                message_id=str(uuid.uuid4()),
                message_type=message_type,
                timestamp=datetime.now(timezone.utc).isoformat(),
                sender_id=agent_id,
                sender_type='agent',
                content=content,
                metadata=metadata or {}
            )
            
            emit('agent_message', asdict(message), broadcast=True)
            
        except Exception as e:
            logger.error(f"❌ Send agent message error: {e}")


class WebSocketService:
    """WebSocket service for real-time agent coordination"""
    
    def __init__(self, app: Flask):
        self.app = app
        self.socketio = SocketIO(
            app,
            cors_allowed_origins="*",
            async_mode='threading',
            logger=True,
            engineio_logger=True
        )
        
        # Register namespace
        self.namespace = SwarmWebSocketNamespace('/swarm')
        self.socketio.on_namespace(self.namespace)
        
        logger.info("🔌 WebSocket service initialized")
    
    def get_agent_states(self) -> Dict[str, AgentState]:
        """Get current agent states"""
        return self.namespace.agent_states
    
    def update_agent_status(self, agent_id: str, status: AgentStatus, 
                          current_task: Optional[str] = None, progress: float = 0.0):
        """Update agent status"""
        self.namespace.update_agent_status(agent_id, status, current_task, progress)
    
    def send_agent_message(self, agent_id: str, content: str, 
                          message_type: MessageType = MessageType.AGENT_MESSAGE,
                          metadata: Optional[Dict[str, Any]] = None):
        """Send message from agent"""
        self.namespace.send_agent_message(agent_id, content, message_type, metadata)
    
    def get_connected_clients_count(self) -> int:
        """Get number of connected clients"""
        return len(self.namespace.connected_clients)
    
    def get_active_rooms(self) -> Dict[str, Dict[str, Any]]:
        """Get active collaboration rooms"""
        return self.namespace.active_rooms

