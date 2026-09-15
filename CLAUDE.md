# KIRA — Claude Code Build Spec
## Phase 0 (Foundation) + Phase 1 (Brain + Memory)

**Target machine:** MacBook Air M4, 16GB unified RAM, 256GB SSD (~32GB free), macOS Tahoe 26.6.2

**Project identity:** KIRA — a local-first, MCP-native, memory-centric personal AI operating system.

---

## 1. PROJECT STRUCTURE

```
kira/
├── CLAUDE.md                          # This spec — Claude Code reads this first
├── README.md
├── docker-compose.yml                 # PostgreSQL + pgvector + Redis
├── .env.example                       # Template for secrets
├── .gitignore
│
├── packages/
│   ├── core/                          # Shared types, config, utilities
│   │   ├── pyproject.toml
│   │   └── kira/
│   │       ├── __init__.py
│   │       ├── config.py              # YAML config loader + env override
│   │       ├── logger.py              # Structured JSON logging
│   │       ├── types.py               # Pydantic models (Message, Memory, Entity, etc.)
│   │       ├── redaction.py           # Auto-redaction engine
│   │       └── permissions.py         # Permission levels + risk classification
│   │
│   ├── brain/                         # LLM routing, intent, planning, verification
│   │   ├── pyproject.toml
│   │   └── kira/
│   │       └── brain/
│   │           ├── __init__.py
│   │           ├── router.py          # Model router (fast/smart/vision)
│   │           ├── ollama_client.py   # Ollama API client
│   │           ├── gemini_client.py   # Gemini API client
│   │           ├── intent.py          # Intent classifier (fast model)
│   │           ├── planner.py         # Task decomposition
│   │           ├── verifier.py        # Self-check before responding
│   │           └── prompts.py         # System prompts, templates
│   │
│   ├── memory/                        # Knowledge graph, long-term, working context
│   │   ├── pyproject.toml
│   │   └── kira/
│   │       └── memory/
│   │           ├── __init__.py
│   │           ├── graph.py           # Knowledge graph (entities + relationships)
│   │           ├── store.py           # Long-term memory CRUD + embedding search
│   │           ├── context.py         # Working context (current session)
│   │           ├── conversations.py   # Conversation history + auto-summarization
│   │           ├── embeddings.py      # Embedding generation (via Ollama)
│   │           └── db.py              # Database connection + migrations
│   │
│   ├── server/                        # FastAPI gateway
│   │   ├── pyproject.toml
│   │   └── kira/
│   │       └── server/
│   │           ├── __init__.py
│   │           ├── app.py             # FastAPI app factory
│   │           ├── routes/
│   │           │   ├── __init__.py
│   │           │   ├── chat.py        # POST /chat, GET /chat/stream (WebSocket)
│   │           │   ├── memory.py      # GET/POST/DELETE /memory/*
│   │           │   ├── health.py      # GET /health
│   │           │   └── config.py      # GET/PATCH /config
│   │           ├── middleware.py      # Rate limiting, CORS, auth
│   │           └── ws.py             # WebSocket manager
│   │
│   └── client/                        # React frontend
│       ├── package.json
│       ├── tsconfig.json
│       ├── vite.config.ts
│       ├── index.html
│       └── src/
│           ├── main.tsx
│           ├── App.tsx
│           ├── components/
│           │   ├── Chat.tsx           # Chat interface
│           │   ├── MessageBubble.tsx  # Individual message
│           │   ├── Avatar.tsx         # KIRA's face (SVG state machine)
│           │   ├── MemoryViewer.tsx   # Knowledge graph + memory browser
│           │   ├── StatusBar.tsx      # Connection status, model info
│           │   └── InputBar.tsx       # Text input + voice toggle (future)
│           ├── hooks/
│           │   ├── useWebSocket.ts    # WS connection to server
│           │   ├── useChat.ts         # Chat state management
│           │   └── useMemory.ts       # Memory queries
│           ├── stores/
│           │   └── appStore.ts        # Zustand global state
│           ├── types/
│           │   └── index.ts           # TypeScript types matching server models
│           └── styles/
│               └── globals.css        # Tailwind + CSS variables
│
├── config/
│   └── default.yaml                   # Default configuration
│
├── evals/
│   ├── README.md
│   ├── run_evals.py                   # Eval runner
│   └── cases/
│       ├── intent_classification.yaml
│       ├── memory_retrieval.yaml
│       └── routing.yaml
│
├── scripts/
│   ├── setup.sh                       # First-time setup (install deps, pull models)
│   ├── dev.sh                         # Start dev environment
│   └── migrate.py                     # Database migrations
│
└── tests/
    ├── test_router.py
    ├── test_memory.py
    ├── test_redaction.py
    └── test_permissions.py
```

---

## 2. CONFIGURATION SYSTEM

`config/default.yaml`:

```yaml
kira:
  name: "KIRA"
  version: "0.1.0"

models:
  fast:
    provider: "ollama"
    model: "gemma4:e2b"
    # Always loaded. Used for: intent classification, tool routing,
    # echo detection, quick classifications, digest passes.
    temperature: 0.3
    timeout_sec: 10

  smart:
    provider: "ollama"
    model: "gemma3:8b"
    # Loaded on demand. Used for: complex reasoning, conversation,
    # multi-step tasks, code analysis.
    temperature: 0.7
    timeout_sec: 60
    # Falls back to cloud if local model unavailable or task too complex
    fallback_to_cloud: true

  cloud:
    provider: "gemini"
    model: "gemini-2.0-flash"
    # Used when: local smart model insufficient, large documents,
    # complex research, heavy coding tasks.
    api_key: "${GEMINI_API_KEY}"
    temperature: 0.7
    timeout_sec: 120

  vision:
    provider: "gemini"
    model: "gemini-2.0-flash"
    api_key: "${GEMINI_API_KEY}"
    timeout_sec: 30

  embeddings:
    provider: "ollama"
    model: "nomic-embed-text"

database:
  postgres:
    host: "localhost"
    port: 5432
    database: "kira"
    user: "kira"
    password: "${POSTGRES_PASSWORD}"
  redis:
    host: "localhost"
    port: 6379

server:
  host: "127.0.0.1"
  port: 8750
  cors_origins: ["http://localhost:5173"]

memory:
  # Auto-summarize conversations longer than this
  auto_summarize_threshold: 20
  # Max memories to retrieve per query
  retrieval_limit: 10
  # Similarity threshold for embedding search (0-1)
  similarity_threshold: 0.7

redaction:
  # Patterns to strip before storing ANY memory
  enabled: true
  patterns:
    - type: "email"
    - type: "api_key"
    - type: "password"
    - type: "credit_card"
    - type: "ssn"
    - type: "phone"
    - type: "ip_address"
    - type: "jwt_token"
    - type: "private_key"

permissions:
  # Risk levels: 0=read, 1=personal, 2=execute, 3=external, 4=critical
  auto_approve_level: 1    # Auto-approve L0 and L1
  require_confirm_level: 2  # L2+ requires confirmation

logging:
  level: "INFO"
  format: "json"
  file: "~/.kira/logs/kira.log"
```

`packages/core/kira/config.py` should:
- Load `config/default.yaml` as base
- Override with `~/.kira/config.yaml` if it exists (user overrides)
- Override with environment variables (pattern: `KIRA_MODELS_FAST_MODEL=xyz`)
- Validate with Pydantic
- Expose a singleton `get_config()` function

---

## 3. DATABASE

`docker-compose.yml`:

