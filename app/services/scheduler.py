"""Automatic refresh of real job feeds.

Three triggers share one guarded entry point, `request_sync`:
- a background thread started with the app (checks every 15 minutes);
- a lazy check when someone searches and the data is stale;
- an external ping (POST /api/jobs/sync, e.g. the scheduled GitHub Action),
  which is what wakes a sleeping free-tier host.
Every trigger is subject to the same cooldown (`sync_interval_hours`, never
under 6 hours because Remotive asks for at most 4 requests a day), so the
open endpoint cannot be used to hammer the sources. Only one sync runs at a
time. Runs are recorded in the sync_runs table.
"""
import json
import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

from ..config import settings
from ..models import Job, SyncRun

log = logging.getLogger("careeros.scheduler")
_lock = threading.Lock()
_started = False


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(ts: str) -> Optional[datetime]:
    try:
        return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def last_run(db) -> Optional[SyncRun]:
    return db.query(SyncRun).order_by(SyncRun.id.desc()).first()


def last_success(db) -> Optional[SyncRun]:
    return (db.query(SyncRun).filter(SyncRun.status.in_(["ok", "partial"]))
            .order_by(SyncRun.id.desc()).first())


def is_due(db) -> bool:
    """True when no run started within the interval (running counts)."""
    run = last_run(db)
    if run is None:
        return True
    started = _parse(run.started_at)
    if started is None:
        return True
    if run.status == "running" and _now() - started < timedelta(minutes=30):
        return False
    return _now() - started >= timedelta(hours=settings.sync_interval_hours)


def status(db) -> Dict:
    ok = last_success(db)
    run = last_run(db)
    nxt = None
    if run is not None and _parse(run.started_at):
        nxt = _iso(_parse(run.started_at) + timedelta(hours=settings.sync_interval_hours))
    real = db.query(Job).filter(Job.source != "seed", Job.is_expired == 0).count()
    return {
        "auto_sync": settings.auto_sync,
        "interval_hours": settings.sync_interval_hours,
        "last_run_status": run.status if run else None,
        "last_run_started_at": run.started_at if run else None,
        "last_success_at": ok.finished_at if ok else None,
        "next_due_at": nxt,
        "real_active_jobs": real,
        "sources": json.loads(ok.report or "{}").get("sources", {}) if ok else {},
    }


def _run(trigger: str) -> None:
    from ..db import SessionLocal
    from .sources.sync import sync_sources
    db = SessionLocal()
    try:
        run = SyncRun(started_at=_iso(_now()), trigger=trigger, status="running")
        db.add(run)
        db.commit()
        try:
            report = sync_sources(db)
            errs = [v for v in report["sources"].values() if str(v).startswith("error")]
            ok_sources = len(report["sources"]) - len(errs)
            run.status = "failed" if ok_sources == 0 else ("partial" if errs else "ok")
            run.report = json.dumps(report)
        except Exception as e:  # never kill the thread
            log.exception("sync failed")
            db.rollback()
            run = db.merge(run)
            run.status = "failed"
            run.report = json.dumps({"error": str(e)})
        run.finished_at = _iso(_now())
        db.commit()
        log.info("sync %s: %s", trigger, run.status)
    finally:
        db.close()
        _lock.release()


def request_sync(db, trigger: str, force: bool = False) -> str:
    """Start a background sync if allowed. Returns 'started', 'fresh' or 'busy'."""
    if not force and not is_due(db):
        return "fresh"
    if not _lock.acquire(blocking=False):
        return "busy"
    threading.Thread(target=_run, args=(trigger,), daemon=True, name="careeros-sync").start()
    return "started"


def _loop() -> None:
    from ..db import SessionLocal
    time.sleep(20)  # let the app finish booting
    first = True
    while True:
        try:
            db = SessionLocal()
            try:
                request_sync(db, "startup" if first else "schedule")
            finally:
                db.close()
        except Exception:
            log.exception("scheduler tick failed")
        first = False
        time.sleep(15 * 60)


def start() -> None:
    global _started
    if _started or not settings.auto_sync:
        return
    _started = True
    threading.Thread(target=_loop, daemon=True, name="careeros-scheduler").start()
