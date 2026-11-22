"""Real-jobs-only behaviour and the automatic refresh guard rails. No network."""
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone

import pytest

os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tempfile.mkdtemp(), "auto.db")

from app.config import settings  # noqa: E402
from app.db import SessionLocal, init_db  # noqa: E402
from app.models import Job, SyncRun  # noqa: E402
from app.services import scheduler  # noqa: E402
from app.services.sources import sync as sync_mod  # noqa: E402
from app.services.sources.base import RawJob  # noqa: E402


@pytest.fixture()
def db():
    init_db()
    s = SessionLocal()
    s.query(SyncRun).delete()
    s.query(Job).delete()
    s.commit()
    yield s
    s.close()


def _fmt(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def test_startup_purges_demo_rows_when_real_only(db, monkeypatch):
    from app import main
    db.add(Job(dedupe_key="x1", title="Fake", company="Nowhere", source="seed"))
    db.add(Job(dedupe_key="x2", title="Real", company="Acme", source="remotive"))
    db.commit()
    monkeypatch.setattr(settings, "demo_seed", False)
    main._purge_demo_jobs(db)
    left = [j.source for j in db.query(Job).all()]
    assert left == ["remotive"]


def test_sync_endpoint_is_rate_limited(db):
    assert scheduler.is_due(db)
    db.add(SyncRun(started_at=_fmt(datetime.now(timezone.utc) - timedelta(hours=1)),
                   finished_at=_fmt(datetime.now(timezone.utc)), status="ok", report="{}"))
    db.commit()
    assert not scheduler.is_due(db)
    assert scheduler.request_sync(db, "external") == "fresh"


def test_due_after_interval(db):
    old = datetime.now(timezone.utc) - timedelta(hours=settings.sync_interval_hours + 1)
    db.add(SyncRun(started_at=_fmt(old), finished_at=_fmt(old), status="ok", report="{}"))
    db.commit()
    assert scheduler.is_due(db)


def test_interval_floor_protects_sources():
    assert settings.sync_interval_hours >= 6  # Remotive asks for max 4 requests a day


def test_empty_source_response_does_not_expire_listings(db):
    raw = RawJob(source="testsrc", source_id="a", title="Backend Intern", company="Acme",
                 location="Remote", url="https://jobs.example/a",
                 posted_date=datetime.now().date().isoformat())
    sync_mod.FETCHERS["testsrc"] = lambda timeout=20: [raw]
    sync_mod.sync_sources(db, ["testsrc"])
    sync_mod.FETCHERS["testsrc"] = lambda timeout=20: []
    report = sync_mod.sync_sources(db, ["testsrc"])
    assert report["expired"] == 0
    assert db.query(Job).filter_by(source="testsrc").one().is_expired == 0


def test_status_reports_freshness(db):
    now = datetime.now(timezone.utc)
    db.add(SyncRun(started_at=_fmt(now), finished_at=_fmt(now), status="ok",
                   report=json.dumps({"sources": {"remotive": 5}})))
    db.commit()
    st = scheduler.status(db)
    assert st["last_success_at"] and st["sources"] == {"remotive": 5}
