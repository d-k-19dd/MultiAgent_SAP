import json
import os
from pydantic import BaseModel
from typing import Dict, Any, Type, Optional
from synthetic_tooluse.config import USE_MOCK_LLM

# Simple optional import for real LLM, safely ignored if unused.
try:
    from litellm import completion
except ImportError:
    completion = None

class BaseAgent:
    """Base LLM orchestrator handling either real or mock API calls."""
    
    def __init__(self, model: str = "gpt-4o-mini", temperature: float = 0.7):
        self.model = model
        self.temperature = temperature
        
    def _fallback_mock(self, messages: list, response_format: Optional[Type[BaseModel]] = None) -> Any:
        """Deterministic mock logic for tests when LLM fails or keys are absent."""
        
        # We try to infer a sensible response based on the latest user message
        last_user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        
        if response_format:
            dummy_data = {}
            for field_name, field_info in response_format.model_fields.items():
                annotation_str = str(field_info.annotation).lower()
                if "list" in annotation_str:
                    dummy_data[field_name] = []
                elif "dict" in annotation_str:
                    dummy_data[field_name] = {}
                elif "int" in annotation_str:
                    dummy_data[field_name] = 1
                elif "float" in annotation_str:
                    dummy_data[field_name] = 4.0
                elif "str" in annotation_str:
                    dummy_data[field_name] = "dummy_string"
                else:
                    dummy_data[field_name] = None
            return response_format(**dummy_data)
        else:
            return "Mock response generated due to USE_MOCK_LLM."

    def __call__(self, messages: list, response_format: Optional[Type[BaseModel]] = None) -> Any:
        if USE_MOCK_LLM or completion is None:
            return self._fallback_mock(messages, response_format)
            
        # Using real generation via litellm
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature
        }
        
        if response_format:
            # We assume OpenAI-compatible structured output
            kwargs["response_format"] = response_format
            
        try:
            response = completion(**kwargs)
            content = response.choices[0].message.content
            if response_format:
                return response_format.model_validate_json(content)
            return content
        except Exception as e:
            print(f"LLM Call Failed: {e}. Falling back to mock.")
            return self._fallback_mock(messages, response_format)
