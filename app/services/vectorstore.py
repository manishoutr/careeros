"""pgvector similarity store (PostgreSQL only).

When DATABASE_URL points at PostgreSQL, init_db() enables the pgvector
extension and creates a job_vectors table with a real VECTOR column, and
retrieval shortlists candidates with SQL-side cosine distance instead of
scanning every row in Python. SQLite installs skip this module: available()
is False and the in-Python hybrid path ranks the whole catalogue. The JSON
embedding column on jobs stays the source of truth either way.
"""
import json
import logging
from typing import List, Optional, Tuple

from sqlalchemy import text

from ..db import engine

log = logging.getLogger("careeros.vectorstore")

_available: Optional[bool] = None


def available() -> bool:
    return bool(_available)


def init() -> None:
    """Create the extension and table on Postgres; mark unavailable elsewhere."""
    global _available
    if not engine.url.get_backend_name().startswith("postgresql"):
        _available = False
        return
    try:
        dim = _current_dim()
        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.execute(text(
                "CREATE TABLE IF NOT EXISTS job_vectors ("
                " job_id INTEGER PRIMARY KEY REFERENCES jobs(id) ON DELETE CASCADE,"
                f" embedding VECTOR({dim}))"))
        _available = True
        log.info("pgvector store ready (dim=%d)", dim)
    except Exception as e:
        _available = False
        log.warning("pgvector unavailable, using in-Python retrieval: %s", e)


def _current_dim() -> int:
    from .embeddings import MODEL_DIM, model_version, HASH_MODEL_VERSION
    return MODEL_DIM if model_version() != HASH_MODEL_VERSION else 256


def upsert(job_id: int, embedding: List[float]) -> None:
    if not available():
        return
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO job_vectors (job_id, embedding) VALUES (:id, :v) "
            "ON CONFLICT (job_id) DO UPDATE SET embedding = EXCLUDED.embedding"),
            {"id": job_id, "v": str(embedding)})


def remove(job_id: int) -> None:
    if not available():
        return
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM job_vectors WHERE job_id = :id"), {"id": job_id})


def search(query_vec: List[float], limit: int = 60) -> List[int]:
    """Job ids ordered by cosine distance (pgvector <=>). Empty when off."""
    if not available():
        return []
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT job_id FROM job_vectors ORDER BY embedding <=> :v LIMIT :n"),
            {"v": str(query_vec), "n": limit}).fetchall()
    return [r[0] for r in rows]


def sync_all(db) -> int:
    """Repopulate job_vectors from the JSON embeddings on jobs."""
    if not available():
        return 0
    from ..models import Job
    n = 0
    for job in db.query(Job).all():
        vec = job.embedding_list()
        if vec:
            upsert(job.id, vec)
            n += 1
    return n


def candidate_jobs(db, query_text: str, limit: int = 60):
    """pgvector shortlist for a query, or None when the store is off
    (callers then fall back to scanning the whole catalogue)."""
    if not available():
        return None
    from ..models import Job
    from .embeddings import embed
    ids = search(embed(query_text), limit)
    if not ids:
        return []
    by_id = {j.id: j for j in db.query(Job).filter(Job.id.in_(ids)).all()}
    return [by_id[i] for i in ids if i in by_id]
