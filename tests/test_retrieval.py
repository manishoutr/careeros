"""Retrieval quality: hybrid search must rank a clearly relevant job first."""
from app.services.retrieval import BM25, hybrid_scores
from app.services.embeddings import embed

TEXTS = [
    "Backend Developer Intern Zoho Chennai python fastapi postgresql redis docker Build and test REST APIs",
    "Frontend Developer Intern Freshworks Chennai javascript react html css git Build UI components",
    "Embedded Systems Intern Bosch Bangalore c c++ python linux testing automotive firmware",
]
EMBEDDINGS = [embed(t) for t in TEXTS]


def test_bm25_ranks_python_backend_first():
    scores = BM25(TEXTS).scores("backend internships using Python in India")
    assert scores[0] == max(scores)


def test_hybrid_ranks_python_backend_first():
    combined, parts = hybrid_scores(TEXTS, EMBEDDINGS, "backend internship Python")
    assert combined[0] == max(combined)
    # both signals contribute to the merged list
    assert len(parts["bm25"]) == len(parts["vector"]) == len(TEXTS)


def test_empty_corpus_is_safe():
    combined, _ = hybrid_scores([], [], "anything")
    assert combined == []
