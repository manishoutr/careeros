"""Re-embed jobs whose stored vector came from another embedding model.

Needed after an embedding-model upgrade: rows carry jobs.embedding_model,
so this finds stale ones and rewrites them (plus the pgvector store when
enabled). Usage: python3 scripts/reindex.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import SessionLocal, init_db  # noqa: E402
from app.models import Job  # noqa: E402
from app.services import vectorstore  # noqa: E402
from app.services.embeddings import embed_batch, model_version  # noqa: E402
from app.services.ingest import job_text  # noqa: E402


def main() -> int:
    init_db()
    db = SessionLocal()
    try:
        current = model_version()
        stale = [j for j in db.query(Job).all() if j.embedding_model != current]
        print(f"model={current} stale={len(stale)}")
        for start in range(0, len(stale), 64):
            batch = stale[start:start + 64]
            texts = [job_text(j.title, j.company, j.location,
                              j.skills_list(), j.description) for j in batch]
            for job, vec in zip(batch, embed_batch(texts)):
                job.embedding = json.dumps(vec)
                job.embedding_model = current
            db.commit()
            print(f"re-embedded {min(start + 64, len(stale))}/{len(stale)}")
        if vectorstore.available():
            print(f"pgvector synced: {vectorstore.sync_all(db)}")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
