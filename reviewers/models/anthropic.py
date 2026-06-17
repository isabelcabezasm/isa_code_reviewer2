from __future__ import annotations

import os
from typing import Any

import httpx


class AnthropicClient:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str = 'https://api.anthropic.com/v1',
        timeout: float = 60.0,
    ) -> None:
        self._api_key = api_key or os.getenv('ANTHROPIC_API_KEY')
        self._base_url = base_url.rstrip('/')
        self._timeout = timeout
        if not self._api_key:
            raise ValueError('ANTHROPIC_API_KEY is required for the Anthropic model client.')

    async def review(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
    ) -> str:
        payload = {
            'model': model,
            'system': system_prompt,
            'temperature': temperature,
            'max_tokens': 2048,
            'messages': [{'role': 'user', 'content': user_prompt}],
        }
        headers = {
            'x-api-key': self._api_key,
            'anthropic-version': '2023-06-01',
            'content-type': 'application/json',
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(f'{self._base_url}/messages', headers=headers, json=payload)
            response.raise_for_status()
        data = response.json()
        return self._extract_content(data)

    def _extract_content(self, payload: dict[str, Any]) -> str:
        content = payload.get('content')
        if not isinstance(content, list) or not content:
            raise ValueError('Anthropic response did not contain content.')
        text_parts = [item.get('text', '') for item in content if isinstance(item, dict)]
        joined = ''.join(text_parts).strip()
        if not joined:
            raise ValueError('Anthropic response did not contain text content.')
        return joined