```yaml
version: "3.9"
services:
  postgres:
    image: pgvector/pgvector:pg17
    environment:
      POSTGRES_DB: kira
      POSTGRES_USER: kira
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-kira_dev_password}
    ports:
      - "5432:5432"
    volumes:
      - kira_pgdata:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - kira_redis:/data

volumes:
  kira_pgdata:
  kira_redis:
```

### Database Schema (SQL migrations)

```sql
-- Enable pgvector
CREATE EXTENSION IF NOT EXISTS vector;

-- Knowledge Graph: Entities
CREATE TABLE entities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    type VARCHAR(50) NOT NULL,          -- 'person', 'project', 'topic', 'place', 'tool', 'event'
    name VARCHAR(255) NOT NULL,
    metadata JSONB DEFAULT '{}',
    embedding vector(768),              -- nomic-embed-text dimension
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_entities_type ON entities(type);
CREATE INDEX idx_entities_embedding ON entities USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Knowledge Graph: Relationships
CREATE TABLE relationships (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id UUID REFERENCES entities(id) ON DELETE CASCADE,
    target_id UUID REFERENCES entities(id) ON DELETE CASCADE,
    type VARCHAR(100) NOT NULL,         -- 'studies', 'works_on', 'member_of', 'uses', 'knows', etc.
    weight FLOAT DEFAULT 1.0,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    valid_until TIMESTAMPTZ,            -- NULL = still valid
    UNIQUE(source_id, target_id, type)
);
CREATE INDEX idx_relationships_source ON relationships(source_id);
CREATE INDEX idx_relationships_target ON relationships(target_id);

-- Long-term Memories
CREATE TABLE memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    content TEXT NOT NULL,
    category VARCHAR(50) NOT NULL,      -- 'preference', 'fact', 'decision', 'task', 'observation'
    importance FLOAT DEFAULT 0.5,       -- 0.0 to 1.0
    embedding vector(768),
    source_type VARCHAR(50) NOT NULL,   -- 'conversation', 'tool', 'manual', 'inferred'
    source_id UUID,                     -- conversation_id if from conversation
    entity_id UUID REFERENCES entities(id) ON DELETE SET NULL,  -- linked entity
    created_at TIMESTAMPTZ DEFAULT NOW(),
    accessed_at TIMESTAMPTZ DEFAULT NOW(),
    access_count INT DEFAULT 0
);
CREATE INDEX idx_memories_category ON memories(category);
CREATE INDEX idx_memories_embedding ON memories USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX idx_memories_importance ON memories(importance DESC);

-- Conversations
CREATE TABLE conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title VARCHAR(255),
    summary TEXT,                       -- Auto-generated summary
    started_at TIMESTAMPTZ DEFAULT NOW(),
    ended_at TIMESTAMPTZ,
    message_count INT DEFAULT 0
);

-- Messages
CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL,          -- 'user', 'assistant', 'system', 'tool'
    content TEXT NOT NULL,
    metadata JSONB DEFAULT '{}',        -- tool_calls, model_used, tokens, latency_ms
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_messages_conversation ON messages(conversation_id, created_at);

-- Audit Log
CREATE TABLE audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    action VARCHAR(100) NOT NULL,       -- 'tool_call', 'memory_write', 'memory_delete', etc.
    tool_name VARCHAR(100),
    risk_level INT NOT NULL,            -- 0-4
    input_summary TEXT,
    output_summary TEXT,
    approved BOOLEAN,
    approved_by VARCHAR(50),            -- 'auto', 'user'
    error TEXT,
    latency_ms INT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_audit_log_created ON audit_log(created_at DESC);
```

---

## 4. CORE PACKAGE

### `packages/core/kira/types.py`

Pydantic models for everything:

```python
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4
from typing import Optional

class Role(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"

class ModelTier(str, Enum):
    FAST = "fast"
    SMART = "smart"
    CLOUD = "cloud"
    VISION = "vision"

class RiskLevel(int, Enum):
    READ = 0
    PERSONAL = 1
    EXECUTE = 2
    EXTERNAL = 3
    CRITICAL = 4

class EntityType(str, Enum):
    PERSON = "person"
    PROJECT = "project"
    TOPIC = "topic"
    PLACE = "place"
    TOOL = "tool"
    EVENT = "event"
    ORGANIZATION = "organization"

class MemoryCategory(str, Enum):
    PREFERENCE = "preference"
    FACT = "fact"
    DECISION = "decision"
    TASK = "task"
    OBSERVATION = "observation"

class KiraState(str, Enum):
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SEARCHING = "searching"
    EXECUTING = "executing"
    SPEAKING = "speaking"
    ERROR = "error"
    SUCCESS = "success"

class Message(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    conversation_id: Optional[UUID] = None
    role: Role
    content: str
    metadata: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)

class Entity(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    type: EntityType
    name: str
    metadata: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)

class Relationship(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    source_id: UUID
    target_id: UUID
    type: str
    weight: float = 1.0
    metadata: dict = Field(default_factory=dict)

class Memory(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    content: str
    category: MemoryCategory
    importance: float = 0.5
    source_type: str = "conversation"
    entity_id: Optional[UUID] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[UUID] = None

class ChatResponse(BaseModel):
    message: Message
    conversation_id: UUID
    state: KiraState = KiraState.IDLE
    memories_used: list[UUID] = Field(default_factory=list)
    model_used: str = ""
    latency_ms: int = 0
```

### `packages/core/kira/redaction.py`

Auto-redaction engine. Runs BEFORE any memory write.

```python
import re

REDACTION_PATTERNS = {
    "email": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
    "api_key": r'(?:sk|pk|api[_-]?key)[_-]?[A-Za-z0-9]{20,}',
    "password": r'(?:password|passwd|pwd)\s*[:=]\s*\S+',
    "credit_card": r'\b(?:\d{4}[- ]?){3}\d{4}\b',
    "ssn": r'\b\d{3}-\d{2}-\d{4}\b',
    "phone": r'\b(?:\+\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b',
    "ip_address": r'\b(?:\d{1,3}\.){3}\d{1,3}\b',
    "jwt_token": r'eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}',
    "private_key": r'-----BEGIN (?:RSA |EC |DSA )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |EC |DSA )?PRIVATE KEY-----',
    "bearer_token": r'Bearer\s+[A-Za-z0-9_-]{20,}',
}

def redact(text: str, enabled_patterns: list[str] | None = None) -> str:
    """Strip sensitive patterns from text before storing."""
    if enabled_patterns is None:
        enabled_patterns = list(REDACTION_PATTERNS.keys())
    
    result = text
    for pattern_name in enabled_patterns:
        if pattern_name in REDACTION_PATTERNS:
            result = re.sub(
                REDACTION_PATTERNS[pattern_name],
                f"[REDACTED:{pattern_name.upper()}]",
                result,
                flags=re.IGNORECASE
            )
    return result
```

### `packages/core/kira/permissions.py`

```python
from kira.types import RiskLevel

class PermissionEngine:
    def __init__(self, auto_approve_level: int = 1):
        self.auto_approve_level = auto_approve_level
    
    def classify_risk(self, tool_name: str, action: str) -> RiskLevel:
        """Classify the risk level of a tool action."""
        # Read-only operations
        read_tools = {"search", "read_file", "list_files", "web_search", "get_weather"}
        if tool_name in read_tools:
            return RiskLevel.READ
        
        # Personal data access
        personal_tools = {"read_calendar", "read_notes", "read_contacts"}
        if tool_name in personal_tools:
            return RiskLevel.PERSONAL
        
        # Execution
        execute_tools = {"run_script", "modify_file", "create_file", "delete_file"}
        if tool_name in execute_tools:
            return RiskLevel.EXECUTE
        
        # External actions
        external_tools = {"send_email", "send_message", "post_content", "create_issue"}
        if tool_name in external_tools:
            return RiskLevel.EXTERNAL
        
        # Critical
        critical_tools = {"payment", "account_change", "security_change"}
        if tool_name in critical_tools:
            return RiskLevel.CRITICAL
        
        return RiskLevel.EXECUTE  # Default to execute level
    
    def needs_confirmation(self, risk_level: RiskLevel) -> bool:
        return risk_level.value > self.auto_approve_level
```

