"""Model router: decides which tier handles each request.

Gemini/cloud is optional. If no API key is configured, cloud + vision are
disabled and every non-fast request stays on the local smart model. Smart
model failures raise instead of falling back to cloud.
"""
from __future__ import annotations

from kira.types import ModelTier


class ModelRouter:
    def __init__(self, config, ollama_client, gemini_client):
        self.config = config
        self.ollama = ollama_client
        # gemini_client is None when GEMINI_API_KEY is not set.
        self.gemini = gemini_client

    @property
    def cloud_available(self) -> bool:
        return self.gemini is not None

    async def route(self, request: str, context: dict) -> ModelTier:
        if context.get("has_image"):
            # Vision needs cloud; if it's not there we still answer with smart.
            return ModelTier.VISION if self.cloud_available else ModelTier.SMART
        if context.get("force_cloud") and self.cloud_available:
            return ModelTier.CLOUD

        classification = await self.classify_complexity(request)
        if classification == "simple":
            return ModelTier.FAST
        if classification == "complex":
            return ModelTier.CLOUD if self.cloud_available else ModelTier.SMART
        return ModelTier.SMART

    async def classify_complexity(self, request: str) -> str:
        prompt = f"""Classify this request as 'simple' or 'moderate' or 'complex'.

simple = yes/no question, status check, simple fact lookup, greeting, time/date
moderate = conversation, explanation, code review, summarization, analysis
complex = multi-step research, large document analysis, complex coding, creative writing

Request: {request}

Respond with ONLY one word: simple, moderate, or complex."""
        try:
            response = await self.ollama.generate(
                model=self.config.models.fast.model,
                prompt=prompt,
                options={"temperature": 0.1},
            )
        except Exception:
            return "moderate"

        result = response.strip().lower().split()[0] if response.strip() else "moderate"
        if result not in ("simple", "moderate", "complex"):
            return "moderate"
        return result

    async def generate(self, tier: ModelTier, messages: list[dict], **kwargs) -> str:
        # If the caller asked for a cloud tier but cloud is unavailable, fall
        # back to the local smart model transparently.
        if tier in (ModelTier.CLOUD, ModelTier.VISION) and not self.cloud_available:
            tier = ModelTier.SMART

        if tier == ModelTier.FAST:
            return await self.ollama.chat(
                model=self.config.models.fast.model, messages=messages, **kwargs
            )
        if tier == ModelTier.SMART:
            try:
                return await self.ollama.chat(
                    model=self.config.models.smart.model, messages=messages, **kwargs
                )
            except Exception:
                if self.cloud_available and self.config.models.smart.fallback_to_cloud:
                    return await self.gemini.chat(messages=messages, **kwargs)
                raise
        if tier in (ModelTier.CLOUD, ModelTier.VISION):
            return await self.gemini.chat(messages=messages, **kwargs)
        raise ValueError(f"Unknown model tier: {tier}")
