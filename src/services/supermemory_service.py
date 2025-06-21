"""
Supermemory Service - Real implementation for conversation persistence and memory management
"""

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

from src.exceptions import ServiceError, SwarmException
from src.services.base_service import BaseService, handle_service_errors

logger = logging.getLogger(__name__)


@dataclass
class ConversationEntry:
    """Represents a single conversation entry"""

    id: str
    agent_id: str
    user_message: str
    agent_response: str
    timestamp: str
    model_used: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class MemoryQuery:
    """Represents a memory query for context retrieval"""

    query: str
    agent_id: Optional[str] = None
    limit: int = 10
    similarity_threshold: float = 0.7


class SupermemoryService(BaseService):
    """Service for managing conversation persistence and memory with Supermemory API"""

    def __init__(self, api_key: str, base_url: str = "https://api.supermemory.ai"):
        super().__init__("Supermemory")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

        # Validate API key on initialization
        if not self.api_key or not self.api_key.startswith("sm_"):
            raise ServiceError(
                "Invalid Supermemory API key format",
                error_code="INVALID_API_KEY",
                details={"expected_format": "sm_*"},
            )

    @handle_service_errors
    def store_conversation(
        self,
        agent_id: str,
        user_message: str,
        agent_response: str,
        model_used: str = None,
        metadata: Dict[str, Any] = None,
    ) -> str:
        """Store a conversation entry in Supermemory"""

        # Create conversation entry
        entry = ConversationEntry(
            id=f"{agent_id}_{datetime.now(timezone.utc).isoformat()}",
            agent_id=agent_id,
            user_message=user_message,
            agent_response=agent_response,
            timestamp=datetime.now(timezone.utc).isoformat(),
            model_used=model_used,
            metadata=metadata or {},
        )

        # Prepare content for storage
        content = f"""
Agent: {agent_id}
User: {user_message}
Assistant: {agent_response}
Model: {model_used or 'unknown'}
Timestamp: {entry.timestamp}
"""

        # Add metadata as tags
        tags = [f"agent:{agent_id}"]
        if model_used:
            tags.append(f"model:{model_used}")
        if metadata:
            for key, value in metadata.items():
                tags.append(f"{key}:{value}")

        payload = {
            "content": content,
            "title": f"Conversation with {agent_id}",
            "description": f"User conversation with {agent_id} agent",
            "tags": tags,
            "metadata": {
                "entry_id": entry.id,
                "agent_id": agent_id,
                "timestamp": entry.timestamp,
                "model_used": model_used,
                **metadata,
            },
        }

        try:
            response = self.post(f"{self.base_url}/api/add", json=payload, headers=self.headers)

            if response.status_code == 201:
                result = response.json()
                logger.info(f"Successfully stored conversation for agent {agent_id}")
                return result.get("id", entry.id)
            else:
                raise ServiceError(
                    f"Failed to store conversation: {response.status_code}",
                    error_code="STORAGE_FAILED",
                    details={"status_code": response.status_code, "response": response.text},
                )

        except requests.exceptions.RequestException as e:
            raise ServiceError(
                f"Network error storing conversation: {str(e)}",
                error_code="NETWORK_ERROR",
                details={"error": str(e)},
            )

    @handle_service_errors
    def get_conversation_history(self, agent_id: str, limit: int = 20) -> List[ConversationEntry]:
        """Retrieve conversation history for a specific agent"""

        try:
            # Query for conversations with this agent
            query_payload = {"query": f"agent:{agent_id}", "limit": limit, "include_metadata": True}

            response = self.post(
                f"{self.base_url}/api/search", json=query_payload, headers=self.headers
            )

            if response.status_code == 200:
                results = response.json()
                conversations = []

                for item in results.get("results", []):
                    metadata = item.get("metadata", {})

                    # Extract conversation details from metadata
                    if metadata.get("agent_id") == agent_id:
                        # Parse content to extract user message and agent response
                        content = item.get("content", "")
                        lines = content.strip().split("\n")

                        user_message = ""
                        agent_response = ""

                        for line in lines:
                            if line.startswith("User: "):
                                user_message = line[6:]
                            elif line.startswith("Assistant: "):
                                agent_response = line[11:]

                        if user_message and agent_response:
                            conversation = ConversationEntry(
                                id=metadata.get("entry_id", item.get("id")),
                                agent_id=agent_id,
                                user_message=user_message,
                                agent_response=agent_response,
                                timestamp=metadata.get("timestamp", ""),
                                model_used=metadata.get("model_used"),
                                metadata=metadata,
                            )
                            conversations.append(conversation)

                # Sort by timestamp (newest first)
                conversations.sort(key=lambda x: x.timestamp, reverse=True)
                logger.info(f"Retrieved {len(conversations)} conversations for agent {agent_id}")
                return conversations

            else:
                raise ServiceError(
                    f"Failed to retrieve conversation history: {response.status_code}",
                    error_code="RETRIEVAL_FAILED",
                    details={"status_code": response.status_code, "response": response.text},
                )

        except requests.exceptions.RequestException as e:
            raise ServiceError(
                f"Network error retrieving conversation history: {str(e)}",
                error_code="NETWORK_ERROR",
                details={"error": str(e)},
            )

    @handle_service_errors
    def search_memory(self, query: MemoryQuery) -> List[Dict[str, Any]]:
        """Search memory for relevant context based on query"""

        # Build search query
        search_query = query.query
        if query.agent_id:
            search_query = f"{search_query} agent:{query.agent_id}"

        payload = {
            "query": search_query,
            "limit": query.limit,
            "similarity_threshold": query.similarity_threshold,
            "include_metadata": True,
        }

        try:
            response = self.post(f"{self.base_url}/api/search", json=payload, headers=self.headers)

            if response.status_code == 200:
                results = response.json()
                memory_items = []

                for item in results.get("results", []):
                    memory_item = {
                        "id": item.get("id"),
                        "content": item.get("content"),
                        "relevance_score": item.get("score", 0),
                        "metadata": item.get("metadata", {}),
                        "timestamp": item.get("metadata", {}).get("timestamp"),
                    }
                    memory_items.append(memory_item)

                logger.info(
                    f"Found {len(memory_items)} relevant memory items for query: {query.query}"
                )
                return memory_items

            else:
                raise ServiceError(
                    f"Failed to search memory: {response.status_code}",
                    error_code="SEARCH_FAILED",
                    details={"status_code": response.status_code, "response": response.text},
                )

        except requests.exceptions.RequestException as e:
            raise ServiceError(
                f"Network error searching memory: {str(e)}",
                error_code="NETWORK_ERROR",
                details={"error": str(e)},
            )

    @handle_service_errors
    def get_agent_context(self, agent_id: str, current_message: str, context_limit: int = 5) -> str:
        """Get relevant context for an agent based on current message"""

        # Search for relevant past conversations
        query = MemoryQuery(query=current_message, agent_id=agent_id, limit=context_limit)

        memory_items = self.search_memory(query)

        if not memory_items:
            return ""

        # Build context string
        context_parts = []
        context_parts.append("## Relevant Past Conversations:")

        for item in memory_items:
            content = item["content"]
            score = item["relevance_score"]
            timestamp = item.get("timestamp", "Unknown time")

            context_parts.append(f"\n**Conversation from {timestamp} (relevance: {score:.2f}):**")
            context_parts.append(content)

        context = "\n".join(context_parts)
        logger.info(
            f"Generated context for agent {agent_id} with {len(memory_items)} relevant items"
        )
        return context

    @handle_service_errors
    def clear_agent_memory(self, agent_id: str) -> bool:
        """Clear all memory for a specific agent"""

        try:
            # First, search for all items for this agent
            query_payload = {
                "query": f"agent:{agent_id}",
                "limit": 1000,  # Large limit to get all items
                "include_metadata": True,
            }

            response = self.post(
                f"{self.base_url}/api/search", json=query_payload, headers=self.headers
            )

            if response.status_code == 200:
                results = response.json()
                items_to_delete = []

                for item in results.get("results", []):
                    if item.get("metadata", {}).get("agent_id") == agent_id:
                        items_to_delete.append(item.get("id"))

                # Delete each item
                deleted_count = 0
                for item_id in items_to_delete:
                    try:
                        delete_response = self.delete(
                            f"{self.base_url}/api/delete/{item_id}", headers=self.headers
                        )
                        if delete_response.status_code in [200, 204]:
                            deleted_count += 1
                    except Exception as e:
                        logger.warning(f"Failed to delete item {item_id}: {e}")

                logger.info(f"Cleared {deleted_count} memory items for agent {agent_id}")
                return deleted_count > 0

            else:
                raise ServiceError(
                    f"Failed to search for agent memory: {response.status_code}",
                    error_code="SEARCH_FAILED",
                    details={"status_code": response.status_code},
                )

        except requests.exceptions.RequestException as e:
            raise ServiceError(
                f"Network error clearing agent memory: {str(e)}",
                error_code="NETWORK_ERROR",
                details={"error": str(e)},
            )

    def health_check(self) -> Dict[str, Any]:
        """Check if Supermemory service is healthy"""
        try:
            response = self.get(f"{self.base_url}/api/health", headers=self.headers, timeout=5)

            if response.status_code == 200:
                return {
                    "status": "healthy",
                    "service": "supermemory",
                    "response_time": response.elapsed.total_seconds(),
                }
            else:
                return {
                    "status": "unhealthy",
                    "service": "supermemory",
                    "error": f"HTTP {response.status_code}",
                }

        except Exception as e:
            return {"status": "unhealthy", "service": "supermemory", "error": str(e)}
