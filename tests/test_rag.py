"""Problems 5 and 6: FAQ text stays intact, the index is built offline, versioned and safe to load."""

import json

import pytest

from retailia.config import packaged_faq_dir
from retailia.rag.documents import split_markdown
from retailia.rag.embeddings import HashingEmbedder
from retailia.rag.index import IndexMismatch, IndexNotBuilt, build_index, load_index, save_index
from retailia.rag.retriever import HybridRetriever
from retailia.rag.text import tokenize


def test_markdown_split_into_citeable_sections():
    chunks = split_markdown("# T\nintro\n## Opening hours\nOpen 9:00 - 17:00.\n## Returns\n30 days.", "faq.md")
    assert [c.chunk_id for c in chunks] == ["faq#introduction", "faq#opening-hours", "faq#returns"]
    assert chunks[1].text == "Open 9:00 - 17:00."


def test_tokenizer_stems_consistently():
    assert tokenize("Cancelling cancelled shipping refunds") == ["cancel", "cancel", "ship", "refund"]


@pytest.mark.parametrize("question,section", [
    ("how long do I have to return something?", "returns-and-refunds"),
    ("do you take paypal", "payment-methods"),
    ("my parcel arrived broken", "damaged-or-wrong-items"),
    ("which size should I pick", "sizing-help"),
    ("is there a warranty on headphones", "warranty"),
    ("can I cancel my order", "cancelling-an-order"),
])
def test_retrieval_top_hit(question, section):
    embedder = HashingEmbedder()
    retriever = HybridRetriever(build_index(packaged_faq_dir(), embedder), embedder)
    assert retriever.search(question)[0].chunk_id == f"store_faq#{section}"


def test_irrelevant_question_returns_no_passages():
    embedder = HashingEmbedder()
    retriever = HybridRetriever(build_index(packaged_faq_dir(), embedder), embedder)
    assert retriever.search("what's the weather on mars") == []


def test_index_round_trip_is_plain_json(tmp_path):
    embedder = HashingEmbedder()
    index = build_index(packaged_faq_dir(), embedder)
    path = tmp_path / "idx.json"
    save_index(index, path)
    payload = json.loads(path.read_text(encoding="utf-8"))  # no pickle anywhere
    assert payload["embedder"] == embedder.name and len(payload["chunks"]) == len(index.chunks)
    loaded = load_index(path, expected_embedder=embedder.name)
    assert loaded.version == index.version and loaded.chunks == index.chunks


def test_missing_or_mismatched_index(tmp_path):
    with pytest.raises(IndexNotBuilt):
        load_index(tmp_path / "missing.json")
    path = tmp_path / "idx.json"
    save_index(build_index(packaged_faq_dir(), HashingEmbedder(64)), path)
    with pytest.raises(IndexMismatch):
        load_index(path, expected_embedder=HashingEmbedder(512).name)


def test_app_without_index_still_answers_account_questions(make_app, tmp_path, customer):
    app = make_app(index_path=tmp_path / "nothing.json")
    assert app.index_problem and "build-index" in app.index_problem
    conv = app.assistant.start(customer)
    assert "couldn't find" in app.assistant.ask(conv, "how do refunds work?").text.lower()
    assert "order" in app.assistant.ask(conv, "show my orders").text.lower()


def test_faq_answer_keeps_colons_times_and_urls(app, customer):
    conv = app.assistant.start(customer)
    support = app.assistant.ask(conv, "When is support available?")
    assert "9:00 AM - 6:00 PM" in support.text and support.citations == ["store_faq#contacting-support"]
    tracking = app.assistant.ask(conv, "How do I track a parcel?")
    assert "https://example.com/track" in tracking.text
