"""Job ingestion: CSV -> normalized, deduplicated, embedded Job rows."""
import csv
import hashlib
import json
from typing import IO, Tuple

from ..models import Job
from .embeddings import embed_batch, model_version


def dedupe_key(title: str, company: str, location: str) -> str:
    raw = "|".join([(title or "").strip().lower(),
                    (company or "").strip().lower(),
                    (location or "").strip().lower()])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def job_text(title: str, company: str, location: str, skills: list,
             description: str) -> str:
    """The document we index for retrieval: every searchable field in one string."""
    return " ".join([title, company, location, " ".join(skills), description])


def ingest_csv(db, fileobj: IO[str]) -> Tuple[int, int]:
    """Load a jobs CSV. Returns (inserted, skipped_duplicates).

    Expected columns: title, company, location, job_type, level, skills
    (semicolon-separated), description, url, posted_date.
    """
    reader = csv.DictReader(fileobj)
    required = {"title", "company", "location", "skills", "description"}
    missing = required - set(reader.fieldnames or [])
    if missing:
        raise ValueError(f"CSV is missing required columns: {sorted(missing)}")

    inserted = skipped = 0
    pending = []
    for row in reader:
        title = (row.get("title") or "").strip()
        company = (row.get("company") or "").strip()
        location = (row.get("location") or "").strip()
        if not title or not company:
            continue  # cannot normalize a job without title/company
        skills = [s.strip() for s in (row.get("skills") or "").split(";") if s.strip()]
        key = dedupe_key(title, company, location)
        if db.query(Job).filter_by(dedupe_key=key).first():
            skipped += 1
            continue
        description = (row.get("description") or "").strip()
        job = Job(
            dedupe_key=key,
            title=title,
            company=company,
            location=location,
            job_type=(row.get("job_type") or "").strip().lower(),
            level=(row.get("level") or "").strip().lower(),
            skills=json.dumps(skills),
            description=description,
            url=(row.get("url") or "").strip(),
            posted_date=(row.get("posted_date") or "").strip(),
            source="seed",
            embedding_model="",
            embedding="[]",
        )
        db.add(job)
        pending.append(job)
        inserted += 1
    db.flush()  # assign ids before embedding
    if pending:
        texts = [job_text(j.title, j.company, j.location,
                          json.loads(j.skills), j.description) for j in pending]
        vecs = embed_batch(texts)
        ver = model_version()
        for job, vec in zip(pending, vecs):
            job.embedding = json.dumps(vec)
            job.embedding_model = ver
    db.commit()
    from . import vectorstore  # keep the pgvector store in step, when enabled
    if vectorstore.available():
        vectorstore.sync_all(db)
    return inserted, skipped
