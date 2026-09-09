# Define the models to use in the agent (env-driven with LiteLLM)

import os
from dotenv import load_dotenv
from os_computer_use.showui_provider import ShowUIProvider
from os_computer_use.llm_provider import LiteLLMProvider


load_dotenv()


API_KEY = os.getenv("API_KEY", "")


def _make_grounding_provider(name: str, model: str):
    """
    Return a grounding-capable provider based on env settings.
    """
    name = (name or "").lower()
    if name in ("showui", "show_ui"):
        return ShowUIProvider()
    return LiteLLMProvider(model, api_key=API_KEY)


def _make_llm_provider(provider: str, model: str):
    """
    Return an LLM provider using LiteLLM.

    The provider parameter is optional - LiteLLM auto-detects from model name.
    You can either:
    1. Pass model with provider prefix: "anthropic/claude-3-5-sonnet-20241022"
    2. Pass standard model names: "gpt-4o", "claude-3-5-sonnet-20241022", etc.
    3. Use provider name to construct the model string
    """
    name = (provider or "").lower()

    if name and name != "openai":
        provider_prefix_map = {
            "anthropic": "anthropic",
            "fireworks": "fireworks_ai",
            "mistral": "mistral",
            "groq": "groq",
            "deepseek": "deepseek",
            "openrouter": "openrouter",
            "gemini": "gemini",
            "moonshot": "moonshot",
            "llama": "ollama",
        }

        if name in provider_prefix_map:
            prefix = provider_prefix_map[name]
            if "/" not in model:
                model = f"{prefix}/{model}"

    return LiteLLMProvider(model, api_key=API_KEY)


GROUNDING_PROVIDER = os.getenv("OCU_GROUNDING_PROVIDER", "showui")
GROUNDING_MODEL = os.getenv("OCU_GROUNDING_MODEL", "gpt-4o")

VISION_PROVIDER = os.getenv("OCU_VISION_PROVIDER", "")
VISION_MODEL = os.getenv("OCU_VISION_MODEL", "gpt-4o")

ACTION_PROVIDER = os.getenv("OCU_ACTION_PROVIDER", "")
ACTION_MODEL = os.getenv("OCU_ACTION_MODEL", "gpt-4o")

# Instantiate providers
grounding_model = _make_grounding_provider(GROUNDING_PROVIDER, GROUNDING_MODEL)
vision_model = _make_llm_provider(VISION_PROVIDER, VISION_MODEL)
action_model = _make_llm_provider(ACTION_PROVIDER, ACTION_MODEL)
