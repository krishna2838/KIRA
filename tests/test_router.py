import asyncio
from types import SimpleNamespace

import pytest

from kira.brain.router import ModelRouter
from kira.types import ModelTier


class FakeOllama:
    def __init__(self, complexity: str = "moderate"):
        self.complexity = complexity
        self.chat_calls: list[dict] = []

    async def generate(self, model, prompt, **kwargs):
        return self.complexity

    async def chat(self, model, messages, **kwargs):
        self.chat_calls.append({"model": model, "messages": messages})
        return f"reply-from-{model}"


class FakeGemini:
    def __init__(self):
        self.calls = 0

    async def chat(self, messages, **kwargs):
        self.calls += 1
        return "reply-from-gemini"


def _config():
    return SimpleNamespace(
        models=SimpleNamespace(
            fast=SimpleNamespace(model="fast-model"),
            smart=SimpleNamespace(model="smart-model", fallback_to_cloud=True),
            cloud=SimpleNamespace(model="cloud-model"),
        )
    )


def test_route_simple_goes_fast():
    r = ModelRouter(_config(), FakeOllama("simple"), FakeGemini())
    tier = asyncio.run(r.route("hi", {}))
    assert tier == ModelTier.FAST


def test_route_complex_goes_cloud():
    r = ModelRouter(_config(), FakeOllama("complex"), FakeGemini())
    tier = asyncio.run(r.route("deep research task", {}))
    assert tier == ModelTier.CLOUD


def test_route_moderate_goes_smart():
    r = ModelRouter(_config(), FakeOllama("moderate"), FakeGemini())
    tier = asyncio.run(r.route("explain something", {}))
    assert tier == ModelTier.SMART


def test_route_image_forces_vision():
    r = ModelRouter(_config(), FakeOllama("simple"), FakeGemini())
    tier = asyncio.run(r.route("what is this", {"has_image": True}))
    assert tier == ModelTier.VISION


def test_generate_fast_uses_fast_model():
    ollama = FakeOllama("simple")
    r = ModelRouter(_config(), ollama, FakeGemini())
    asyncio.run(r.generate(ModelTier.FAST, [{"role": "user", "content": "hi"}]))
    assert ollama.chat_calls[-1]["model"] == "fast-model"


def test_route_complex_stays_local_when_no_cloud():
    r = ModelRouter(_config(), FakeOllama("complex"), None)
    assert r.cloud_available is False
    tier = asyncio.run(r.route("deep research task", {}))
    assert tier == ModelTier.SMART


def test_route_image_falls_back_to_smart_when_no_cloud():
    r = ModelRouter(_config(), FakeOllama("moderate"), None)
    tier = asyncio.run(r.route("what is this", {"has_image": True}))
    assert tier == ModelTier.SMART


def test_generate_cloud_tier_uses_smart_when_no_cloud():
    ollama = FakeOllama("moderate")
    r = ModelRouter(_config(), ollama, None)
    asyncio.run(r.generate(ModelTier.CLOUD, [{"role": "user", "content": "hi"}]))
    assert ollama.chat_calls[-1]["model"] == "smart-model"