### `packages/core/kira/logger.py`

Structured JSON logging:

```python
import logging
import json
import sys
from datetime import datetime

class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "module": record.module,
            "message": record.getMessage(),
        }
        if hasattr(record, "extra_data"):
            log_entry.update(record.extra_data)
        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry)

def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(f"kira.{name}")
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger
```

---

## 5. BRAIN PACKAGE

### `packages/brain/kira/brain/router.py`

The model router decides which model handles each request.

```python
class ModelRouter:
    """Routes requests to the appropriate model tier."""
    
    def __init__(self, config, ollama_client, gemini_client):
        self.config = config
        self.ollama = ollama_client
        self.gemini = gemini_client
    
    async def route(self, request: str, context: dict) -> ModelTier:
        """Determine which model tier should handle this request.
        
        Routing logic:
        - FAST: intent classification, yes/no questions, simple lookups,
                tool routing, echo detection, status queries
        - SMART: conversation, reasoning, multi-step tasks, code review,
                 document analysis (< 4K tokens)
        - CLOUD: complex research, large documents (> 4K tokens),
                 difficult coding, multi-step planning when local fails
        - VISION: screenshot analysis, image understanding, OCR verification
        """
        # Use fast model to classify the request complexity
        classification = await self.classify_complexity(request)
        
        if classification == "simple":
            return ModelTier.FAST
        elif classification == "complex" or context.get("force_cloud"):
            return ModelTier.CLOUD
        elif context.get("has_image"):
            return ModelTier.VISION
        else:
            return ModelTier.SMART
    
    async def classify_complexity(self, request: str) -> str:
        """Use fast model to classify request complexity."""
        prompt = f"""Classify this request as 'simple' or 'moderate' or 'complex'.
        
simple = yes/no question, status check, simple fact lookup, greeting, time/date
moderate = conversation, explanation, code review, summarization, analysis
complex = multi-step research, large document analysis, complex coding, creative writing

Request: {request}

Respond with ONLY one word: simple, moderate, or complex."""
        
        response = await self.ollama.generate(
            model=self.config.models.fast.model,
            prompt=prompt,
            temperature=0.1
        )
        
        result = response.strip().lower()
        if result not in ("simple", "moderate", "complex"):
            return "moderate"
        return result
    
    async def generate(self, tier: ModelTier, messages: list[dict], **kwargs) -> str:
        """Generate a response using the specified model tier."""
        if tier == ModelTier.FAST:
            return await self.ollama.chat(
                model=self.config.models.fast.model,
                messages=messages,
                **kwargs
            )
        elif tier == ModelTier.SMART:
            try:
                return await self.ollama.chat(
                    model=self.config.models.smart.model,
                    messages=messages,
                    **kwargs
                )
            except Exception:
                if self.config.models.smart.fallback_to_cloud:
                    return await self.gemini.chat(messages=messages, **kwargs)
                raise
        elif tier == ModelTier.CLOUD:
            return await self.gemini.chat(messages=messages, **kwargs)
        elif tier == ModelTier.VISION:
            return await self.gemini.chat(messages=messages, **kwargs)
```

### `packages/brain/kira/brain/ollama_client.py`

```python
import httpx

class OllamaClient:
    """Async client for Ollama API."""
    
    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url
        self.client = httpx.AsyncClient(base_url=base_url, timeout=120.0)
    
    async def chat(self, model: str, messages: list[dict], **kwargs) -> str:
        response = await self.client.post("/api/chat", json={
            "model": model,
            "messages": messages,
            "stream": False,
            **kwargs
        })
        response.raise_for_status()
        return response.json()["message"]["content"]
    
    async def generate(self, model: str, prompt: str, **kwargs) -> str:
        response = await self.client.post("/api/generate", json={
            "model": model,
            "prompt": prompt,
            "stream": False,
            **kwargs
        })
        response.raise_for_status()
        return response.json()["response"]
    
    async def embed(self, model: str, text: str) -> list[float]:
        response = await self.client.post("/api/embed", json={
            "model": model,
            "input": text
        })
        response.raise_for_status()
        return response.json()["embeddings"][0]
    
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
```

### `packages/brain/kira/brain/gemini_client.py`

```python
import httpx

class GeminiClient:
    """Async client for Google Gemini API."""
    
    def __init__(self, api_key: str, model: str = "gemini-2.0-flash"):
        self.api_key = api_key
        self.model = model
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"
        self.client = httpx.AsyncClient(timeout=120.0)
    
    async def chat(self, messages: list[dict], **kwargs) -> str:
        # Convert OpenAI-style messages to Gemini format
        contents = []
        for msg in messages:
            role = "user" if msg["role"] == "user" else "model"
            if msg["role"] == "system":
                # Gemini handles system via system_instruction
                continue
            contents.append({
                "role": role,
                "parts": [{"text": msg["content"]}]
            })
        
        system_msg = next((m["content"] for m in messages if m["role"] == "system"), None)
        
        body = {
            "contents": contents,
            "generationConfig": {
                "temperature": kwargs.get("temperature", 0.7),
                "maxOutputTokens": kwargs.get("max_tokens", 4096),
            }
        }
        
        if system_msg:
            body["system_instruction"] = {"parts": [{"text": system_msg}]}
        
        url = f"{self.base_url}/models/{self.model}:generateContent?key={self.api_key}"
        response = await self.client.post(url, json=body)
        response.raise_for_status()
        
        data = response.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]
```

### `packages/brain/kira/brain/intent.py`

Intent classifier using the fast model:

```python
class IntentClassifier:
    """Classifies user intent using the fast model.
    
    Categories:
    - greeting: "hi", "hello", "hey kira"
    - question: asking for information
    - command: asking to do something
    - conversation: continuing a discussion
    - memory_query: asking about past conversations or stored knowledge
    - meta: questions about KIRA itself
    """
    
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
        response = await self.ollama.generate(
            model=self.model,
            prompt=self.INTENT_PROMPT.format(message=message),
            temperature=0.1
        )
        intent = response.strip().lower()
        valid = {"greeting", "question", "command", "conversation", "memory_query", "meta"}
        return intent if intent in valid else "conversation"
```

### `packages/brain/kira/brain/prompts.py`

```python
KIRA_SYSTEM_PROMPT = """You are KIRA, a personal AI assistant for Krishna.

Core traits:
- Direct and concise. No filler phrases like "How can I assist you today?"
- Warm but not sycophantic. You're a capable peer, not a servant.
- When you don't know something, say so clearly.
- When you're uncertain, express your confidence level.
- You remember past conversations and use that context naturally.

Knowledge about Krishna:
{personal_context}

Relevant memories:
{memories}

Current conversation context:
{working_context}

Guidelines:
- For simple questions, answer directly without preamble.
- For tasks, explain what you'll do, do it, then confirm.
- For uncertain information, say "I think..." or "Based on what I know..."
- Never fabricate information. If you need to search or verify, say so.
- When multiple tools could help, briefly explain why you chose one.
"""

MEMORY_EXTRACTION_PROMPT = """Extract durable facts from this conversation that are worth remembering long-term.

Rules:
- Only extract facts the USER stated (not your own responses)
- Focus on: preferences, decisions, people mentioned, projects, goals, schedules
- Skip: transient questions, greetings, things already known
- Each fact should be a single clear statement
- Tag each fact with a category: preference, fact, decision, task, observation

Conversation:
{conversation}

Return as JSON array:
[{{"content": "...", "category": "...", "importance": 0.0-1.0, "entities": ["entity_name", ...]}}]

If nothing worth remembering, return: []"""

SUMMARIZATION_PROMPT = """Summarize this conversation in 2-3 sentences. Focus on:
- What was discussed
- What decisions were made
- What actions were taken or planned

Conversation:
{conversation}

Summary:"""

ENTITY_EXTRACTION_PROMPT = """Extract named entities from this text that should be tracked in a knowledge graph.

Entity types: person, project, topic, place, tool, event, organization

Text: {text}

Return as JSON array:
[{{"name": "...", "type": "...", "relationship_to_user": "..."}}]

If no notable entities, return: []"""
```

