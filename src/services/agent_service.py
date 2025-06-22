"""
Agent management system with proper definitions and capabilities
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from src.config_flexible import get_config
from src.exceptions import AgentNotFoundError, ValidationError
from src.services.openrouter_service import ChatMessage, ChatResponse, OpenRouterService
from src.services.supermemory_service import SupermemoryService
from src.services.mcp_filesystem import MCPFilesystemService

logger = logging.getLogger(__name__)


class AgentCapability(Enum):
    """Enumeration of agent capabilities"""

    EMAIL_COMPOSITION = "email_composition"
    EMAIL_ANALYSIS = "email_analysis"
    WORKFLOW_AUTOMATION = "workflow_automation"
    SCHEDULING = "scheduling"
    TIME_MANAGEMENT = "time_management"
    MEETING_COORDINATION = "meeting_coordination"
    CODING = "coding"
    DEBUGGING = "debugging"
    ARCHITECTURE_DESIGN = "architecture_design"
    CODE_REVIEW = "code_review"
    TROUBLESHOOTING = "troubleshooting"
    SYSTEM_ANALYSIS = "system_analysis"
    ERROR_RESOLUTION = "error_resolution"
    TASK_COORDINATION = "task_coordination"
    GENERAL_ASSISTANCE = "general_assistance"
    ROUTING = "routing"
    PLANNING = "planning"


@dataclass
class AgentDefinition:
    """Definition of an agent with its capabilities and configuration"""

    agent_id: str
    name: str
    description: str
    capabilities: List[AgentCapability]
    system_prompt: str
    preferred_models: List[str]
    default_model: str
    max_context_messages: int = 10
    temperature: float = 0.7

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "description": self.description,
            "capabilities": [cap.value for cap in self.capabilities],
            "preferred_models": self.preferred_models,
            "default_model": self.default_model,
            "system_prompt": self.system_prompt,
        }


class AgentRegistry:
    """Registry of all available agents"""

    def __init__(self):
        self._agents: Dict[str, AgentDefinition] = {}
        self._initialize_default_agents()

    def _initialize_default_agents(self):
        """Initialize the default set of agents"""

        # Email Agent
        self.register_agent(
            AgentDefinition(
                agent_id="email",
                name="Email Agent",
                description="Specialized in professional email composition, analysis, and workflow automation",
                capabilities=[
                    AgentCapability.EMAIL_COMPOSITION,
                    AgentCapability.EMAIL_ANALYSIS,
                    AgentCapability.WORKFLOW_AUTOMATION,
                ],
                system_prompt="""You are an Email Agent specialized in professional email composition, analysis, and workflow automation. 

Your core responsibilities:
- Compose clear, professional emails for various business contexts
- Analyze email content for tone, clarity, and effectiveness
- Suggest improvements for email communication
- Help automate email workflows and templates
- Ensure proper email etiquette and formatting

Always maintain a professional tone while being helpful and efficient. When composing emails, consider the recipient, context, and desired outcome.""",
                preferred_models=["openai/gpt-4o", "openai/gpt-4o-mini"],
                default_model="openai/gpt-4o",
            )
        )

        # Calendar Agent
        self.register_agent(
            AgentDefinition(
                agent_id="calendar",
                name="Calendar Agent",
                description="Handles scheduling, time management, and meeting coordination",
                capabilities=[
                    AgentCapability.SCHEDULING,
                    AgentCapability.TIME_MANAGEMENT,
                    AgentCapability.MEETING_COORDINATION,
                ],
                system_prompt="""You are a Calendar Agent specialized in scheduling, time management, and meeting coordination.

Your core responsibilities:
- Help schedule meetings and appointments efficiently
- Resolve scheduling conflicts and find optimal meeting times
- Provide time management advice and strategies
- Coordinate complex multi-participant meetings
- Suggest meeting agendas and follow-up actions

