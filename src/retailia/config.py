"""Runtime settings, read once from environment variables.

Paths are made absolute here so the app behaves the same from any working directory.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Mapping

HOME_DIR = Path.home() / ".retailia"
LLM_PROVIDERS = ("offline", "openai")
EMBEDDERS = ("hashing", "openai")


class SettingsError(ValueError):
    pass


def packaged_faq_dir() -> Path:
    return Path(str(resources.files("retailia.rag").joinpath("faq")))


def _path(env: Mapping[str, str], name: str, default: Path) -> Path:
    raw = env.get(name, "").strip()
    return Path(raw).expanduser().resolve() if raw else default


def _positive_int(env: Mapping[str, str], name: str, default: int) -> int:
    raw = env.get(name, "").strip()
    if not raw:
        return default
    if not raw.isdigit() or int(raw) < 1:
        raise SettingsError(f"{name} must be a positive integer (got {raw!r})")
    return int(raw)


def _choice(env: Mapping[str, str], name: str, default: str, allowed: tuple[str, ...]) -> str:
    value = env.get(name, "").strip().lower() or default
    if value not in allowed:
        raise SettingsError(f"{name} must be one of {', '.join(allowed)} (got {value!r})")
    return value


@dataclass(frozen=True)
class Settings:
    db_path: Path = HOME_DIR / "retailia.db"
    faq_dir: Path = field(default_factory=packaged_faq_dir)
    index_path: Path = HOME_DIR / "faq_index.json"
    llm_provider: str = "offline"
    llm_model: str = "llama-3.1-8b-instant"
    llm_base_url: str | None = None
    llm_api_key: str | None = field(default=None, repr=False)
    embedder: str = "hashing"
    embedding_model: str = "text-embedding-3-small"
    max_tool_steps: int = 5
    session_ttl_minutes: int = 30
    max_login_failures: int = 5
    lockout_minutes: int = 15
    seed: int = 11

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        env = os.environ if env is None else env
        settings = cls(
            db_path=_path(env, "RETAILIA_DB_PATH", HOME_DIR / "retailia.db"),
            faq_dir=_path(env, "RETAILIA_FAQ_DIR", packaged_faq_dir()),
            index_path=_path(env, "RETAILIA_INDEX_PATH", HOME_DIR / "faq_index.json"),
            llm_provider=_choice(env, "RETAILIA_LLM_PROVIDER", "offline", LLM_PROVIDERS),
            llm_model=env.get("RETAILIA_LLM_MODEL", "").strip() or "llama-3.1-8b-instant",
            llm_base_url=env.get("RETAILIA_LLM_BASE_URL", "").strip() or None,
            llm_api_key=env.get("RETAILIA_LLM_API_KEY", "").strip() or None,
            embedder=_choice(env, "RETAILIA_EMBEDDER", "hashing", EMBEDDERS),
            embedding_model=env.get("RETAILIA_EMBEDDING_MODEL", "").strip() or "text-embedding-3-small",
            max_tool_steps=_positive_int(env, "RETAILIA_MAX_TOOL_STEPS", 5),
            session_ttl_minutes=_positive_int(env, "RETAILIA_SESSION_TTL_MINUTES", 30),
            max_login_failures=_positive_int(env, "RETAILIA_MAX_LOGIN_FAILURES", 5),
            lockout_minutes=_positive_int(env, "RETAILIA_LOCKOUT_MINUTES", 15),
            seed=_positive_int(env, "RETAILIA_SEED", 11),
        )
        needs_remote = settings.llm_provider == "openai" or settings.embedder == "openai"
        if needs_remote and not (settings.llm_api_key or settings.llm_base_url):
            raise SettingsError("the 'openai' provider/embedder needs RETAILIA_LLM_API_KEY, or "
                                "RETAILIA_LLM_BASE_URL for a local OpenAI-compatible server")
        return settings


def load_env_file() -> None:
    """Load a local .env if python-dotenv is installed (optional)."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(override=False)