---

## 6. MEMORY PACKAGE

### `packages/memory/kira/memory/db.py`

Database connection and migration management:

```python
import asyncpg
from kira.config import get_config
from kira.logger import get_logger

logger = get_logger("memory.db")

class Database:
    def __init__(self):
        self.pool: asyncpg.Pool | None = None
    
    async def connect(self):
        config = get_config()
        self.pool = await asyncpg.create_pool(
            host=config.database.postgres.host,
            port=config.database.postgres.port,
            database=config.database.postgres.database,
            user=config.database.postgres.user,
            password=config.database.postgres.password,
            min_size=2,
            max_size=10
        )
        logger.info("Connected to PostgreSQL")
    
    async def disconnect(self):
        if self.pool:
            await self.pool.close()
    
    async def execute(self, query: str, *args):
        async with self.pool.acquire() as conn:
            return await conn.execute(query, *args)
    
    async def fetch(self, query: str, *args):
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, *args)
    
    async def fetchrow(self, query: str, *args):
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, *args)
    
    async def fetchval(self, query: str, *args):
        async with self.pool.acquire() as conn:
            return await conn.fetchval(query, *args)

# Singleton
_db = Database()

async def get_db() -> Database:
    if _db.pool is None:
        await _db.connect()
    return _db
```

### `packages/memory/kira/memory/embeddings.py`

```python
class EmbeddingEngine:
    def __init__(self, ollama_client, model: str = "nomic-embed-text"):
        self.ollama = ollama_client
        self.model = model
    
    async def embed(self, text: str) -> list[float]:
        return await self.ollama.embed(self.model, text)
    
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [await self.embed(text) for text in texts]
```

### `packages/memory/kira/memory/graph.py`

Knowledge graph operations:

```python
class KnowledgeGraph:
    """Entity-relationship knowledge graph backed by PostgreSQL.
    
    Stores entities (people, projects, topics, etc.) and their
    relationships. Supports semantic search via pgvector embeddings.
    """
    
    def __init__(self, db: Database, embeddings: EmbeddingEngine):
        self.db = db
        self.embeddings = embeddings
    
    async def add_entity(self, entity: Entity) -> Entity:
        embedding = await self.embeddings.embed(f"{entity.type}: {entity.name}")
        await self.db.execute(
            """INSERT INTO entities (id, type, name, metadata, embedding)
               VALUES ($1, $2, $3, $4, $5)
               ON CONFLICT (id) DO UPDATE SET
                 name = EXCLUDED.name,
                 metadata = EXCLUDED.metadata,
                 embedding = EXCLUDED.embedding,
                 updated_at = NOW()""",
            entity.id, entity.type.value, entity.name,
            json.dumps(entity.metadata), embedding
        )
        return entity
    
    async def add_relationship(self, rel: Relationship) -> Relationship:
        await self.db.execute(
            """INSERT INTO relationships (id, source_id, target_id, type, weight, metadata)
               VALUES ($1, $2, $3, $4, $5, $6)
               ON CONFLICT (source_id, target_id, type) DO UPDATE SET
                 weight = EXCLUDED.weight,
                 metadata = EXCLUDED.metadata""",
            rel.id, rel.source_id, rel.target_id, rel.type, rel.weight,
            json.dumps(rel.metadata)
        )
        return rel
    
    async def get_entity(self, name: str) -> Entity | None:
        row = await self.db.fetchrow(
            "SELECT * FROM entities WHERE LOWER(name) = LOWER($1)", name
        )
        if row:
            return Entity(**dict(row))
        return None
    
    async def get_related(self, entity_id: UUID, depth: int = 1) -> list[dict]:
        """Get entities related to a given entity, up to N hops."""
        rows = await self.db.fetch(
            """SELECT e.*, r.type as rel_type, r.weight
               FROM relationships r
               JOIN entities e ON (e.id = r.target_id OR e.id = r.source_id)
               WHERE (r.source_id = $1 OR r.target_id = $1)
                 AND e.id != $1
                 AND r.valid_until IS NULL""",
            entity_id
        )
        return [dict(row) for row in rows]
    
    async def search_entities(self, query: str, limit: int = 10) -> list[Entity]:
        """Semantic search for entities."""
        embedding = await self.embeddings.embed(query)
        rows = await self.db.fetch(
            """SELECT *, embedding <=> $1::vector AS distance
               FROM entities
               ORDER BY distance ASC
               LIMIT $2""",
            embedding, limit
        )
        return [Entity(**dict(row)) for row in rows]
    
    async def build_context_for(self, query: str) -> str:
        """Build a natural language context string from relevant graph data."""
        entities = await self.search_entities(query, limit=5)
        if not entities:
            return ""
        
        context_parts = []
        for entity in entities:
            related = await self.get_related(entity.id)
            relations_str = ", ".join(
                f"{r['rel_type']} {r['name']}" for r in related[:5]
            )
            if relations_str:
                context_parts.append(f"{entity.name} ({entity.type.value}): {relations_str}")
            else:
                context_parts.append(f"{entity.name} ({entity.type.value})")
        
        return "\n".join(context_parts)
```

### `packages/memory/kira/memory/store.py`

Long-term memory storage with semantic search:

```python
class MemoryStore:
    """Long-term memory storage with semantic search.
    
    Stores facts, preferences, decisions, and observations.
    All writes pass through redaction before storage.
    """
    
    def __init__(self, db: Database, embeddings: EmbeddingEngine):
        self.db = db
        self.embeddings = embeddings
    
    async def store(self, memory: Memory) -> Memory:
        """Store a new memory, redacting sensitive content first."""
        from kira.redaction import redact
        clean_content = redact(memory.content)
        embedding = await self.embeddings.embed(clean_content)
        
        await self.db.execute(
            """INSERT INTO memories (id, content, category, importance, embedding,
                                     source_type, source_id, entity_id)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8)""",
            memory.id, clean_content, memory.category.value, memory.importance,
            embedding, memory.source_type, memory.source_id, memory.entity_id
        )
        return memory
    
    async def search(self, query: str, limit: int = 10, 
                     category: str | None = None,
                     min_importance: float = 0.0) -> list[Memory]:
        """Semantic search over memories."""
        embedding = await self.embeddings.embed(query)
        
        base_query = """
            SELECT *, embedding <=> $1::vector AS distance
            FROM memories
            WHERE importance >= $2
        """
        args = [embedding, min_importance]
        
        if category:
            base_query += f" AND category = ${len(args) + 1}"
            args.append(category)
        
        base_query += f" ORDER BY distance ASC LIMIT ${len(args) + 1}"
        args.append(limit)
        
        rows = await self.db.fetch(base_query, *args)
        
        # Update access tracking
        for row in rows:
            await self.db.execute(
                "UPDATE memories SET accessed_at = NOW(), access_count = access_count + 1 WHERE id = $1",
                row["id"]
            )
        
        return [Memory(**dict(row)) for row in rows]
    
    async def get_all(self, limit: int = 100, offset: int = 0) -> list[Memory]:
        rows = await self.db.fetch(
            "SELECT * FROM memories ORDER BY created_at DESC LIMIT $1 OFFSET $2",
            limit, offset
        )
        return [Memory(**dict(row)) for row in rows]
    
    async def delete(self, memory_id: UUID) -> bool:
        result = await self.db.execute(
            "DELETE FROM memories WHERE id = $1", memory_id
        )
        return result == "DELETE 1"
```

