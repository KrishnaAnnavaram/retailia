"""Embedding back ends behind one small interface.

* :class:`HashingEmbedder` is deterministic and offline (feature hashing of
  words and word pairs). It is the default and is what the tests use.
* :class:`OpenAICompatEmbedder` calls any OpenAI-compatible embeddings endpoint
  (``pip install retailia[openai]``).

The index records which embedder built it, and loading refuses a mismatch.
"""

from __future__ import annotations

import hashlib
import math
from typing import Any, Protocol, Sequence

from retailia.rag.text import tokenize


class Embedder(Protocol):
    name: str

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


def _normalise(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vector))
    return [v / norm for v in vector] if norm else vector


class HashingEmbedder:
    def __init__(self, dimensions: int = 512) -> None:
        self.dimensions = dimensions
        self.name = f"hashing-{dimensions}"

    def _bucket(self, feature: str) -> tuple[int, float]:
        digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
        value = int.from_bytes(digest, "big")
        return value % self.dimensions, (1.0 if (value >> 63) & 1 else -1.0)

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        out = []
        for text in texts:
            vector = [0.0] * self.dimensions
            tokens = tokenize(text)
            features = tokens + [f"{a}_{b}" for a, b in zip(tokens, tokens[1:])]
            for feature in features:
                index, sign = self._bucket(feature)
                vector[index] += sign
            out.append(_normalise(vector))
        return out


class OpenAICompatEmbedder:
    def __init__(self, model: str, *, api_key: str | None = None, base_url: str | None = None,
                 client: Any = None) -> None:
        if client is None:  # pragma: no cover - optional dependency
            from openai import OpenAI

            client = OpenAI(api_key=api_key or "unused-for-local-servers", base_url=base_url)
        self.client = client
        self.model = model
        self.name = f"openai:{model}"

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        response = self.client.embeddings.create(model=self.model, input=list(texts))
        return [_normalise(list(item.embedding)) for item in response.data]


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(x * y for x, y in zip(a, b))
