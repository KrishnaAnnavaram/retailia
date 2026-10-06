"""Load FAQ sources and split them into citeable chunks.

Markdown and plain-text files are supported out of the box; each ``## Heading``
section becomes one chunk with a stable id ``<file stem>#<heading slug>``.
PDF files are read when the optional ``pypdf`` package is installed
(``pip install retailia[pdf]``) and are split into paragraphs per page.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

MAX_CHUNK_CHARS = 1500


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    title: str
    text: str
    source: str


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "section"


def split_markdown(text: str, source: str) -> list[Chunk]:
    stem = Path(source).stem
    chunks: list[Chunk] = []
    title, lines = "Introduction", []

    def flush() -> None:
        body = "\n".join(lines).strip()
        if body:
            for i, part in enumerate(_limit(body)):
                suffix = f"-{i + 1}" if i else ""
                chunks.append(Chunk(f"{stem}#{slugify(title)}{suffix}", title, part, source))

    for line in text.splitlines():
        heading = re.match(r"^#{2,3}\s+(.+?)\s*#*\s*$", line)
        if heading:
            flush()
            title, lines = heading.group(1), []
        elif not re.match(r"^#\s", line):
            lines.append(line)
    flush()
    return chunks


def _limit(body: str) -> list[str]:
    """Split overly long sections on paragraph boundaries (never inside a sentence like '9:00')."""
    if len(body) <= MAX_CHUNK_CHARS:
        return [body]
    parts, current = [], ""
    for paragraph in re.split(r"\n\s*\n", body):
        if current and len(current) + len(paragraph) > MAX_CHUNK_CHARS:
            parts.append(current.strip())
            current = ""
        current += paragraph + "\n\n"
    if current.strip():
        parts.append(current.strip())
    return parts


def _pdf_chunks(path: Path) -> list[Chunk]:
    try:
        from pypdf import PdfReader
    except ImportError:
        return []
    chunks = []
    for page_no, page in enumerate(PdfReader(str(path)).pages, start=1):
        text = (page.extract_text() or "").strip()
        for i, part in enumerate(_limit(text)):
            if part:
                chunks.append(Chunk(f"{path.stem}#page-{page_no}-{i + 1}", f"{path.stem} p.{page_no}", part, path.name))
    return chunks


def load_faq_chunks(folder: Path) -> list[Chunk]:
    folder = Path(folder)
    if not folder.is_dir():
        raise FileNotFoundError(f"FAQ folder not found: {folder}")
    chunks: list[Chunk] = []
    for path in sorted(folder.iterdir()):
        if path.suffix.lower() in (".md", ".txt"):
            chunks.extend(split_markdown(path.read_text(encoding="utf-8"), path.name))
        elif path.suffix.lower() == ".pdf":
            chunks.extend(_pdf_chunks(path))
    if not chunks:
        raise ValueError(f"no FAQ content found in {folder}")
    return chunks
