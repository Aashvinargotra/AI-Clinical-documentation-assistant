"""Multi-Provider LLM Key Rotation & Failover System.

Supports automatic failover across Groq, NVIDIA NIM, OpenRouter, Google Gemini, and OpenAI.
If one provider encounters a rate limit (HTTP 429), quota exhaustion, or connection error,
the rotation manager seamlessly switches to the next configured provider.
"""

import os
import time
import logging
from typing import List, Dict, Any, Optional, Type
from pydantic import BaseModel
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI
from langchain_core.runnables import Runnable

load_dotenv()

logger = logging.getLogger("llm_provider_rotator")

# Define provider configurations utilizing OpenAI-compatible REST endpoints
PROVIDER_CONFIGS = {
    "groq": {
        "name": "Groq",
        "base_url": "https://api.groq.com/openai/v1",
        "default_model": "llama-3.3-70b-versatile",
        "api_key_env": "GROQ_API_KEY"
    },
    "nvidia": {
        "name": "NVIDIA NIM",
        "base_url": "https://integrate.api.nvidia.com/v1",
        "default_model": "meta/llama-3.3-70b-instruct",
        "api_key_env": "NVIDIA_API_KEY"
    },
    "openrouter": {
        "name": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "default_model": "meta-llama/llama-3.3-70b-instruct",
        "api_key_env": "OPENROUTER_API_KEY"
    },
    "gemini": {
        "name": "Google Gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "default_model": "gemini-2.0-flash",
        "api_key_env": "GEMINI_API_KEY"
    },
    "openai": {
        "name": "OpenAI",
        "base_url": None,
        "default_model": "gpt-4o-mini",
        "api_key_env": "OPENAI_API_KEY"
    }
}


class LLMRotationManager:
    """Manages multi-provider LLM initialization, key rotation, and automatic failover."""

    def __init__(self, provider_order: Optional[List[str]] = None):
        if provider_order is None:
            order_str = os.getenv("LLM_PROVIDER_ORDER", "groq,nvidia,openrouter,gemini,openai")
            provider_order = [p.strip().lower() for p in order_str.split(",") if p.strip()]

        self.provider_order = provider_order
        self.cooldown_period_seconds = 300  # 5 minute cooldown for rate-limited providers
        self.failed_providers: Dict[str, float] = {}

    def _get_active_provider_keys(self) -> List[str]:
        """Filter provider order by availability of non-placeholder API keys."""
        valid_providers = []
        for provider_id in self.provider_order:
            if provider_id not in PROVIDER_CONFIGS:
                continue
            config = PROVIDER_CONFIGS[provider_id]
            key_val = os.getenv(config["api_key_env"], "").strip()
            
            # Check if key is present and not a dummy placeholder
            if key_val and not key_val.startswith("your-"):
                # Check cooldown
                if provider_id in self.failed_providers:
                    if time.time() - self.failed_providers[provider_id] < self.cooldown_period_seconds:
                        continue  # Still in cooldown
                    else:
                        del self.failed_providers[provider_id]  # Cooldown expired
                valid_providers.append(provider_id)
                
        return valid_providers

    def get_llm_instance(self, provider_id: str, temperature: float = 0.0) -> ChatOpenAI:
        """Instantiate ChatOpenAI client for a specific provider."""
        config = PROVIDER_CONFIGS[provider_id]
        api_key = os.getenv(config["api_key_env"])
        
        kwargs = {
            "model": config["default_model"],
            "temperature": temperature,
            "api_key": api_key,
        }
        if config["base_url"]:
            kwargs["base_url"] = config["base_url"]
            
        return ChatOpenAI(**kwargs)

    def invoke_structured_chain_with_failover(
        self,
        prompt_template: Any,
        input_data: Dict[str, Any],
        schema_model: Type[BaseModel],
        temperature: float = 0.0
    ) -> Any:
        """Execute chain with automatic provider failover if quota/rate-limit error occurs."""
        active_providers = self._get_active_provider_keys()
        
        if not active_providers:
            raise RuntimeError("No valid, active LLM provider keys found in environment.")

        last_exception = None

        for provider_id in active_providers:
            provider_name = PROVIDER_CONFIGS[provider_id]["name"]
            try:
                logger.info(f"Attempting execution using LLM Provider: {provider_name}")
                llm = self.get_llm_instance(provider_id, temperature=temperature)
                try:
                    structured_llm = llm.with_structured_output(schema_model)
                    chain = prompt_template | structured_llm
                    result = chain.invoke(input_data)
                except Exception as inner_exc:
                    if "json_schema" in str(inner_exc).lower() or "400" in str(inner_exc):
                        logger.info(f"Retrying provider {provider_name} using method='json_mode'...")
                        structured_llm = llm.with_structured_output(schema_model, method="json_mode")
                        chain = prompt_template | structured_llm
                        result = chain.invoke(input_data)
                    else:
                        raise inner_exc

                logger.info(f"Successfully executed chain with provider: {provider_name}")
                return result

            except Exception as exc:
                error_msg = str(exc).lower()
                logger.warning(f"Provider {provider_name} failed with error: {exc}")
                
                # If rate limit (429), quota exhausted, auth error, or model/schema incompatibility, mark provider in cooldown and failover
                if any(term in error_msg for term in ["429", "400", "404", "rate limit", "quota", "exceeded", "401", "unauthorized", "invalid_api_key", "does not support", "json_schema"]):
                    self.failed_providers[provider_id] = time.time()
                    logger.warning(f"Marking provider '{provider_name}' in 5-minute cooldown. Failing over to next provider...")
                
                last_exception = exc

        raise RuntimeError(f"All configured LLM providers failed. Last error: {last_exception}") from last_exception


# Global singleton instance for easy import across agent nodes
llm_rotator = LLMRotationManager()