### `packages/memory/kira/memory/conversations.py`

```python
class ConversationManager:
    """Manages conversation history and auto-summarization."""
    
    def __init__(self, db: Database, ollama_client, model: str, 
                 summarize_threshold: int = 20):
        self.db = db
        self.ollama = ollama_client
        self.model = model
        self.summarize_threshold = summarize_threshold
    
    async def create_conversation(self) -> UUID:
        conv_id = uuid4()
        await self.db.execute(
            "INSERT INTO conversations (id) VALUES ($1)", conv_id
        )
        return conv_id
    
    async def add_message(self, conversation_id: UUID, message: Message) -> Message:
        await self.db.execute(
            """INSERT INTO messages (id, conversation_id, role, content, metadata)
               VALUES ($1, $2, $3, $4, $5)""",
            message.id, conversation_id, message.role.value, 
            message.content, json.dumps(message.metadata)
        )
        await self.db.execute(
            "UPDATE conversations SET message_count = message_count + 1 WHERE id = $1",
            conversation_id
        )
        
        # Check if we should auto-summarize
        count = await self.db.fetchval(
            "SELECT message_count FROM conversations WHERE id = $1",
            conversation_id
        )
        if count and count >= self.summarize_threshold:
            await self._auto_summarize(conversation_id)
        
        return message
    
    async def get_messages(self, conversation_id: UUID, 
                           limit: int = 50) -> list[Message]:
        rows = await self.db.fetch(
            """SELECT * FROM messages 
               WHERE conversation_id = $1 
               ORDER BY created_at ASC 
               LIMIT $2""",
            conversation_id, limit
        )
        return [Message(**dict(row)) for row in rows]
    
    async def get_recent_context(self, conversation_id: UUID, 
                                  max_messages: int = 10) -> list[dict]:
        """Get recent messages formatted for LLM context."""
        messages = await self.get_messages(conversation_id, limit=max_messages)
        return [
            {"role": m.role.value, "content": m.content}
            for m in messages
        ]
    
    async def _auto_summarize(self, conversation_id: UUID):
        """Generate a summary of the conversation."""
        messages = await self.get_messages(conversation_id, limit=100)
        conversation_text = "\n".join(
            f"{m.role.value}: {m.content}" for m in messages
        )
        
        from kira.brain.prompts import SUMMARIZATION_PROMPT
        summary = await self.ollama.generate(
            model=self.model,
            prompt=SUMMARIZATION_PROMPT.format(conversation=conversation_text),
            temperature=0.3
        )
        
        await self.db.execute(
            "UPDATE conversations SET summary = $1 WHERE id = $2",
            summary.strip(), conversation_id
        )
```

### `packages/memory/kira/memory/context.py`

Working context (current session state):

```python
class WorkingContext:
    """Maintains the current session's working context.
    
    This is short-term memory: what's happening RIGHT NOW.
    It doesn't persist to the database — it lives in RAM
    and dies when the session ends.
    """
    
    def __init__(self):
        self.current_conversation_id: UUID | None = None
        self.current_topic: str | None = None
        self.recent_entities: list[str] = []  # Last N mentioned entities
        self.recent_tools_used: list[str] = []
        self.session_facts: list[str] = []  # Facts learned this session
        self.state: KiraState = KiraState.IDLE
    
    def update_topic(self, topic: str):
        self.current_topic = topic
    
    def add_entity(self, name: str):
        if name not in self.recent_entities:
            self.recent_entities.append(name)
            if len(self.recent_entities) > 20:
                self.recent_entities.pop(0)
    
    def add_tool_used(self, tool: str):
        self.recent_tools_used.append(tool)
        if len(self.recent_tools_used) > 10:
            self.recent_tools_used.pop(0)
    
    def add_fact(self, fact: str):
        self.session_facts.append(fact)
    
    def to_string(self) -> str:
        parts = []
        if self.current_topic:
            parts.append(f"Current topic: {self.current_topic}")
        if self.recent_entities:
            parts.append(f"Recently mentioned: {', '.join(self.recent_entities[-5:])}")
        if self.session_facts:
            parts.append(f"Learned this session: {'; '.join(self.session_facts[-5:])}")
        return "\n".join(parts) if parts else "No prior context in this session."
```

---

## 7. SERVER PACKAGE

### `packages/server/kira/server/app.py`

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: connect to DB, initialize models
    from kira.memory.db import get_db
    db = await get_db()
    
    # Run migrations
    from scripts.migrate import run_migrations
    await run_migrations(db)
    
    # Initialize brain
    from kira.brain.ollama_client import OllamaClient
    from kira.brain.gemini_client import GeminiClient
    from kira.brain.router import ModelRouter
    from kira.config import get_config
    
    config = get_config()
    ollama = OllamaClient()
    gemini = GeminiClient(api_key=config.models.cloud.api_key)
    router = ModelRouter(config, ollama, gemini)
    
    # Store in app state
    app.state.db = db
    app.state.ollama = ollama
    app.state.gemini = gemini
    app.state.router = router
    
    yield
    
    # Shutdown
    await db.disconnect()

def create_app() -> FastAPI:
    app = FastAPI(
        title="KIRA",
        description="Personal AI Assistant",
        version="0.1.0",
        lifespan=lifespan
    )
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    from kira.server.routes import chat, memory, health, config
    app.include_router(health.router)
    app.include_router(chat.router, prefix="/api")
    app.include_router(memory.router, prefix="/api")
    app.include_router(config.router, prefix="/api")
    
    return app
```

### `packages/server/kira/server/routes/chat.py`

The main chat endpoint. This is where brain + memory + tools come together.

```python
from fastapi import APIRouter, WebSocket, Request
from kira.types import ChatRequest, ChatResponse, Message, Role, ModelTier, KiraState
from kira.brain.intent import IntentClassifier
from kira.brain.prompts import KIRA_SYSTEM_PROMPT, MEMORY_EXTRACTION_PROMPT
from kira.memory.store import MemoryStore
from kira.memory.graph import KnowledgeGraph
from kira.memory.conversations import ConversationManager
from kira.memory.context import WorkingContext
from kira.memory.embeddings import EmbeddingEngine

router = APIRouter(tags=["chat"])

# Session-scoped working context
_contexts: dict[str, WorkingContext] = {}

