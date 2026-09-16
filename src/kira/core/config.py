"""Configuration loader.

Layered: config/default.yaml -> ~/.kira/config.yaml -> env overrides.
Environment overrides use the pattern KIRA_<SECTION>_<KEY>[_<SUBKEY>...].
"""
from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field


load_dotenv()


class ModelSpec(BaseModel):
    provider: str
    model: str
    api_key: str | None = None
    temperature: float = 0.7
    timeout_sec: int = 60
    fallback_to_cloud: bool = False


class EmbeddingsSpec(BaseModel):
    provider: str
    model: str


class ModelsConfig(BaseModel):
    fast: ModelSpec
    smart: ModelSpec
    cloud: ModelSpec
    vision: ModelSpec
    embeddings: EmbeddingsSpec


class PostgresConfig(BaseModel):
    host: str = "localhost"
    port: int = 5432
    database: str = "kira"
    user: str = "kira"
    password: str = ""


class RedisConfig(BaseModel):
    host: str = "localhost"
    port: int = 6379


class DatabaseConfig(BaseModel):
    postgres: PostgresConfig
    redis: RedisConfig


class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8750
    network_mode: str = "home"
    cors_origins: list[str] = Field(default_factory=list)


class MemoryConfig(BaseModel):
    auto_summarize_threshold: int = 20
    retrieval_limit: int = 10
    similarity_threshold: float = 0.7


class RedactionPattern(BaseModel):
    type: str


class RedactionConfig(BaseModel):
    enabled: bool = True
    patterns: list[RedactionPattern] = Field(default_factory=list)


class ToolOverrideSpec(BaseModel):
    mode: str = "default"
    rate_limit_per_min: int | None = None
    risk_override: int | None = None


class PermissionsConfig(BaseModel):
    auto_approve_level: int = 1
    require_confirm_level: int = 2
    tool_overrides: dict[str, ToolOverrideSpec] = Field(default_factory=dict)


class ExternalMCPSpec(BaseModel):
    name: str
    transport: str = "stdio"
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] | None = None
    url: str | None = None


class ToolsConfig(BaseModel):
    enabled_builtins: list[str] = Field(default_factory=list)
    external: list[ExternalMCPSpec] = Field(default_factory=list)
    relevance_top_k: int = 6


class TelegramConfig(BaseModel):
    bot_token: str = ""
    allowed_chat_ids: list[int] = Field(default_factory=list)


class DiscordConfig(BaseModel):
    bot_token: str = ""


class IntegrationsConfig(BaseModel):
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    discord: DiscordConfig = Field(default_factory=DiscordConfig)


class MonitorConfig(BaseModel):
    check_interval_sec: int = 300
    proactive_min_score: float = 0.6
    proactive_batch_window_sec: int = 30


class PersonalityConfig(BaseModel):
    formality: str = "balanced"   # "casual" | "balanced" | "formal"
    verbosity: str = "normal"     # "terse" | "normal" | "detailed"
    opinions: bool = True         # KIRA offers opinions when asked


class DocumentsConfig(BaseModel):
    enabled: bool = True
    watched_directories: list[str] = Field(default_factory=list)
    auto_index_on_startup: bool = True
    max_file_mb: int = 40
    chunk_tokens: int = 500
    overlap_tokens: int = 50
    parallelism: int = 2


class VoiceConfig(BaseModel):
    enabled: bool = True
    wake_word_enabled: bool = True
    wake_word_models: list[str] = Field(default_factory=lambda: ["hey_jarvis"])
    wake_word_threshold: float = 0.5
    whisper_model: str = "small.en"
    whisper_device: str = "auto"
    whisper_compute_type: str = "int8"
    piper_voice_path: str = ""
    input_device: int | str | None = None
    output_device: int | str | None = None


class LoggingConfig(BaseModel):
    level: str = "INFO"
    format: str = "json"
    file: str = "~/.kira/logs/kira.log"


class KiraMeta(BaseModel):
    name: str = "KIRA"
    version: str = "0.1.0"


class Config(BaseModel):
    kira: KiraMeta
    models: ModelsConfig
    database: DatabaseConfig
    server: ServerConfig
    memory: MemoryConfig
    redaction: RedactionConfig
    permissions: PermissionsConfig
    logging: LoggingConfig
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    integrations: IntegrationsConfig = Field(default_factory=IntegrationsConfig)
    monitor: MonitorConfig = Field(default_factory=MonitorConfig)
    documents: DocumentsConfig = Field(default_factory=DocumentsConfig)
    personality: PersonalityConfig = Field(default_factory=PersonalityConfig)
    voice: VoiceConfig = Field(default_factory=VoiceConfig)


_ENV_VAR_RE = re.compile(r"\$\{([A-Z0-9_]+)\}")


def _expand_env(value: Any) -> Any:
    if isinstance(value, str):
        def repl(match: re.Match) -> str:
            return os.environ.get(match.group(1), "")
        return _ENV_VAR_RE.sub(repl, value)
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env(v) for v in value]
    return value


def _deep_merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def _apply_env_overrides(data: dict) -> dict:
    """Apply KIRA_SECTION_KEY env overrides in-place."""
    for env_key, env_val in os.environ.items():
        if not env_key.startswith("KIRA_"):
            continue
        parts = env_key[len("KIRA_"):].lower().split("_")
        if not parts:
            continue
        node = data
        for p in parts[:-1]:
            if not isinstance(node, dict) or p not in node:
                node = None
                break
            node = node[p]
        if isinstance(node, dict) and parts[-1] in node:
            node[parts[-1]] = env_val
    return data


def _find_default_yaml() -> Path:
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        candidate = parent / "config" / "default.yaml"
        if candidate.exists():
            return candidate
    raise FileNotFoundError("config/default.yaml not found")


@lru_cache(maxsize=1)
def get_config() -> Config:
    default_path = _find_default_yaml()
    with default_path.open() as f:
        data = yaml.safe_load(f) or {}

    user_override = Path.home() / ".kira" / "config.yaml"
    if user_override.exists():
        with user_override.open() as f:
            override = yaml.safe_load(f) or {}
        data = _deep_merge(data, override)

    data = _apply_env_overrides(data)
    data = _expand_env(data)

    return Config(**data)


def reload_config() -> Config:
    get_config.cache_clear()
    return get_config()
