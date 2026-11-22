"""Job-source sync: fixtures, no network. Covers dedupe (in-batch and
cross-run), idempotency, expiry marking and provenance fields."""
import json
from datetime import date, timedelta

import pytest

from app.db import SessionLocal, init_db
from app.models import Job
from app.services.sources import sync as sync_mod
from app.services.sources.base import RawJob


def _raw(source_id, title="Backend Intern", company="Acme", location="Remote",
         posted=None, skills=("python", "fastapi")):
    return RawJob(source="testsrc", source_id=source_id, title=title,
                  company=company, location=location, job_type="internship",
                  level="entry", skills=list(skills), description="build apis",
                  url=f"https://jobs.example/{source_id}",
                  posted_date=posted or date.today().isoformat())


@pytest.fixture()
def db():
    init_db()
    session = SessionLocal()
    yield session
    session.query(Job).filter(Job.source == "testsrc").delete()
    session.commit()
    session.close()


def _run_sync(db, payloads):
    sync_mod.FETCHERS["testsrc"] = lambda timeout=20: payloads
    return sync_mod.sync_sources(db, ["testsrc"])


def test_insert_and_provenance(db):
    report = _run_sync(db, [_raw("a1"), _raw("a2", title="React Intern")])
    assert report["inserted"] == 2
    job = db.query(Job).filter_by(source="testsrc", source_id="a1").one()
    assert job.last_verified_at == date.today().isoformat()
    assert job.is_expired == 0
    assert job.embedding_model  # recorded which model wrote the vector
    assert len(json.loads(job.embedding)) > 0


def test_in_batch_duplicates_do_not_crash(db):
    # Same title+company+location twice in one fetch (regression: UNIQUE crash)
    report = _run_sync(db, [_raw("b1"), _raw("b2")])
    assert report["inserted"] == 1
    assert report["skipped_duplicates"] == 1


def test_second_run_is_idempotent(db):
    _run_sync(db, [_raw("c1")])
    report = _run_sync(db, [_raw("c1")])
    assert report["inserted"] == 0
    assert report["updated"] == 1
    assert db.query(Job).filter_by(source="testsrc").count() == 1


def test_missing_listing_expires(db):
    _run_sync(db, [_raw("d1"), _raw("d2", title="Other Role")])
    report = _run_sync(db, [_raw("d1")])  # d2 gone from source
    assert report["expired"] == 1
    gone = db.query(Job).filter_by(source_id="d2").one()
    assert gone.is_expired == 1


def test_old_posting_expires(db):
    old = (date.today() - timedelta(days=90)).isoformat()
    _run_sync(db, [_raw("e1", posted=old)])
    job = db.query(Job).filter_by(source_id="e1").one()
    assert job.is_expired == 1


def test_cross_source_dedupe_by_identity(db):
    _run_sync(db, [_raw("f1")])
    other = _raw("x9")
    other.source = "othersrc"
    sync_mod.FETCHERS["othersrc"] = lambda timeout=20: [other]
    report = sync_mod.sync_sources(db, ["othersrc"])
    assert report["skipped_duplicates"] == 1
    db.query(Job).filter(Job.source == "othersrc").delete()
    db.commit()


def test_fetch_failure_is_reported_not_fatal(db):
    def boom(timeout=20):
        raise RuntimeError("network down")
    sync_mod.FETCHERS["deadsrc"] = boom
    report = sync_mod.sync_sources(db, ["deadsrc"])
    assert "error" in report["sources"]["deadsrc"]
