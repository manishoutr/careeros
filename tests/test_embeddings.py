"""Embedding backend: semantic MiniLM by default, honest hashing fallback."""
from app.services import embeddings


def test_semantic_backend_dim_and_norm():
    if embeddings.backend_info()["semantic"] is False:
        import pytest
        pytest.skip("MiniLM unavailable in this environment")
    vec = embeddings.embed("python backend internship")
    assert len(vec) == embeddings.MODEL_DIM == 384
    assert abs(sum(x * x for x in vec) ** 0.5 - 1.0) < 1e-3
    assert embeddings.model_version() == embeddings.MODEL_VERSION


def test_semantic_similarity_beats_lexical_mismatch():
    if embeddings.backend_info()["semantic"] is False:
        import pytest
        pytest.skip("MiniLM unavailable in this environment")
    a = embeddings.embed("junior software engineer role")
    b = embeddings.embed("entry level developer position")   # paraphrase, few shared words
    c = embeddings.embed("senior pastry chef needed")
    assert embeddings.cosine(a, b) > embeddings.cosine(a, c)


def test_hashing_fallback_is_explicit():
    saved = embeddings._minilm._failed
    try:
        embeddings._minilm._failed = "forced for test"
        vec = embeddings.embed("python backend internship")
        assert len(vec) == embeddings.HASH_DIM
        assert embeddings.model_version() == embeddings.HASH_MODEL_VERSION
        assert embeddings.backend_info()["semantic"] is False
    finally:
        embeddings._minilm._failed = saved


def test_batch_is_homogeneous_and_subbatched():
    if embeddings.backend_info()["semantic"] is False:
        import pytest
        pytest.skip("MiniLM unavailable in this environment")
    vecs = embeddings.embed_batch([f"job posting number {i} about python" for i in range(70)])
    assert len(vecs) == 70
    assert all(len(v) == 384 for v in vecs)
