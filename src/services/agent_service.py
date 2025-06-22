"""
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
                    system_prompt += "\n\n✅ **FILESYSTEM ACCESS ACTIVE** - You can read, write, and manage files in the workspace."
                else:
                    system_prompt += f"\n\n⚠️ **FILESYSTEM ACCESS LIMITED** - {health.get('error', 'Unknown issue')}"
            except Exception as e:
                system_prompt += f"\n\n❌ **FILESYSTEM ACCESS ERROR** - {str(e)}"
        else:
            system_prompt += "\n\n❌ **FILESYSTEM ACCESS UNAVAILABLE** - File operations are not currently supported."

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