@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, req: Request):
    import time
    start = time.time()
    
    db = req.app.state.db
    ollama = req.app.state.ollama
    model_router = req.app.state.router
    config = get_config()
    
    # Initialize subsystems
    embeddings = EmbeddingEngine(ollama)
    memory_store = MemoryStore(db, embeddings)
    knowledge_graph = KnowledgeGraph(db, embeddings)
    conversations = ConversationManager(db, ollama, config.models.fast.model)
    intent_classifier = IntentClassifier(ollama, config.models.fast.model)
    
    # Get or create working context
    session_key = str(request.conversation_id or "default")
    if session_key not in _contexts:
        _contexts[session_key] = WorkingContext()
    ctx = _contexts[session_key]
    
    # Get or create conversation
    conv_id = request.conversation_id
    if not conv_id:
        conv_id = await conversations.create_conversation()
    ctx.current_conversation_id = conv_id
    
    # Store user message
    user_msg = Message(role=Role.USER, content=request.message, conversation_id=conv_id)
    await conversations.add_message(conv_id, user_msg)
    
    # 1. Classify intent
    intent = await intent_classifier.classify(request.message)
    
    # 2. Route to model tier
    tier = await model_router.route(request.message, {
        "intent": intent,
        "has_context": bool(ctx.current_topic),
    })
    
    # 3. Retrieve relevant memories
    memories = await memory_store.search(request.message, limit=5)
    memories_text = "\n".join(f"- {m.content}" for m in memories) or "No relevant memories."
    
    # 4. Get knowledge graph context
    graph_context = await knowledge_graph.build_context_for(request.message)
    
    # 5. Build messages for LLM
    system_prompt = KIRA_SYSTEM_PROMPT.format(
        personal_context=graph_context or "No personal context loaded yet.",
        memories=memories_text,
        working_context=ctx.to_string()
    )
    
    recent_messages = await conversations.get_recent_context(conv_id, max_messages=10)
    
    llm_messages = [
        {"role": "system", "content": system_prompt},
        *recent_messages
    ]
    
    # 6. Generate response
    response_text = await model_router.generate(tier, llm_messages)
    
    # 7. Store assistant message
    assistant_msg = Message(
        role=Role.ASSISTANT, 
        content=response_text,
        conversation_id=conv_id,
        metadata={"model_tier": tier.value, "intent": intent}
    )
    await conversations.add_message(conv_id, assistant_msg)
    
    # 8. Background: extract memories from this exchange
    # (In production, this would be an async background task)
    await _extract_and_store_memories(
        request.message, response_text, conv_id,
        ollama, config, memory_store, knowledge_graph, embeddings
    )
    
    latency_ms = int((time.time() - start) * 1000)
    
    return ChatResponse(
        message=assistant_msg,
        conversation_id=conv_id,
        state=KiraState.IDLE,
        memories_used=[m.id for m in memories],
        model_used=f"{tier.value}",
        latency_ms=latency_ms
    )


async def _extract_and_store_memories(
    user_message: str, assistant_response: str, conv_id,
    ollama, config, memory_store, knowledge_graph, embeddings
):
    """Extract durable facts from the exchange and store them."""
    from kira.brain.prompts import MEMORY_EXTRACTION_PROMPT
    import json as json_module
    
    exchange = f"User: {user_message}\nAssistant: {assistant_response}"
    
    try:
        result = await ollama.generate(
            model=config.models.fast.model,
            prompt=MEMORY_EXTRACTION_PROMPT.format(conversation=exchange),
            temperature=0.1
        )
        
        # Parse JSON response
        # Strip markdown code fences if present
        clean = result.strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[1].rsplit("```", 1)[0]
        
        facts = json_module.loads(clean)
        
        for fact in facts:
            if not fact.get("content"):
                continue
            
            memory = Memory(
                content=fact["content"],
                category=MemoryCategory(fact.get("category", "observation")),
                importance=float(fact.get("importance", 0.5)),
                source_type="conversation",
                source_id=conv_id
            )
            await memory_store.store(memory)
            
            # Extract and link entities
            for entity_name in fact.get("entities", []):
                existing = await knowledge_graph.get_entity(entity_name)
                if not existing:
                    entity = Entity(
                        type=EntityType.TOPIC,
                        name=entity_name
                    )
                    await knowledge_graph.add_entity(entity)
    
    except (json_module.JSONDecodeError, KeyError, ValueError):
        # Memory extraction is best-effort, don't fail the chat
        pass
```

### `packages/server/kira/server/routes/memory.py`

```python
from fastapi import APIRouter, Request
router = APIRouter(tags=["memory"])

@router.get("/memory/search")
async def search_memories(q: str, limit: int = 10, req: Request = None):
    db = req.app.state.db
    ollama = req.app.state.ollama
    embeddings = EmbeddingEngine(ollama)
    store = MemoryStore(db, embeddings)
    memories = await store.search(q, limit=limit)
    return {"memories": [m.model_dump() for m in memories]}

@router.get("/memory/graph")
async def get_graph(req: Request):
    db = req.app.state.db
    entities = await db.fetch("SELECT id, type, name, metadata FROM entities ORDER BY updated_at DESC LIMIT 100")
    relationships = await db.fetch("SELECT * FROM relationships WHERE valid_until IS NULL LIMIT 500")
    return {
        "entities": [dict(e) for e in entities],
        "relationships": [dict(r) for r in relationships]
    }

@router.get("/memory/all")
async def get_all_memories(limit: int = 50, offset: int = 0, req: Request = None):
    db = req.app.state.db
    ollama = req.app.state.ollama
    embeddings = EmbeddingEngine(ollama)
    store = MemoryStore(db, embeddings)
    memories = await store.get_all(limit=limit, offset=offset)
    return {"memories": [m.model_dump() for m in memories]}

@router.delete("/memory/{memory_id}")
async def delete_memory(memory_id: str, req: Request):
    db = req.app.state.db
    ollama = req.app.state.ollama
    embeddings = EmbeddingEngine(ollama)
    store = MemoryStore(db, embeddings)
    deleted = await store.delete(UUID(memory_id))
    return {"deleted": deleted}
```

### `packages/server/kira/server/routes/health.py`

```python
from fastapi import APIRouter, Request
router = APIRouter(tags=["health"])

@router.get("/health")
async def health(req: Request):
    ollama_ok = await req.app.state.ollama.health()
    db_ok = req.app.state.db.pool is not None
    
    return {
        "status": "ok" if (ollama_ok and db_ok) else "degraded",
        "ollama": "connected" if ollama_ok else "disconnected",
        "database": "connected" if db_ok else "disconnected",
        "version": "0.1.0"
    }
```

---

## 8. CLIENT (React Frontend)

The Phase 1 frontend is a clean text chat interface + memory viewer. No voice yet, no 3D avatar — just a functional brain you can talk to.

### Tech stack:
- React 18 + TypeScript
- Vite
- Tailwind CSS
- Zustand (state management)
- Minimal, dark theme

### Key components:

**App.tsx** — Main layout: sidebar (memory viewer toggle, conversations list) + main area (chat).

**Chat.tsx** — Message list + input bar. Shows model tier used per message (small tag: "fast" / "smart" / "cloud"). Streams responses via WebSocket when available, falls back to POST.

**Avatar.tsx** — Simple SVG circle with state-based animations:
- IDLE: subtle breathing pulse
- THINKING: rotating ring
- SPEAKING: wave animation  
- ERROR: red pulse

This is intentionally minimal. The 3D upgrade comes in Phase 11.

**MemoryViewer.tsx** — Two tabs:
1. **Memories** — searchable list of stored memories, grouped by category, with delete buttons
2. **Knowledge Graph** — visual graph of entities and relationships (can use a simple force-directed layout with d3-force or just a list view initially)

**StatusBar.tsx** — Shows: connection status, current model, last response latency.

### Design direction:
- Dark background (#0a0a0a)
- Accent color for KIRA: electric blue (#3b82f6) or cyan (#06b6d4)
- Monospace for code/technical, system font for conversation
- No unnecessary borders or cards — let content breathe
- The avatar sits at the top of the chat, small, reacting to state

---

## 9. SCRIPTS

### `scripts/setup.sh`

```bash
#!/bin/bash
set -e

echo "Setting up KIRA..."