Focus on efficiency, clarity, and consideration for all participants' time. Always confirm details and provide clear next steps.""",
                preferred_models=["openai/gpt-4o-mini", "anthropic/claude-3.5-sonnet"],
                default_model="openai/gpt-4o-mini",
            )
        )

        # Code Agent
        self.register_agent(
            AgentDefinition(
                agent_id="code",
                name="Code Agent",
                description="Software development, debugging, and technical implementation specialist",
                capabilities=[
                    AgentCapability.CODING,
                    AgentCapability.DEBUGGING,
                    AgentCapability.ARCHITECTURE_DESIGN,
                    AgentCapability.CODE_REVIEW,
                ],
                system_prompt="""You are a Code Agent specialized in software development, debugging, and technical implementation.

Your core responsibilities:
- Write clean, efficient, and well-documented code
- Debug complex technical issues and provide solutions
- Design software architecture and system components
- Review code for quality, security, and best practices
- Explain technical concepts clearly to different audiences

Focus on code quality, security, maintainability, and following best practices. Always provide clear explanations and consider the broader system context.""",
                preferred_models=["deepseek/deepseek-r1", "openai/gpt-4o"],
                default_model="openai/gpt-4o",
            )
        )

        # Debug Agent
        self.register_agent(
            AgentDefinition(
                agent_id="debug",
                name="Debug Agent",
                description="Troubleshooting, system diagnostics, and error resolution specialist",
                capabilities=[
                    AgentCapability.DEBUGGING,
                    AgentCapability.TROUBLESHOOTING,
                    AgentCapability.SYSTEM_ANALYSIS,
                    AgentCapability.ERROR_RESOLUTION,
                ],
                system_prompt="""You are a Debug Agent specialized in troubleshooting, system diagnostics, and error resolution.

Your core responsibilities:
- Analyze error messages and system logs to identify root causes
- Provide step-by-step debugging procedures
- Suggest preventive measures to avoid future issues
- Help optimize system performance and reliability
- Guide users through complex troubleshooting processes

Be methodical, thorough, and patient. Break down complex problems into manageable steps and always verify solutions.""",
                preferred_models=["openai/gpt-4o", "anthropic/claude-3.5-sonnet"],
                default_model="openai/gpt-4o",
            )
        )

        # General Agent
        self.register_agent(
            AgentDefinition(
                agent_id="general",
                name="General Agent",
                description="Task coordination, routing, and general assistance",
                capabilities=[
                    AgentCapability.TASK_COORDINATION,
                    AgentCapability.GENERAL_ASSISTANCE,
                    AgentCapability.ROUTING,
                    AgentCapability.PLANNING,
                ],
                system_prompt="""You are a General Agent specialized in task coordination, routing, and general assistance.

Your core responsibilities:
- Coordinate tasks between different agents and systems
- Route requests to the most appropriate specialist agents
- Provide general assistance for various tasks
- Help plan and organize complex multi-step projects
- Facilitate communication and collaboration

Be helpful, organized, and efficient. When tasks require specialized expertise, recommend the appropriate specialist agent while providing initial guidance.""",
                preferred_models=["anthropic/claude-3.5-sonnet", "openai/gpt-4o"],
                default_model="anthropic/claude-3.5-sonnet",
            )
        )

    def register_agent(self, agent: AgentDefinition):
        """Register a new agent"""
        self._agents[agent.agent_id] = agent
        logger.info(f"Registered agent: {agent.name} ({agent.agent_id})")

    def get_agent(self, agent_id: str) -> AgentDefinition:
        """Get agent by ID"""
        if agent_id not in self._agents:
            raise AgentNotFoundError(
                f"Agent '{agent_id}' not found",
                error_code="AGENT_NOT_FOUND",
                details={"agent_id": agent_id, "available_agents": list(self._agents.keys())},
            )
        return self._agents[agent_id]

    def list_agents(self) -> List[AgentDefinition]:
        """Get list of all agents"""
        return list(self._agents.values())

    def get_agents_by_capability(self, capability: AgentCapability) -> List[AgentDefinition]:
        """Get agents that have a specific capability"""
        return [agent for agent in self._agents.values() if capability in agent.capabilities]


