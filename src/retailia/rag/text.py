"""Tokenisation shared by BM25 and the hashing embedder."""

from __future__ import annotations

import re

STOPWORDS = frozenset(
    "a an and are as at be by can do does for from how i if in is it me my of on or our the to was we what "
    "when where which who will with you your this that there their is are am".split()
    # low-information verbs and fillers that otherwise dominate short questions
    + "take takes get got have has need want like know tell much many long any some would could should please "
      "also just its still".split()
)


def stem(token: str) -> str:
    """Tiny suffix stripper: 'cancelling'/'cancelled' -> 'cancel', 'shipping' -> 'ship', 'refunds' -> 'refund'."""
    for suffix in ("ing", "ed", "es", "s"):
        if len(token) > len(suffix) + 2 and token.endswith(suffix) and not token.endswith("ss"):
            token = token[: -len(suffix)]
            if suffix in ("ing", "ed") and len(token) > 3 and token[-1] == token[-2] and token[-1] not in "aeiouls":
                token = token[:-1]
            elif suffix in ("ing", "ed") and token.endswith("ll") and len(token) > 5:
                token = token[:-1]
            break
    return token


def tokenize(text: str) -> list[str]:
    return [stem(t) for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) > 1 and t not in STOPWORDS]
