"""Hybrid retrieval: BM25 (lexical) + embeddings (semantic), merged by weighted, max-normalised scores."""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass

from retailia.rag.embeddings import Embedder, cosine
from retailia.rag.index import FaqIndex
from retailia.rag.text import tokenize


@dataclass(frozen=True)
class Passage:
    chunk_id: str
    title: str
    text: str
    score: float

    def citation(self) -> str:
        return f"[{self.chunk_id}]"


class BM25:
    def __init__(self, documents: list[list[str]], *, k1: float = 1.4, b: float = 0.75) -> None:
        self.k1, self.b = k1, b
        self.docs = [Counter(d) for d in documents]
        self.lengths = [len(d) for d in documents]
        self.avg_len = (sum(self.lengths) / len(self.lengths)) if self.lengths else 0.0
        frequency: Counter[str] = Counter()
        for doc in self.docs:
            frequency.update(doc.keys())
        n = len(self.docs)
        self.idf = {term: math.log(1 + (n - df + 0.5) / (df + 0.5)) for term, df in frequency.items()}

    def scores(self, query: list[str]) -> list[float]:
        out = []
        for doc, length in zip(self.docs, self.lengths):
            score = 0.0
            for term in set(query):
                tf = doc.get(term, 0)
                if tf:
                    norm = tf + self.k1 * (1 - self.b + self.b * length / (self.avg_len or 1))
                    score += self.idf[term] * tf * (self.k1 + 1) / norm
            out.append(score)
        return out


class HybridRetriever:
    def __init__(self, index: FaqIndex, embedder: Embedder, *, lexical_weight: float = 0.6, min_lexical: float = 1.5,
                 min_semantic: float = 0.3) -> None:
        self.index = index
        self.embedder = embedder
        self.lexical_weight = lexical_weight
        self.min_lexical = min_lexical
        self.min_semantic = min_semantic
        self.bm25 = BM25([tokenize(f"{c.title} {c.text}") for c in index.chunks])

    def search(self, question: str, k: int = 3) -> list[Passage]:
        """Top-k passages; empty when nothing is relevant enough (an explicit "no answer" signal)."""
        lexical = self.bm25.scores(tokenize(question))
        query_vec = self.embedder.embed([question])[0]
        semantic = [cosine(query_vec, v) for v in self.index.vectors]
        candidates = [i for i in range(len(self.index.chunks))
                      if lexical[i] >= self.min_lexical or semantic[i] >= self.min_semantic]
        if not candidates:
            return []
        top_lex = max(lexical[i] for i in candidates) or 1.0
        top_sem = max(max(semantic[i], 0.0) for i in candidates) or 1.0
        w = self.lexical_weight
        fused = {i: w * lexical[i] / top_lex + (1 - w) * max(semantic[i], 0.0) / top_sem for i in candidates}
        best = sorted(candidates, key=lambda i: (-fused[i], i))[:k]
        return [Passage(self.index.chunks[i].chunk_id, self.index.chunks[i].title, self.index.chunks[i].text,
                        round(fused[i], 5)) for i in best]