class AgentService:
    """Service for managing agent interactions with memory persistence"""

    def __init__(
        self, 
        openrouter_service: OpenRouterService, 
        supermemory_service: SupermemoryService = None,
        mcp_filesystem_service: MCPFilesystemService = None
    ):
        self.openrouter = openrouter_service
        self.supermemory = supermemory_service
        self.mcp_filesystem = mcp_filesystem_service
        self.registry = AgentRegistry()

        if not self.supermemory:
            logger.warning("Supermemory service not provided - conversation persistence disabled")
        
        if not self.mcp_filesystem:
            logger.warning("MCP Filesystem service not provided - file operations disabled")
        else:
            logger.info("MCP Filesystem service enabled - agents can access files")

    def get_agent_info(self, agent_id: str) -> Dict[str, Any]:
        """Get agent information"""
        agent = self.registry.get_agent(agent_id)
        return agent.to_dict()

    def list_all_agents(self) -> List[Dict[str, Any]]:
        """Get list of all available agents"""
        return [agent.to_dict() for agent in self.registry.list_agents()]

    def chat_with_agent(
        self,
        agent_id: str,
        message: str,
        conversation_history: List[Dict[str, str]] = None,
        model: str = None,
    ) -> ChatResponse:
        """Chat with a specific agent with memory persistence"""

        # Validate inputs
        if not message.strip():
            raise ValidationError("Message cannot be empty")

        # Get agent definition
        agent = self.registry.get_agent(agent_id)

        # Use specified model or agent's default
        selected_model = model or agent.default_model

        # Validate model is in agent's preferred list
        if selected_model not in agent.preferred_models:
            logger.warning(f"Model {selected_model} not in preferred list for agent {agent_id}")

        # Get relevant context from memory if available
        context = ""
        if self.supermemory:
            try:
                context = self.supermemory.get_agent_context(
                    agent_id=agent_id, current_message=message, context_limit=3
                )
            except Exception as e:
                logger.warning(f"Failed to get context from Supermemory: {e}")

        # Build message list
        messages = [ChatMessage(role="system", content=agent.system_prompt)]

        # Add MCP filesystem capabilities if available
        if self.mcp_filesystem:
            filesystem_prompt = """

FILESYSTEM ACCESS CAPABILITIES:
You have access to a secure filesystem through MCP (Model Context Protocol). You can:

- READ FILES: Access and read file contents from the workspace
- WRITE FILES: Create and modify files in the workspace  
- LIST DIRECTORIES: Browse folder contents and file structures
- CREATE DIRECTORIES: Make new folders for organization
- DELETE FILES/FOLDERS: Remove files and directories when needed
- MOVE/RENAME: Reorganize files and folders
- COPY FILES: Duplicate files and directories

IMPORTANT FILESYSTEM GUIDELINES:
- Always use relative paths from the workspace root
- Supported file types: .txt, .md, .json, .yaml, .csv, .log, .py, .js, .html, .css, .xml, .sql, .sh, .pdf, .doc, .docx, .xls, .xlsx, .ppt, .pptx
- Maximum file size: 10MB
- When users ask about files or folders, you CAN access them directly
- Provide specific file operations and show actual file contents
- Use proper error handling and inform users of any limitations

To perform file operations, describe what you want to do and I will execute the filesystem commands for you.
"""
            messages.append(ChatMessage(role="system", content=filesystem_prompt))

        # Add context if available
        if context:
            messages.append(
                ChatMessage(
                    role="system",
                    content=f"Relevant context from previous conversations:\n{context}",
                )
            )

        # Add conversation history (limited)
        if conversation_history:
            history_limit = min(len(conversation_history), agent.max_context_messages)
            for hist_msg in conversation_history[-history_limit:]:
                if hist_msg.get("role") and hist_msg.get("content"):
                    messages.append(ChatMessage(role=hist_msg["role"], content=hist_msg["content"]))

        # Add current message
        messages.append(ChatMessage(role="user", content=message))

        # Get response from OpenRouter
        response = self.openrouter.chat_completion(messages, selected_model)

        # Store conversation in memory if available
        if self.supermemory and response:
            try:
                self.supermemory.store_conversation(
                    agent_id=agent_id,
                    user_message=message,
                    agent_response=response.content,
                    model_used=selected_model,
                    metadata={"timestamp": response.created, "usage": response.usage},
                )
                logger.info(f"Stored conversation for agent {agent_id} in Supermemory")
            except Exception as e:
                logger.error(f"Failed to store conversation in Supermemory: {e}")

        return response

    def get_conversation_history(self, agent_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Get conversation history for an agent"""
        if not self.supermemory:
            logger.warning("Supermemory service not available - returning empty history")
            return []

        try:
            conversations = self.supermemory.get_conversation_history(agent_id, limit)
            return [
                {
                    "id": conv.id,
                    "user_message": conv.user_message,
                    "agent_response": conv.agent_response,
                    "timestamp": conv.timestamp,
                    "model_used": conv.model_used,
                }
                for conv in conversations
            ]
        except Exception as e:
            logger.error(f"Failed to get conversation history for {agent_id}: {e}")
            return []

    def clear_agent_memory(self, agent_id: str) -> bool:
        """Clear memory for a specific agent"""
        if not self.supermemory:
            logger.warning("Supermemory service not available")
            return False

        try:
            return self.supermemory.clear_agent_memory(agent_id)
        except Exception as e:
            logger.error(f"Failed to clear memory for {agent_id}: {e}")
            return False

    def suggest_agent_for_task(self, task_description: str) -> List[str]:
        """Suggest appropriate agents for a given task"""
        # Simple keyword-based suggestion (could be enhanced with ML)
        suggestions = []
        task_lower = task_description.lower()

        if any(word in task_lower for word in ["email", "message", "compose", "send"]):
            suggestions.append("email")

        if any(word in task_lower for word in ["schedule", "meeting", "calendar", "time"]):
            suggestions.append("calendar")

        if any(word in task_lower for word in ["code", "program", "develop", "implement"]):
            suggestions.append("code")

        if any(word in task_lower for word in ["debug", "error", "fix", "troubleshoot"]):
            suggestions.append("debug")

        # Always include general as fallback
        if not suggestions:
            suggestions.append("general")

        return suggestions
