"""Composition root shared by the CLI, the Streamlit UI and the evaluation harness."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from retailia.agent.assistant import Assistant
from retailia.agent.models import ChatModel, OpenAICompatModel
from retailia.agent.offline import OfflineModel
from retailia.auth.service import AuthService, SessionStore
from retailia.config import Settings
from retailia.data.db import StoreDB
from retailia.rag.embeddings import Embedder, HashingEmbedder, OpenAICompatEmbedder
from retailia.rag.index import IndexMismatch, IndexNotBuilt, load_index
from retailia.rag.retriever import HybridRetriever


@dataclass
class Retailia:
    settings: Settings
    db: StoreDB
    auth: AuthService
    sessions: SessionStore
    assistant: Assistant
    index_problem: str | None  # why FAQ answers are unavailable, if they are


def make_embedder(settings: Settings) -> Embedder:
    if settings.embedder == "openai":
        return OpenAICompatEmbedder(settings.embedding_model, api_key=settings.llm_api_key,
                                    base_url=settings.llm_base_url)
    return HashingEmbedder()


def make_model(settings: Settings) -> ChatModel:
    if settings.llm_provider == "openai":
        return OpenAICompatModel(settings.llm_model, api_key=settings.llm_api_key, base_url=settings.llm_base_url)
    return OfflineModel()


def build(settings: Settings, *, model: ChatModel | None = None, embedder: Embedder | None = None,
          clock: Callable[[], datetime] = datetime.now) -> Retailia:
    db = StoreDB(settings.db_path)
    embedder = embedder or make_embedder(settings)
    retriever, problem = None, None
    try:
        retriever = HybridRetriever(load_index(settings.index_path, expected_embedder=embedder.name), embedder)
    except (IndexNotBuilt, IndexMismatch) as exc:  # FAQ answers degrade gracefully instead of crashing
        problem = str(exc)
    assistant = Assistant(model or make_model(settings), db, retriever, max_steps=settings.max_tool_steps)
    auth = AuthService(db, clock, max_failures=settings.max_login_failures, lockout_minutes=settings.lockout_minutes)
    return Retailia(settings, db, auth, SessionStore(settings.session_ttl_minutes, clock), assistant, problem)
