"""
OpenRouter service for AI model interactions
Robust implementation with proper error handling and model management
"""

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from src.config import config
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
    """Service for interacting with OpenRouter API"""

    def __init__(self):
        super().__init__("OpenRouter")
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
