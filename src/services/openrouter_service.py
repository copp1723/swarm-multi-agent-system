"""
OpenRouter service for AI model interactions with streaming support
Robust implementation with proper error handling and model management
"""

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Generator, Iterator
import requests

from src.config_flexible import get_config
from src.exceptions import ModelError, ValidationError
from src.services.base_service import BaseService, handle_service_errors

logger = logging.getLogger(__name__)


@dataclass
class ModelInfo:
    """Information about an available AI model"""

    id: str
    name: str
    description: str
    context_length: int
    pricing: Dict[str, str]

    @classmethod
    def from_api_response(cls, data: Dict[str, Any]) -> "ModelInfo":
        """Create ModelInfo from API response"""
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            description=data.get("description", ""),
            context_length=data.get("context_length", 0),
            pricing=data.get("pricing", {}),
        )


@dataclass
class ChatMessage:
    """Represents a chat message"""

    role: str  # 'system', 'user', 'assistant'
    content: str

    def to_dict(self) -> Dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass
class ChatResponse:
    """Response from chat completion"""

    content: str
    model: str
    usage: Optional[Dict[str, Any]] = None


class OpenRouterService(BaseService):
    """Service for interacting with OpenRouter API with streaming support"""

    def __init__(self):
        super().__init__("OpenRouter")
        # Get flexible configuration
        config = get_config()
        self.base_url = "https://openrouter.ai/api/v1"
        self.headers = {
            "Authorization": f"Bearer {config.api.openrouter_api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://swarm-agents.local",
            "X-Title": "Swarm Multi-Agent System",
        }
        self._models_cache = None
        self._cache_timestamp = 0
        self.cache_duration = 300  # 5 minutes

    @handle_service_errors
    def get_available_models(self) -> List[ModelInfo]:
        """Get list of available models with caching"""
        import time

        # Check cache
        current_time = time.time()
        if (
            self._models_cache is not None
            and current_time - self._cache_timestamp < self.cache_duration
        ):
            logger.info("Returning cached models")
            return self._models_cache

        logger.info("Fetching models from OpenRouter API")

        try:
            response = self.get(f"{self.base_url}/models", headers=self.headers)
            data = response.json()

            if "data" not in data:
                raise ModelError(
                    "Invalid response format from OpenRouter models API",
                    error_code="INVALID_RESPONSE",
                    details={"response": data},
                )

            models = []
            for model_data in data["data"]:
                try:
                    model = ModelInfo.from_api_response(model_data)
                    models.append(model)
                except Exception as e:
                    logger.warning(f"Failed to parse model data: {e}")
                    continue

            # Cache the results
            self._models_cache = models
            self._cache_timestamp = current_time

            logger.info(f"Successfully fetched {len(models)} models")
            return models

        except json.JSONDecodeError as e:
            raise ModelError(
                "Failed to parse models response",
                error_code="JSON_DECODE_ERROR",
                details={"error": str(e)},
            )

    @handle_service_errors
    def chat_completion(
        self, messages: List[ChatMessage], model: str = "openai/gpt-4o"
    ) -> ChatResponse:
        """Get chat completion from specified model"""

        # Validate inputs
        if not messages:
            raise ValidationError("Messages list cannot be empty")

        if not model:
            raise ValidationError("Model must be specified")

        # Validate message format
        for i, msg in enumerate(messages):
            if not isinstance(msg, ChatMessage):
                raise ValidationError(f"Message {i} must be a ChatMessage instance")
            if msg.role not in ["system", "user", "assistant"]:
                raise ValidationError(f"Invalid role '{msg.role}' in message {i}")
            if not msg.content.strip():
                raise ValidationError(f"Message {i} content cannot be empty")

        logger.info(f"Making chat completion request with model {model}")

        payload = {
            "model": model,
            "messages": [msg.to_dict() for msg in messages],
            "temperature": 0.7,
            "max_tokens": 2000,
            "stream": False,
        }

        try:
            response = self.post(
                f"{self.base_url}/chat/completions", headers=self.headers, json=payload
            )

            data = response.json()

            # Validate response structure
            if "choices" not in data or not data["choices"]:
                raise ModelError(
                    "No choices in response", error_code="NO_CHOICES", details={"response": data}
                )

            choice = data["choices"][0]
            if "message" not in choice or "content" not in choice["message"]:
                raise ModelError(
                    "Invalid choice structure",
                    error_code="INVALID_CHOICE",
                    details={"choice": choice},
                )

            content = choice["message"]["content"]
            if not content:
                raise ModelError("Empty response content", error_code="EMPTY_CONTENT")

            return ChatResponse(content=content, model=model, usage=data.get("usage"))

        except json.JSONDecodeError as e:
            raise ModelError(
                "Failed to parse chat completion response",
                error_code="JSON_DECODE_ERROR",
                details={"error": str(e)},
            )

    @handle_service_errors
    def stream_chat_completion(
        self, messages: List[Dict[str, str]], model: str = "openai/gpt-4o"
    ) -> Generator[Dict[str, Any], None, None]:
        """Stream chat completion from specified model"""

        # Validate inputs
        if not messages:
            raise ValidationError("Messages list cannot be empty")

        if not model:
            raise ValidationError("Model must be specified")

        # Validate message format
        for i, msg in enumerate(messages):
            if not isinstance(msg, dict):
                raise ValidationError(f"Message {i} must be a dictionary")
            if "role" not in msg or "content" not in msg:
                raise ValidationError(f"Message {i} must have 'role' and 'content' keys")
            if msg["role"] not in ["system", "user", "assistant"]:
                raise ValidationError(f"Invalid role '{msg['role']}' in message {i}")
            if not msg["content"].strip():
                raise ValidationError(f"Message {i} content cannot be empty")

        logger.info(f"Making streaming chat completion request with model {model}")

        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 2000,
            "stream": True,
        }

        try:
            # Use requests directly for streaming
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=self.headers,
                json=payload,
                stream=True,
                timeout=30
            )
            
            response.raise_for_status()

            # Process streaming response
            for line in response.iter_lines():
                if line:
                    line = line.decode('utf-8')
                    
                    # Skip empty lines and comments
                    if not line.strip() or line.startswith('#'):
                        continue
                    
                    # Handle SSE format
                    if line.startswith('data: '):
                        data_str = line[6:]  # Remove 'data: ' prefix
                        
                        # Check for end of stream
                        if data_str.strip() == '[DONE]':
                            break
                        
                        try:
                            chunk = json.loads(data_str)
                            yield chunk
                        except json.JSONDecodeError as e:
                            logger.warning(f"Failed to parse streaming chunk: {e}")
                            continue

        except requests.exceptions.RequestException as e:
            raise ModelError(
                "Failed to make streaming request",
                error_code="STREAMING_REQUEST_ERROR",
                details={"error": str(e)},
            )
        except Exception as e:
            raise ModelError(
                "Unexpected error during streaming",
                error_code="STREAMING_ERROR",
                details={"error": str(e)},
            )

    @handle_service_errors
    def chat_completion_with_messages(
        self, messages: List[Dict[str, str]], model: str = "openai/gpt-4o", stream: bool = False
    ) -> ChatResponse:
        """Get chat completion with raw message format"""

        # Validate inputs
        if not messages:
            raise ValidationError("Messages list cannot be empty")

        if not model:
            raise ValidationError("Model must be specified")

        # If streaming is requested, use streaming method
        if stream:
            full_content = ""
            for chunk in self.stream_chat_completion(messages, model):
                if chunk and 'choices' in chunk and len(chunk['choices']) > 0:
                    delta = chunk['choices'][0].get('delta', {})
                    content = delta.get('content', '')
                    if content:
                        full_content += content
            
            return ChatResponse(content=full_content, model=model)

        # Convert to ChatMessage objects for regular completion
        chat_messages = []
        for msg in messages:
            chat_messages.append(ChatMessage(role=msg["role"], content=msg["content"]))

        return self.chat_completion(chat_messages, model)

    @handle_service_errors
    def get_model_info(self, model_id: str) -> Optional[ModelInfo]:
        """Get information about a specific model"""
        models = self.get_available_models()
        for model in models:
            if model.id == model_id:
                return model
        return None

    def is_model_available(self, model_id: str) -> bool:
        """Check if a model is available"""
        return self.get_model_info(model_id) is not None

    def get_popular_models(self) -> List[str]:
        """Get list of popular model IDs for quick access"""
        return [
            "openai/gpt-4o",
            "anthropic/claude-3.5-sonnet",
            "deepseek/deepseek-chat",
            "google/gemini-pro",
            "openai/gpt-4o-mini",
            "meta-llama/llama-3.1-70b-instruct",
            "mistralai/mistral-large",
            "cohere/command-r-plus"
        ]

