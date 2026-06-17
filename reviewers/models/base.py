from __future__ import annotations

from typing import Protocol


class ModelClient(Protocol):
    async def review(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
    ) -> str: ...