# Check Ollama
if ! command -v ollama &> /dev/null; then
    echo "Ollama not found. Install from https://ollama.com/download"
    exit 1
fi

# Pull models
echo "Pulling fast model (gemma4:e2b)..."
ollama pull gemma4:e2b

echo "Pulling smart model (gemma3:8b)..."
ollama pull gemma3:8b

echo "Pulling embedding model..."
ollama pull nomic-embed-text

# Start infrastructure
echo "Starting PostgreSQL + Redis..."
docker compose up -d

# Wait for PostgreSQL
echo "Waiting for PostgreSQL..."
sleep 5

# Install Python packages
echo "Installing Python packages..."
cd packages/core && pip install -e . && cd ../..
cd packages/brain && pip install -e . && cd ../..
cd packages/memory && pip install -e . && cd ../..
cd packages/server && pip install -e . && cd ../..

# Run migrations
echo "Running database migrations..."
python scripts/migrate.py

# Install frontend
echo "Installing frontend..."
cd packages/client && npm install && cd ../..

# Create .env from example
if [ ! -f .env ]; then
    cp .env.example .env
    echo "Created .env — fill in your GEMINI_API_KEY"
fi

echo "KIRA setup complete."
echo "Run 'bash scripts/dev.sh' to start."
```

### `scripts/dev.sh`

```bash
#!/bin/bash
# Start KIRA in development mode

# Ensure Docker services are running
docker compose up -d

# Start backend
echo "Starting KIRA server..."
cd packages/server
uvicorn kira.server.app:create_app --factory --reload --host 127.0.0.1 --port 8750 &
BACKEND_PID=$!

# Start frontend
echo "Starting KIRA client..."
cd ../client
npm run dev &
FRONTEND_PID=$!

# Cleanup on exit
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null" EXIT

echo ""
echo "KIRA is running:"
echo "  Backend:  http://localhost:8750"
echo "  Frontend: http://localhost:5173"
echo ""

wait
```

---

## 10. EVALS

### `evals/cases/intent_classification.yaml`

```yaml
name: intent_classification
description: Test that the intent classifier correctly categorizes messages

cases:
  - input: "Hello KIRA"
    expected: "greeting"
  
  - input: "What's the capital of France?"
    expected: "question"
  
  - input: "Open VS Code for me"
    expected: "command"
  
  - input: "Yeah I think that's a good approach, let's go with React"
    expected: "conversation"
  
  - input: "What did I say about the project deadline?"
    expected: "memory_query"
  
  - input: "What models do you use?"
    expected: "meta"
  
  - input: "Can you remember that I prefer dark mode?"
    expected: "command"
  
  - input: "Do you remember my meeting schedule?"
    expected: "memory_query"
```

### `evals/cases/routing.yaml`

```yaml
name: model_routing
description: Test that the model router picks the right tier

cases:
  - input: "Hi"
    expected_tier: "fast"
  
  - input: "What time is it?"
    expected_tier: "fast"
  
  - input: "Explain how transformers work in machine learning"
    expected_tier: "smart"
  
  - input: "Review this 200-line Python file and suggest improvements"
    expected_tier: "smart"
  
  - input: "Research the top 10 AI frameworks in 2026 with pros and cons"
    expected_tier: "cloud"
