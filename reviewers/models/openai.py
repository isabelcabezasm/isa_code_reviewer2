from __future__ import annotations

import os
from typing import Any

import httpx


class OpenAIClient:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str = 'https://api.openai.com/v1',
        timeout: float = 60.0,
    ) -> None:
        self._api_key = api_key or os.getenv('OPENAI_API_KEY')
        self._base_url = base_url.rstrip('/')
        self._timeout = timeout
        if not self._api_key:
            raise ValueError('OPENAI_API_KEY is required for the OpenAI model client.')

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
            'temperature': temperature,
            'messages': [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt},
            ],
        }
        headers = {
            'Authorization': f'Bearer {self._api_key}',
            'Content-Type': 'application/json',
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(f'{self._base_url}/chat/completions', headers=headers, json=payload)
            response.raise_for_status()
        data = response.json()
        return self._extract_content(data)

    def _extract_content(self, payload: dict[str, Any]) -> str:
        choices = payload.get('choices')
        if not isinstance(choices, list) or not choices:
            raise ValueError('OpenAI response did not contain choices.')
        message = choices[0].get('message', {})
        content = message.get('content')
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            text_parts = [item.get('text', '') for item in content if isinstance(item, dict)]
            return ''.join(text_parts).strip()
        raise ValueError('OpenAI response did not contain message content.')
