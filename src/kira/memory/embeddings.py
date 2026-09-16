"""Embedding generation via Ollama."""
from __future__ import annotations


class EmbeddingEngine:
    def __init__(self, ollama_client, model: str = "nomic-embed-text"):
        self.ollama = ollama_client
        self.model = model

    async def embed(self, text: str) -> list[float]:
        return await self.ollama.embed(self.model, text)

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [await self.embed(t) for t in texts]