```

---

## 11. PYTHON DEPENDENCIES

### `packages/core/pyproject.toml`

```toml
[project]
name = "kira-core"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "pydantic>=2.0",
    "pyyaml>=6.0",
    "python-dotenv>=1.0",
]
```

### `packages/brain/pyproject.toml`

```toml
[project]
name = "kira-brain"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "kira-core",
    "httpx>=0.27",
]
```

### `packages/memory/pyproject.toml`

```toml
[project]
name = "kira-memory"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "kira-core",
    "kira-brain",
    "asyncpg>=0.29",
    "pgvector>=0.3",
]
```

### `packages/server/pyproject.toml`

```toml
[project]
name = "kira-server"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "kira-core",
    "kira-brain",
    "kira-memory",
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "websockets>=13.0",
]
```

---

## 12. KEY DESIGN DECISIONS

1. **All memory writes go through redaction.** No exceptions. The `MemoryStore.store()` method calls `redact()` before writing. This is the security layer.

2. **The fast model is always warm.** It handles intent, routing, memory extraction, and digest. It should respond in <500ms. If it's slow, something is wrong.

3. **The smart model loads on demand.** On a 16GB M4, keeping both gemma4:e2b (~1.5GB) and gemma3:8b (~5GB) loaded simultaneously is tight but feasible. If RAM pressure is an issue, the smart model unloads when idle.

4. **Cloud is a fallback, not a default.** Gemini fires only when: (a) the smart model explicitly fails, (b) the router classifies "complex", or (c) the user forces it.

5. **Memory extraction is background and best-effort.** If the LLM returns bad JSON or the extraction fails, chat still works. Memory is a bonus, not a dependency.

6. **The knowledge graph builds over time.** It starts empty. Every conversation extracts entities and relationships. After a week of use, KIRA knows your world.

7. **Working context dies with the session.** It's RAM-only. Long-term facts go to the database. This keeps the boundary clean.

8. **Every chat response includes metadata.** The frontend shows which model tier was used and the latency. Transparency builds trust.






13. DESKTOP APP (Tauri)

KIRA runs as a native macOS desktop app using Tauri v2, NOT in a browser tab.

Why Tauri over Electron:
Uses macOS native WebKit (no bundled Chromium)
~5MB binary vs ~300MB for Electron
Lower RAM usage — critical on 16GB
Native macOS APIs (notifications, system tray, menu bar, global shortcuts)
Rust backend for system-level features
Project structure addition:
kira/
├── src-tauri/                    # Tauri (Rust) backend
│   ├── Cargo.toml
│   ├── tauri.conf.json
│   ├── src/
│   │   ├── main.rs              # Tauri app entry
│   │   └── lib.rs               # Commands exposed to frontend
│   ├── icons/                   # App icons
│   └── capabilities/
│       └── default.json
│
├── packages/
│   └── client/                  # React frontend (Tauri loads this)
│       ├── src-tauri → ../../src-tauri  # Symlink or Tauri config points here
│       └── ...existing React app
src-tauri/tauri.conf.json:
json
{
  "$schema": "https://raw.githubusercontent.com/nicholasgasior/tauri-build-action/main/tauri.conf.schema.json",
  "productName": "KIRA",
  "identifier": "dev.kira.app",
  "version": "0.1.0",
  "build": {
    "frontendDist": "../packages/client/dist",
    "devUrl": "http://localhost:5173",
    "beforeDevCommand": "cd packages/client && npm run dev",
    "beforeBuildCommand": "cd packages/client && npm run build"
  },
  "app": {
    "title": "KIRA",
    "windows": [
      {
        "title": "KIRA",
        "width": 1200,
        "height": 800,
        "minWidth": 400,
        "minHeight": 600,
        "resizable": true,
        "decorations": true,
        "transparent": false
      }
    ],
    "trayIcon": {
      "iconPath": "icons/tray-icon.png",
      "tooltip": "KIRA"
    }
  },
  "bundle": {
    "active": true,
    "targets": ["dmg", "app"],
    "icon": [
      "icons/32x32.png",
      "icons/128x128.png",
      "icons/128x128@2x.png",
      "icons/icon.icns"
    ],
    "macOS": {
      "minimumSystemVersion": "14.0"
    }
  }
}
src-tauri/src/main.rs:
rust
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use tauri::{Manager, SystemTray, SystemTrayEvent, SystemTrayMenu, CustomMenuItem};

fn main() {
    let tray_menu = SystemTrayMenu::new()
        .add_item(CustomMenuItem::new("show", "Show KIRA"))
        .add_item(CustomMenuItem::new("quit", "Quit"));

    let system_tray = SystemTray::new().with_menu(tray_menu);

    tauri::Builder::default()
        .system_tray(system_tray)
        .on_system_tray_event(|app, event| match event {
            SystemTrayEvent::LeftClick { .. } => {
                let window = app.get_window("main").unwrap();
                window.show().unwrap();
                window.set_focus().unwrap();
            }
            SystemTrayEvent::MenuItemClick { id, .. } => match id.as_str() {
                "show" => {
                    let window = app.get_window("main").unwrap();
                    window.show().unwrap();
                    window.set_focus().unwrap();
                }
                "quit" => std::process::exit(0),
                _ => {}
            },
            _ => {}
        })
        .on_window_event(|event| match event.event() {
            tauri::WindowEvent::CloseRequested { api, .. } => {
                // Hide to tray instead of quitting
                event.window().hide().unwrap();
                api.prevent_close();
            }
            _ => {}
        })
        .invoke_handler(tauri::generate_handler![
            get_server_status,
            get_local_ip,
        ])
        .run(tauri::generate_context!())
        .expect("error while running KIRA");
}

#[tauri::command]
async fn get_server_status() -> Result<String, String> {
    let client = reqwest::Client::new();
    match client.get("http://127.0.0.1:8750/health").send().await {
        Ok(resp) => Ok(resp.text().await.unwrap_or_default()),
        Err(e) => Err(format!("Server not running: {}", e)),
    }
}

#[tauri::command]
fn get_local_ip() -> String {
    local_ip_address::local_ip()
        .map(|ip| ip.to_string())
        .unwrap_or_else(|_| "unknown".to_string())
}
Key behaviors:
System tray — KIRA lives in the macOS menu bar. Click tray icon to show/hide.
Close = hide — Closing the window hides to tray, doesn't quit. KIRA is always running.
Global shortcut — Cmd+Shift+K opens KIRA from anywhere (register in Tauri).
Auto-start Python server — Tauri's beforeDevCommand or a sidecar process starts the FastAPI backend automatically.
Tauri dependencies:
bash
# Install Rust (if not present)
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# Install Tauri CLI
cargo install tauri-cli

# Initialize in project root
cd ~/kira
cargo tauri init
14. NETWORK ACCESS (Phone + Other Devices)
Server changes:

In config/default.yaml, change:

yaml
server:
  host: "0.0.0.0"          # Was "127.0.0.1" — now listens on all interfaces
  port: 8750
  cors_origins:
    - "http://localhost:5173"
    - "tauri://localhost"          # Tauri webview origin
    - "http://localhost:8750"
    - "http://*:8750"             # Local network access

In packages/server/kira/server/app.py, update CORS to allow local network:

python
# Dynamic CORS — allow any device on local network
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1|192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+|tauri://localhost)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
Phone access flow:
Your Mac (192.168.1.x)
├── KIRA Server (0.0.0.0:8750)     ← Python FastAPI backend
├── KIRA Client (built static)      ← Served by FastAPI too
└── Tauri Desktop App               ← Native Mac window

Your Phone (same WiFi)
└── Safari: http://192.168.1.x:8750 ← Gets the same React UI
Serve the frontend from FastAPI:

Add a static file mount so the built React app is served by the backend itself. This way, opening http://192.168.1.x:8750 on your phone loads the full KIRA UI without a separate dev server.

In packages/server/kira/server/app.py:

python
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

def create_app() -> FastAPI:
    app = FastAPI(...)
    
    # ... existing setup ...
    
    # Serve React build for phone/browser access
    client_dist = Path(__file__).parent.parent.parent.parent / "client" / "dist"
    if client_dist.exists():
        app.mount("/assets", StaticFiles(directory=client_dist / "assets"), name="assets")
        
        @app.get("/{path:path}")
        async def serve_spa(path: str):
            """Serve React SPA — all non-API routes return index.html"""
            file_path = client_dist / path
            if file_path.exists() and file_path.is_file():
                return FileResponse(file_path)
            return FileResponse(client_dist / "index.html")
    
    return app
Frontend API base URL detection:

In the React app, detect whether it's running in Tauri (desktop) or browser (phone):

typescript
// packages/client/src/lib/api.ts

function getApiBaseUrl(): string {
  // If running in Tauri, server is always on localhost
  if ('__TAURI__' in window) {
    return 'http://127.0.0.1:8750';
  }
  
  // If running in browser (phone access), use the same host
  // Since FastAPI serves both the API and the static files,
  // the API is on the same origin
  return window.location.origin;
}

export const API_BASE = getApiBaseUrl();

// WebSocket URL
export function getWsUrl(): string {
  const base = API_BASE.replace('http', 'ws');
  return `${base}/api/chat/stream`;
}
Show QR code for phone connection:

Add a small feature: KIRA shows a QR code in the desktop app with the local network URL. Scan from your phone to connect instantly.

typescript
// packages/client/src/components/PhoneConnect.tsx
// Use a QR code library (qrcode.react) to show:
// http://<local-ip>:8750
Security for local network:

Since this is on your home WiFi, not the internet:

No auth needed for local network (it's your devices)
The CORS regex only allows private network IPs (192.168.x.x, 10.x.x.x)
The server never binds to a public interface
If you're on public WiFi, KIRA should auto-switch to 127.0.0.1 only

Add to config:

yaml
server:
  network_mode: "home"    # "home" = 0.0.0.0, "public" = 127.0.0.1 only
15. UPDATED dev.sh
bash
#!/bin/bash
# Start KIRA in development mode

# Ensure Docker services are running
docker compose up -d

# Get local IP for phone access
LOCAL_IP=$(ipconfig getifaddr en0 2>/dev/null || echo "127.0.0.1")

# Start backend (bind to all interfaces)
echo "Starting KIRA server..."
cd packages/server
uvicorn kira.server.app:create_app --factory --reload --host 0.0.0.0 --port 8750 &
BACKEND_PID=$!

# Start frontend dev server
echo "Starting KIRA client..."
cd ../client
npm run dev -- --host &
FRONTEND_PID=$!

# Cleanup on exit
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null" EXIT

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║             KIRA is running              ║"
echo "╠══════════════════════════════════════════╣"
echo "║  Desktop:  http://localhost:5173         ║"
echo "║  API:      http://localhost:8750         ║"
echo "║  Phone:    http://$LOCAL_IP:8750    ║"
echo "╚══════════════════════════════════════════╝"
echo ""

wait
16. UPDATED scripts/setup.sh

Add Rust/Tauri to the setup:

bash
# ... existing setup steps ...

# Install Rust (for Tauri)
if ! command -v rustc &> /dev/null; then
    echo "Installing Rust..."
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
    source "$HOME/.cargo/env"
fi

# Install Tauri CLI
if ! command -v cargo-tauri &> /dev/null; then
    echo "Installing Tauri CLI..."
    cargo install tauri-cli
fi

echo ""
echo "To run as desktop app:  cargo tauri dev"
echo "To run in browser:      bash scripts/dev.sh"
echo "To build .dmg:          cargo tauri build"
Summary of what changes from the original spec:
Server binds to 0.0.0.0 instead of 127.0.0.1
CORS allows local network IPs (192.168.x.x, 10.x.x.x) + tauri://localhost
FastAPI serves the built React app as static files (for phone access)
Tauri wraps the React frontend as a native Mac app with system tray
Frontend auto-detects Tauri vs browser and adjusts API URL accordingly
QR code component for easy phone pairing
Close = hide to tray, KIRA is always running
Global shortcut Cmd+Shift+K to summon KIRA from anywhere
