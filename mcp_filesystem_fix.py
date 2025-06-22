#!/usr/bin/env python3
"""
Comprehensive MCP Filesystem Integration Fix

This script addresses the critical issues preventing MCP filesystem from working:
1. Workspace directory creation and permissions
2. Flask app context in threading
3. Error handling and logging
4. Service initialization verification
"""

import os
import sys
import logging
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def fix_workspace_permissions():
    """Ensure workspace directory exists with proper permissions"""
    workspace_path = Path("/tmp/swarm_workspace")
    
    try:
        # Create workspace directory
        workspace_path.mkdir(parents=True, exist_ok=True)
        
        # Set proper permissions
        os.chmod(workspace_path, 0o755)
        
        # Create a test file to verify write permissions
        test_file = workspace_path / ".test_permissions"
        test_file.write_text("test")
        test_file.unlink()
        
        print(f"✅ Workspace directory created and verified: {workspace_path}")
        return True
        
    except Exception as e:
        print(f"❌ Failed to create workspace: {e}")
        return False

def create_enhanced_websocket_service():
    """Create enhanced WebSocket service with proper MCP integration"""
    
    websocket_service_content = '''"""
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
'''
    
    return websocket_service_content

def create_enhanced_agent_service():
    """Create enhanced agent service with better MCP integration"""
    
    agent_service_content = '''"""
Agent management system with proper MCP filesystem integration
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.exceptions import ServiceError, SwarmException
from src.services.base_service import BaseService, handle_service_errors
from src.services.openrouter_service import ChatMessage, ChatResponse, OpenRouterService
from src.services.supermemory_service import SupermemoryService

logger = logging.getLogger(__name__)


class AgentService(BaseService):
    """Enhanced agent service with MCP filesystem capabilities"""

    def __init__(
        self,
        openrouter_service: OpenRouterService,
        supermemory_service: SupermemoryService = None,
        mcp_filesystem_service = None,
    ):
        super().__init__("Agent")
        self.openrouter = openrouter_service
        self.supermemory = supermemory_service
        self.mcp_filesystem = mcp_filesystem_service
        
        # Log MCP filesystem status
        if self.mcp_filesystem:
            health = self.mcp_filesystem.health_check()
            logger.info(f"✅ AgentService initialized with MCP filesystem: {health.get('status', 'unknown')}")
        else:
            logger.warning("⚠️ AgentService initialized without MCP filesystem")

        # Define agent capabilities with MCP filesystem support
        self.agents = {
            "email_agent": {
                "name": "Email Agent",
                "description": "Specialized in professional email composition, analysis, and workflow automation",
                "capabilities": ["email_composition", "email_analysis", "workflow_automation"],
                "system_prompt": self._get_email_agent_prompt(),
                "mcp_enabled": True,
            },
            "calendar_agent": {
                "name": "Calendar Agent", 
                "description": "Handles scheduling, time management, and meeting coordination",
                "capabilities": ["scheduling", "time_management", "meeting_coordination"],
                "system_prompt": self._get_calendar_agent_prompt(),
                "mcp_enabled": True,
            },
            "code_agent": {
                "name": "Code Agent",
                "description": "Software development, debugging, and technical implementation",
                "capabilities": ["code_generation", "debugging", "technical_analysis"],
                "system_prompt": self._get_code_agent_prompt(),
                "mcp_enabled": True,
            },
            "debug_agent": {
                "name": "Debug Agent",
                "description": "Troubleshooting, system diagnostics, and error resolution",
                "capabilities": ["troubleshooting", "diagnostics", "error_resolution"],
                "system_prompt": self._get_debug_agent_prompt(),
                "mcp_enabled": True,
            },
            "general_agent": {
                "name": "General Agent",
                "description": "Task coordination, routing, and general assistance",
                "capabilities": ["task_coordination", "routing", "general_assistance"],
                "system_prompt": self._get_general_agent_prompt(),
                "mcp_enabled": True,
            },
        }

    def _get_base_system_prompt(self) -> str:
        """Get base system prompt with MCP filesystem capabilities"""
        mcp_capabilities = ""
        
        if self.mcp_filesystem:
            try:
                stats = self.mcp_filesystem.get_workspace_stats()
                mcp_capabilities = f"""

## 🗂️ FILESYSTEM ACCESS CAPABILITIES

You have access to a secure filesystem workspace for file operations:

**Workspace:** {stats.get('workspace_path', '/tmp/swarm_workspace')}
**Available Operations:**
- Read files and directories
- Write and create new files  
- Create directories
- Move and copy files
- Delete files and directories
- Get file information and statistics

**Supported File Types:** {', '.join(stats.get('allowed_extensions', []))}
**Max File Size:** {stats.get('max_file_size_mb', 10)}MB

**Usage Guidelines:**
- Always use relative paths within the workspace
- Check if files exist before operations
- Create directories as needed
- Use appropriate file extensions
- Handle errors gracefully

**Example Operations:**
- To read a file: "Please read the contents of 'notes.txt'"
- To create a file: "Create a new file called 'report.md' with this content..."
- To list directory: "Show me what files are in the 'projects' folder"
- To organize files: "Create a folder called 'documents' and move all .pdf files there"

You can perform these operations directly - no need to ask for permission.
"""
        else:
            mcp_capabilities = """

## ⚠️ FILESYSTEM ACCESS UNAVAILABLE

Filesystem access is currently not available. You cannot read, write, or manage files directly.
"""

        return f"""You are an AI agent in a multi-agent collaboration system. You work alongside other specialized agents to help users accomplish their goals.

## CORE PRINCIPLES
- Be helpful, accurate, and professional
- Collaborate effectively with other agents when needed
- Provide clear, actionable responses
- Ask clarifying questions when needed
- Acknowledge limitations honestly

## COLLABORATION
- You can work independently or with other agents
- Use @mention to bring other agents into conversations
- Share relevant information between agents
- Coordinate tasks effectively

{mcp_capabilities}

## MEMORY SYSTEM
- Conversations are stored in shared memory for context
- Previous interactions inform current responses
- Maintain consistency across sessions

Remember: You are part of a team. Focus on your specialization while being ready to collaborate.
"""

    def _get_email_agent_prompt(self) -> str:
        """Get email agent system prompt with MCP capabilities"""
        base_prompt = self._get_base_system_prompt()
        return f"""{base_prompt}

## EMAIL AGENT SPECIALIZATION

You are the **Email Agent** - specialized in professional email composition, analysis, and workflow automation.

**Your Expertise:**
- Professional email writing and editing
- Email template creation and management
- Email workflow optimization
- Communication strategy and etiquette
- Email analytics and insights

**Key Capabilities:**
- Draft professional emails for any purpose
- Analyze and improve existing emails
- Create reusable email templates
- Suggest email automation workflows
- Provide communication best practices

**File Operations for Email:**
- Save email templates to files
- Read and analyze email drafts
- Create email campaign files
- Organize email-related documents

Focus on clear, professional communication and efficient email workflows.
"""

    def _get_calendar_agent_prompt(self) -> str:
        """Get calendar agent system prompt with MCP capabilities"""
        base_prompt = self._get_base_system_prompt()
        return f"""{base_prompt}

## CALENDAR AGENT SPECIALIZATION

You are the **Calendar Agent** - specialized in scheduling, time management, and meeting coordination.

**Your Expertise:**
- Meeting scheduling and coordination
- Calendar optimization and time blocking
- Event planning and management
- Time zone coordination
- Productivity scheduling strategies

**Key Capabilities:**
- Schedule meetings and events
- Optimize calendar layouts
- Coordinate across time zones
- Plan recurring events
- Suggest productivity improvements

**File Operations for Scheduling:**
- Save meeting agendas and notes
- Create calendar templates
- Store scheduling preferences
- Manage event documentation

Focus on efficient time management and seamless scheduling coordination.
"""

    def _get_code_agent_prompt(self) -> str:
        """Get code agent system prompt with MCP capabilities"""
        base_prompt = self._get_base_system_prompt()
        return f"""{base_prompt}

## CODE AGENT SPECIALIZATION

You are the **Code Agent** - specialized in software development, debugging, and technical implementation.

**Your Expertise:**
- Code generation and optimization
- Debugging and troubleshooting
- Architecture and design patterns
- Code review and best practices
- Technical documentation

**Key Capabilities:**
- Write code in multiple languages
- Debug and fix code issues
- Suggest improvements and optimizations
- Create technical documentation
- Implement software solutions

**File Operations for Development:**
- Read and analyze code files
- Create new code files and projects
- Save code snippets and templates
- Organize project structures
- Manage documentation files

Focus on clean, efficient code and robust software solutions.
"""

    def _get_debug_agent_prompt(self) -> str:
        """Get debug agent system prompt with MCP capabilities"""
        base_prompt = self._get_base_system_prompt()
        return f"""{base_prompt}

## DEBUG AGENT SPECIALIZATION

You are the **Debug Agent** - specialized in troubleshooting, system diagnostics, and error resolution.

**Your Expertise:**
- Error analysis and resolution
- System diagnostics and monitoring
- Performance troubleshooting
- Log analysis and interpretation
- Root cause analysis

**Key Capabilities:**
- Analyze error messages and logs
- Diagnose system issues
- Suggest debugging strategies
- Create diagnostic procedures
- Document solutions

**File Operations for Debugging:**
- Read log files and error reports
- Create diagnostic scripts
- Save troubleshooting procedures
- Organize debugging documentation

Focus on systematic problem-solving and clear diagnostic procedures.
"""

    def _get_general_agent_prompt(self) -> str:
        """Get general agent system prompt with MCP capabilities"""
        base_prompt = self._get_base_system_prompt()
        return f"""{base_prompt}

## GENERAL AGENT SPECIALIZATION

You are the **General Agent** - specialized in task coordination, routing, and general assistance.

**Your Expertise:**
- Task coordination and management
- Agent routing and collaboration
- General problem-solving
- Information synthesis
- Project management

**Key Capabilities:**
- Coordinate multi-agent tasks
- Route requests to appropriate agents
- Provide general assistance
- Synthesize information from multiple sources
- Manage project workflows

**File Operations for Coordination:**
- Create project documentation
- Save task lists and workflows
- Organize shared resources
- Manage collaboration files

Focus on effective coordination and comprehensive assistance across all domains.
"""

    @handle_service_errors
    def chat_with_agent(
        self, agent_id: str, message: str, model: str = "openai/gpt-4o"
    ) -> ChatResponse:
        """Enhanced chat with agent including MCP filesystem capabilities"""
        
        if agent_id not in self.agents:
            raise ServiceError(
                f"Unknown agent: {agent_id}",
                error_code="UNKNOWN_AGENT",
                details={"agent_id": agent_id, "available_agents": list(self.agents.keys())},
            )

        agent_config = self.agents[agent_id]
        
        # Build system prompt with MCP capabilities
        system_prompt = agent_config["system_prompt"]
        
        # Add current MCP status to system prompt
        if self.mcp_filesystem and agent_config.get("mcp_enabled", False):
            try:
                health = self.mcp_filesystem.health_check()
                if health.get("status") == "healthy":
                    system_prompt += "\\n\\n✅ **FILESYSTEM ACCESS ACTIVE** - You can read, write, and manage files in the workspace."
                else:
                    system_prompt += f"\\n\\n⚠️ **FILESYSTEM ACCESS LIMITED** - {health.get('error', 'Unknown issue')}"
            except Exception as e:
                system_prompt += f"\\n\\n❌ **FILESYSTEM ACCESS ERROR** - {str(e)}"
        else:
            system_prompt += "\\n\\n❌ **FILESYSTEM ACCESS UNAVAILABLE** - File operations are not currently supported."

        # Prepare messages
        messages = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=message),
        ]

        try:
            # Get response from OpenRouter
            response = self.openrouter.chat_completion(
                messages=messages,
                model=model,
                temperature=0.7,
                max_tokens=2000,
            )

            logger.info(f"✅ Agent {agent_id} responded successfully (MCP: {'enabled' if self.mcp_filesystem else 'disabled'})")
            return response

        except Exception as e:
            logger.error(f"❌ Agent {agent_id} chat error: {e}")
            
            # Return fallback response
            fallback_content = f"I apologize, but I encountered a technical issue while processing your request. Error: {str(e)}. Please try again or contact support if the issue persists."
            
            return ChatResponse(
                content=fallback_content,
                model=model,
                usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                finish_reason="error"
            )

    def get_agent_info(self, agent_id: str) -> Dict[str, Any]:
        """Get detailed agent information including MCP status"""
        if agent_id not in self.agents:
            raise ServiceError(f"Unknown agent: {agent_id}", error_code="UNKNOWN_AGENT")

        agent_config = self.agents[agent_id].copy()
        
        # Add MCP filesystem status
        if self.mcp_filesystem and agent_config.get("mcp_enabled", False):
            try:
                health = self.mcp_filesystem.health_check()
                agent_config["mcp_status"] = health.get("status", "unknown")
                agent_config["mcp_details"] = health
            except Exception as e:
                agent_config["mcp_status"] = "error"
                agent_config["mcp_error"] = str(e)
        else:
            agent_config["mcp_status"] = "disabled"

        return agent_config

    def list_agents(self) -> Dict[str, Any]:
        """List all available agents with MCP status"""
        agents_info = {}
        
        for agent_id in self.agents:
            agents_info[agent_id] = self.get_agent_info(agent_id)
        
        # Add overall MCP status
        mcp_overall_status = "disabled"
        if self.mcp_filesystem:
            try:
                health = self.mcp_filesystem.health_check()
                mcp_overall_status = health.get("status", "unknown")
            except:
                mcp_overall_status = "error"
        
        return {
            "agents": agents_info,
            "total_count": len(agents_info),
            "mcp_filesystem_status": mcp_overall_status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def health_check(self) -> Dict[str, Any]:
        """Enhanced health check including MCP filesystem status"""
        try:
            # Test OpenRouter connection
            test_response = self.openrouter.chat_completion(
                messages=[ChatMessage(role="user", content="Hello")],
                model="openai/gpt-4o-mini",
                max_tokens=10,
            )
            openrouter_status = "healthy" if test_response else "unhealthy"
        except Exception as e:
            openrouter_status = f"error: {str(e)}"

        # Test MCP filesystem
        mcp_status = "disabled"
        mcp_details = None
        if self.mcp_filesystem:
            try:
                mcp_health = self.mcp_filesystem.health_check()
                mcp_status = mcp_health.get("status", "unknown")
                mcp_details = mcp_health
            except Exception as e:
                mcp_status = f"error: {str(e)}"

        return {
            "service": "agent_service",
            "status": "healthy" if openrouter_status == "healthy" else "degraded",
            "openrouter_status": openrouter_status,
            "mcp_filesystem_status": mcp_status,
            "mcp_details": mcp_details,
            "agent_count": len(self.agents),
            "agents": list(self.agents.keys()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
'''
    
    return agent_service_content

def apply_fixes():
    """Apply all the MCP filesystem integration fixes"""
    
    print("🔧 Applying MCP Filesystem Integration Fixes...")
    
    # 1. Fix workspace permissions
    if not fix_workspace_permissions():
        print("❌ Failed to fix workspace permissions")
        return False
    
    # 2. Create enhanced WebSocket service
    try:
        websocket_content = create_enhanced_websocket_service()
        with open("src/services/websocket_service.py", "w") as f:
            f.write(websocket_content)
        print("✅ Enhanced WebSocket service created")
    except Exception as e:
        print(f"❌ Failed to create enhanced WebSocket service: {e}")
        return False
    
    # 3. Create enhanced Agent service
    try:
        agent_content = create_enhanced_agent_service()
        with open("src/services/agent_service.py", "w") as f:
            f.write(agent_content)
        print("✅ Enhanced Agent service created")
    except Exception as e:
        print(f"❌ Failed to create enhanced Agent service: {e}")
        return False
    
    print("🎉 All MCP filesystem integration fixes applied successfully!")
    return True

if __name__ == "__main__":
    success = apply_fixes()
    sys.exit(0 if success else 1)

