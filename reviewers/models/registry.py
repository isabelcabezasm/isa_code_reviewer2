from __future__ import annotations

from typing import Callable

from reviewers.models.anthropic import AnthropicClient
from reviewers.models.base import ModelClient
from reviewers.models.openai import OpenAIClient

MODEL_CLIENTS: dict[str, Callable[[], ModelClient]] = {
    'openai': OpenAIClient,
    'anthropic': AnthropicClient,
}


def get_model_client(provider: str) -> ModelClient:
    normalized = provider.strip().lower()
    if normalized not in MODEL_CLIENTS:
        raise ValueError(f'Unsupported model provider: {provider}')
    return MODEL_CLIENTS[normalized]()
