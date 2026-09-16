"""Async Google Gemini client."""
from __future__ import annotations

import httpx


class GeminiClient:
    def __init__(self, api_key: str, model: str = "gemini-2.0-flash"):
        self.api_key = api_key
        self.model = model
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"
        self.client = httpx.AsyncClient(timeout=120.0)

    async def chat(self, messages: list[dict], **kwargs) -> str:
        contents = []
        for msg in messages:
            if msg["role"] == "system":
                continue
            role = "user" if msg["role"] == "user" else "model"
            contents.append({"role": role, "parts": [{"text": msg["content"]}]})

        system_msg = next(
            (m["content"] for m in messages if m["role"] == "system"), None
        )

        body: dict = {
            "contents": contents,
            "generationConfig": {
                "temperature": kwargs.get("temperature", 0.7),
                "maxOutputTokens": kwargs.get("max_tokens", 4096),
            },
        }
        if system_msg:
            body["system_instruction"] = {"parts": [{"text": system_msg}]}

        url = f"{self.base_url}/models/{self.model}:generateContent?key={self.api_key}"
        response = await self.client.post(url, json=body)
        response.raise_for_status()
        data = response.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]

    async def close(self) -> None:
        await self.client.aclose()
