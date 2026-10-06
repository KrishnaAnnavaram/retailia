"""Offline-built, versioned FAQ index stored as plain JSON (no pickle, nothing executable on load)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from retailia.rag.documents import Chunk, load_faq_chunks
from retailia.rag.embeddings import Embedder

INDEX_FORMAT = 1


class IndexNotBuilt(FileNotFoundError):
    pass


class IndexMismatch(ValueError):
    pass


@dataclass(frozen=True)
class FaqIndex:
    chunks: list[Chunk]
    vectors: list[list[float]]
    embedder: str
    source_hash: str
    built_at: str

    @property
    def version(self) -> str:
        return self.source_hash[:12]


def _source_hash(chunks: list[Chunk]) -> str:
    digest = hashlib.sha256()
    for chunk in chunks:
        digest.update(f"{chunk.chunk_id}\x00{chunk.text}\x00".encode("utf-8"))
    return digest.hexdigest()


def build_index(faq_dir: Path, embedder: Embedder) -> FaqIndex:
    chunks = load_faq_chunks(faq_dir)
    vectors = embedder.embed([f"{c.title}\n{c.text}" for c in chunks])
    return FaqIndex(chunks, vectors, embedder.name, _source_hash(chunks),
                    datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))


def save_index(index: FaqIndex, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "format": INDEX_FORMAT,
        "embedder": index.embedder,
        "source_hash": index.source_hash,
        "built_at": index.built_at,
        "chunks": [asdict(c) for c in index.chunks],
        "vectors": [[round(v, 6) for v in vec] for vec in index.vectors],
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    tmp.replace(path)  # atomic swap: readers never see a half-written index


def load_index(path: Path, *, expected_embedder: str | None = None) -> FaqIndex:
    path = Path(path)
    if not path.exists():
        raise IndexNotBuilt(f"FAQ index not found at {path}; run `retailia build-index` first")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("format") != INDEX_FORMAT:
        raise IndexMismatch(f"unsupported index format {payload.get('format')!r}; rebuild the index")
    if expected_embedder and payload["embedder"] != expected_embedder:
        raise IndexMismatch(f"index was built with {payload['embedder']!r} but {expected_embedder!r} is configured; "
                            "rebuild the index")
    chunks = [Chunk(**c) for c in payload["chunks"]]
    if len(chunks) != len(payload["vectors"]):
        raise IndexMismatch("corrupt index: chunk and vector counts differ")
    return FaqIndex(chunks, payload["vectors"], payload["embedder"], payload["source_hash"], payload["built_at"])
