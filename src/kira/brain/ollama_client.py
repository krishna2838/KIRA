"""Async Ollama HTTP client."""
from __future__ import annotations

import httpx


class OllamaClient:
    def __init__(self, base_url: str = "http://localhost:11434", timeout: float = 300.0):
        # 300s default: cold-loading a multi-GB model on first request can
        # take well over a minute on an M4; don't time out mid-load.
        self.base_url = base_url
        self.client = httpx.AsyncClient(base_url=base_url, timeout=timeout)

    async def chat(self, model: str, messages: list[dict], **kwargs) -> str:
        response = await self.client.post(
            "/api/chat",
            json={"model": model, "messages": messages, "stream": False, **kwargs},
        )
        response.raise_for_status()
        return response.json()["message"]["content"]

    async def generate(self, model: str, prompt: str, **kwargs) -> str:
        response = await self.client.post(
            "/api/generate",
            json={"model": model, "prompt": prompt, "stream": False, **kwargs},
        )
        response.raise_for_status()
        return response.json()["response"]

    async def embed(self, model: str, text: str) -> list[float]:
        response = await self.client.post(
            "/api/embed", json={"model": model, "input": text}
        )
        response.raise_for_status()
        data = response.json()
        embeddings = data.get("embeddings") or [data.get("embedding")]
        return embeddings[0]

    async def health(self) -> bool:
        try:
            response = await self.client.get("/api/tags")
            return response.status_code == 200
        except Exception:
            return False

    async def list_models(self) -> list[str]:
        response = await self.client.get("/api/tags")
        response.raise_for_status()
        return [m["name"] for m in response.json().get("models", [])]

    async def close(self) -> None:
        await self.client.aclose()
