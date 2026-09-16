"""Intent classifier (uses the fast model)."""
from __future__ import annotations


VALID_INTENTS = {
    "greeting",
    "question",
    "command",
    "conversation",
    "memory_query",
    "meta",
}


class IntentClassifier:
    INTENT_PROMPT = """You are an intent classifier for a personal AI assistant named KIRA.
Classify the user's message into exactly ONE category.

Categories:
- greeting: hello, hi, hey
- question: asking for information or explanation
- command: requesting an action be performed
- conversation: continuing an ongoing discussion
- memory_query: asking about past conversations, preferences, or stored knowledge
- meta: questions about the assistant itself

Message: {message}

Respond with ONLY the category name."""

    def __init__(self, ollama_client, model: str):
        self.ollama = ollama_client
        self.model = model

    async def classify(self, message: str) -> str:
        try:
            response = await self.ollama.generate(
                model=self.model,
                prompt=self.INTENT_PROMPT.format(message=message),
                options={"temperature": 0.1},
            )
        except Exception:
            return "conversation"
        intent = response.strip().lower().split()[0] if response.strip() else ""
        intent = intent.strip(".,!?:")
        return intent if intent in VALID_INTENTS else "conversation"
