"""Job synchronisation: fetch external sources, normalise, dedupe, embed,
and mark stale listings expired.

Idempotent: re-running with the same source data updates last_verified_at
and changes nothing else. Dedupe works on two levels:
1. same source + same source id -> same listing seen again;
2. normalised title+company across sources -> cross-posted duplicate.
"""
import json
import logging
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

from ..embeddings import embed_batch, model_version
from ..ingest import dedupe_key, job_text
from ...models import Job
from ..parsing import SKILLS_LEXICON
from .base import RawJob, skills_from

log = logging.getLogger("careeros.sources")

FETCHERS = {}
SOURCE_TIMEOUT = 20
EXPIRE_AFTER_DAYS = 45
# A listing no source has confirmed for this long is hidden, even when its
# source keeps erroring or returning empty answers.
UNVERIFIED_EXPIRE_DAYS = 3


def _register():
    from . import arbeitnow, boards, remotive
    FETCHERS["remotive"] = remotive.fetch
    FETCHERS["arbeitnow"] = arbeitnow.fetch
    FETCHERS["greenhouse"] = boards.fetch


def _release_memory() -> None:
    """Hand freed memory back to the OS between sources (512 MB free host)."""
    import gc
    gc.collect()
    try:
        import ctypes
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except Exception:
        pass


def _today() -> str:
    return date.today().isoformat()


def _stale(posted: str) -> bool:
    try:
        d = datetime.strptime(posted[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return False
    return date.today() - d > timedelta(days=EXPIRE_AFTER_DAYS)


def expire_unverified(db, days: int = UNVERIFIED_EXPIRE_DAYS) -> int:
    """Bounded aging: hide listings whose source has not confirmed them within
    `days`. Covers repeated errors and empty responses, which deliberately do
    not expire anything on their own."""
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    n = 0
    for job in db.query(Job).filter(Job.is_expired == 0, Job.source != "seed").all():
        if job.last_verified_at and job.last_verified_at < cutoff:
            job.is_expired = 1
            n += 1
    if n:
        db.commit()
    return n


def sync_sources(db, source_names: Optional[List[str]] = None) -> Dict:
    """Fetch and merge the given sources (default: all). Returns a report."""
    if not FETCHERS:
        _register()
    names = source_names or list(FETCHERS)
    report = {"fetched": 0, "inserted": 0, "updated": 0,
              "skipped_duplicates": 0, "expired": 0, "sources": {}}
    today = _today()

    for name in names:
        fetcher = FETCHERS.get(name)
        if fetcher is None:
            report["sources"][name] = "unknown source"
            continue
        try:
            raw_jobs = fetcher(timeout=SOURCE_TIMEOUT)
        except Exception as e:
            log.warning("source %s failed: %s", name, e)
            report["sources"][name] = f"error: {e}"
            continue
        if not raw_jobs:
            # An empty answer is more likely an outage than a source with no
            # vacancies at all; never expire a whole source on that evidence.
            report["sources"][name] = "empty response: kept existing listings"
            continue
        report["fetched"] += len(raw_jobs)
        report["sources"][name] = len(raw_jobs)

        seen_ids = set()
        batch_keys = set()
        to_embed = []
        for raw in raw_jobs:
            seen_ids.add(raw.source_id)
            existing = db.query(Job).filter_by(source=raw.source,
                                               source_id=raw.source_id).first()
            if existing is not None:
                existing.last_verified_at = today
                existing.is_expired = 0
                existing.job_type, existing.level = raw.job_type, raw.level  # classifier fixes reach old rows
                report["updated"] += 1
                continue
            key = dedupe_key(raw.title, raw.company, raw.location)
            if key in batch_keys or db.query(Job).filter_by(dedupe_key=key).first() is not None:
                report["skipped_duplicates"] += 1
                continue
            batch_keys.add(key)
            skills = raw.skills or skills_from(raw.title + " " + raw.description,
                                               SKILLS_LEXICON)
            job = Job(
                dedupe_key=key, title=raw.title, company=raw.company,
                location=raw.location, job_type=raw.job_type, level=raw.level,
                skills=json.dumps(skills),
                description=raw.description,
                url=raw.url, posted_date=raw.posted_date,
                source=raw.source, source_id=raw.source_id,
                last_verified_at=today,
                is_expired=1 if (name != "greenhouse" and _stale(raw.posted_date)) else 0,
                embedding_model="",  # set after embedding below
                embedding="[]",
            )
            db.add(job)
            to_embed.append(job)
            report["inserted"] += 1

        db.flush()  # assign ids before embedding
        if to_embed:
            texts = [job_text(j.title, j.company, j.location,
                              json.loads(j.skills), j.description) for j in to_embed]
            vecs = embed_batch(texts)
            ver = model_version()
            for job, vec in zip(to_embed, vecs):
                job.embedding = json.dumps(vec)
                job.embedding_model = ver

        # Listings from this source that disappeared, or that are too old.
        stale = (db.query(Job)
                 .filter(Job.source == name, Job.is_expired == 0)
                 .all())
        for job in stale:
            if job.source_id not in seen_ids or (name != "greenhouse" and _stale(job.posted_date)):
                job.is_expired = 1
                report["expired"] += 1
        db.commit()
        del raw_jobs, to_embed
        db.expire_all()
        _release_memory()

    report["expired"] += expire_unverified(db)

    from .. import vectorstore  # keep pgvector store in step, when enabled
    if vectorstore.available():
        vectorstore.sync_all(db)
    return report
