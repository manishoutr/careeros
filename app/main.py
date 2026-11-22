"""CareerOS API.

Endpoints are grouped by feature: profile, jobs, search, assistant, tailor.
The frontend (app/static) is served at / and only talks to /api/*.
"""
import io
import json
import logging
import time
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from .db import get_db, init_db
from .models import ChatMessage, Job, Profile, TailoredDraft
from .schemas import (ChatRequest, ChatResponse, JobOut, ProfileData,
                      RankedJob, SearchRequest, SearchResponse, SkillGapResponse,
                      SyncResponse, TailorRequest, TailorResponse)
from .config import settings
from .services import assistant as assistant_service
from .services import skillgap as skillgap_service
from .services import tailor as tailor_service
from .services import scheduler, vectorstore
from .services.embeddings import backend_info as embedding_backend_info
from .services.sources.sync import sync_sources
from .services.ingest import ingest_csv
from .services.llm import llm
from .services.parsing import extract_text, parse_resume
from .services.ranking import apply_query_constraints, score_job, understand_query
from .services.retrieval import hybrid_scores

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("careeros")

BASE_DIR = Path(__file__).resolve().parent.parent
SEED_CSV = BASE_DIR / "seed" / "jobs.csv"
SAMPLE_RESUME_TXT = BASE_DIR / "sample_data" / "sample_resume.txt"
STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="CareerOS", version="1.0.0",
              description="AI-powered personalized career agent (learning project)")

# --- Simple reliability metrics (in-memory; see /api/metrics) ---
METRICS = {"requests": 0, "errors": 0, "total_latency_ms": 0.0,
           "ingest_runs": 0, "searches": 0, "assistant_messages": 0,
           "tailored_drafts": 0, "tailor_safety_rejections": 0}


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    METRICS["requests"] += 1
    METRICS["total_latency_ms"] += (time.time() - start) * 1000
    if response.status_code >= 500:
        METRICS["errors"] += 1
    return response


@app.on_event("startup")
def startup() -> None:
    init_db()
    Path(settings.data_dir).mkdir(parents=True, exist_ok=True)
    # Auto-seed the demo catalogue on first run so the demo path is one command.
    db = next(get_db())
    try:
        if not settings.demo_seed:
            _purge_demo_jobs(db)
        _fix_internship_labels(db)
        if settings.demo_seed and SEED_CSV.exists() and db.query(Job).count() == 0:
            with open(SEED_CSV, newline="", encoding="utf-8") as f:
                inserted, skipped = ingest_csv(db, f)
            METRICS["ingest_runs"] += 1
            log.info("seeded %d jobs (%d duplicates skipped)", inserted, skipped)
        # Seed the sample candidate profile on first run so search, match
        # reasons and tailoring work out of the box. Uploading a real resume
        # replaces it.
        if SAMPLE_RESUME_TXT.exists() and db.query(Profile).filter_by(id=1).first() is None:
            profile = parse_resume(SAMPLE_RESUME_TXT.read_text(encoding="utf-8"))
            db.merge(Profile(id=1, name=profile.name, data=profile.model_dump_json()))
            db.commit()
            log.info("seeded sample candidate profile")
    finally:
        db.close()
    scheduler.start()


def _fix_internship_labels(db) -> None:
    """Older rows were labelled internship by substring ("Internal Auditor").
    Re-derive the label from the title for those rows only; the next sync
    refreshes everything else."""
    from .services.sources.base import infer_type_and_level
    n = 0
    for job in db.query(Job).filter(Job.job_type == "internship", Job.source != "seed").all():
        jtype, level = infer_type_and_level(job.title)
        if jtype != "internship":
            job.job_type, job.level = jtype, level
            n += 1
    if n:
        db.commit()
        log.info("relabelled %d listings wrongly marked internship", n)


def _purge_demo_jobs(db) -> None:
    """Real listings only: delete any fictional demo rows left by earlier
    versions, so they cannot reappear in results after a redeploy."""
    demo = db.query(Job).filter(Job.source == "seed").all()
    if not demo:
        return
    for job in demo:
        if vectorstore.available():
            vectorstore.remove(job.id)
        db.delete(job)
    db.commit()
    log.info("removed %d fictional demo listings", len(demo))


# --- helpers -------------------------------------------------------------

def _job_out(job: Job) -> JobOut:
    return JobOut(id=job.id, title=job.title, company=job.company,
                  location=job.location, job_type=job.job_type, level=job.level,
                  skills=job.skills_list(), description=job.description,
                  url=job.url, posted_date=job.posted_date,
                  source=job.source or "seed",
                  last_verified_at=job.last_verified_at or "",
                  is_expired=bool(job.is_expired))


def _get_profile(db: Session):
    row = db.query(Profile).filter_by(id=1).first()
    if row is None:
        return None, None
    return row, ProfileData.model_validate(json.loads(row.data or "{}"))


# --- health / metrics ------------------------------------------------------

@app.get("/api/health")
def health(db: Session = Depends(get_db)):
    active = db.query(Job).filter(Job.is_expired == 0).count()
    return {"status": "ok", "llm_mode": llm.mode,
            "jobs": db.query(Job).count(), "active_jobs": active,
            "demo_listings": "enabled" if settings.demo_seed else "disabled",
            "last_sync_success": scheduler.status(db)["last_success_at"],
            "embeddings": embedding_backend_info(),
            "vectorstore": "pgvector" if vectorstore.available() else "python",
            "db": "postgresql" if settings.database_url.startswith("postgres") else "sqlite"}


@app.get("/api/metrics")
def metrics():
    avg = (METRICS["total_latency_ms"] / METRICS["requests"]) if METRICS["requests"] else 0.0
    return {**METRICS, "avg_latency_ms": round(avg, 2)}


# --- profile ---------------------------------------------------------------

ALLOWED_UPLOADS = (".pdf", ".txt", ".md")


@app.post("/api/profile/resume", response_model=ProfileData)
async def upload_resume(file: UploadFile = File(...), db: Session = Depends(get_db)):
    filename = file.filename or "resume"
    if not filename.lower().endswith(ALLOWED_UPLOADS):
        raise HTTPException(415, f"Unsupported file type. Allowed: {', '.join(ALLOWED_UPLOADS)}")
    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(413, "File too large (max 5 MB)")
    text = extract_text(content, filename)
    if len(text.strip()) < 20:
        raise HTTPException(422, "Could not extract readable text from this file")
    profile = parse_resume(text)
    row = db.query(Profile).filter_by(id=1).first() or Profile(id=1)
    row.name = profile.name
    row.data = profile.model_dump_json()
    db.merge(row)
    db.commit()
    return profile


@app.get("/api/profile", response_model=ProfileData)
def get_profile(db: Session = Depends(get_db)):
    _, profile = _get_profile(db)
    if profile is None:
        raise HTTPException(404, "No profile yet. Upload a resume first.")
    return profile


@app.put("/api/profile", response_model=ProfileData)
def update_profile(data: ProfileData, db: Session = Depends(get_db)):
    """User corrections to the parsed profile are saved verbatim."""
    row = db.query(Profile).filter_by(id=1).first() or Profile(id=1)
    row.name = data.name
    row.data = data.model_dump_json()
    db.merge(row)
    db.commit()
    return data


# --- jobs ------------------------------------------------------------------

@app.post("/api/jobs/ingest")
def ingest(db: Session = Depends(get_db)):
    if not settings.demo_seed:
        raise HTTPException(403, "Demo listings are disabled: CareerOS shows real listings only")
    if not SEED_CSV.exists():
        raise HTTPException(404, "Seed file not found")
    with open(SEED_CSV, newline="", encoding="utf-8") as f:
        inserted, skipped = ingest_csv(db, io.StringIO(f.read()))
    METRICS["ingest_runs"] += 1
    return {"inserted": inserted, "skipped_duplicates": skipped,
            "total": db.query(Job).count()}


@app.get("/api/jobs", response_model=list[JobOut])
def list_jobs(skip: int = 0, limit: int = 200, include_expired: bool = False,
              source: str = "", db: Session = Depends(get_db)):
    q = db.query(Job)
    if not settings.demo_seed:
        q = q.filter(Job.source != "seed")
    if not include_expired:
        q = q.filter(Job.is_expired == 0)
    if source:
        q = q.filter(Job.source == source)
    limit = max(1, min(limit, 500))
    return [_job_out(j) for j in q.order_by(Job.id).offset(max(0, skip)).limit(limit).all()]


@app.post("/api/jobs/sync")
def sync_jobs_endpoint(db: Session = Depends(get_db)):
    """Ask for a refresh of the real job feeds. Runs in the background and is
    rate limited (one run per sync interval), so repeated calls are harmless."""
    result = scheduler.request_sync(db, "external")
    if result == "started":
        METRICS["ingest_runs"] += 1
    return {"result": result, **scheduler.status(db)}


@app.get("/api/jobs/sync/status")
def sync_status(db: Session = Depends(get_db)):
    return scheduler.status(db)


@app.get("/api/jobs/{job_id}/skill-gap", response_model=SkillGapResponse)
def skill_gap(job_id: int, db: Session = Depends(get_db)):
    job = db.query(Job).filter_by(id=job_id).first()
    if job is None:
        raise HTTPException(404, f"Job {job_id} not found")
    _, profile = _get_profile(db)
    matched, missing, coverage, advice = skillgap_service.analyze(profile, job)
    return SkillGapResponse(job=_job_out(job), matched=matched, missing=missing,
                            coverage=coverage, advice=advice)


# --- search ----------------------------------------------------------------

@app.post("/api/search", response_model=SearchResponse)
def search(req: SearchRequest, db: Session = Depends(get_db)):
    METRICS["searches"] += 1
    if settings.auto_sync:
        scheduler.request_sync(db, "schedule")  # no-op unless the data is stale
    qu = understand_query(req.query)
    jobs = vectorstore.candidate_jobs(
        db, req.query, constrained=bool(qu.get("entry_intent") or qu.get("location")))
    if jobs is None:
        jobs = db.query(Job).filter(Job.is_expired == 0).all()
    if not settings.demo_seed:
        jobs = [j for j in jobs if j.source != "seed"]
    if not jobs:
        return SearchResponse(query=req.query, count=0, results=[])
    _, profile = _get_profile(db)
    jobs, constraint_note = apply_query_constraints(jobs, qu)
    if not jobs:
        return SearchResponse(query=req.query, count=0, results=[])
    combined, _parts = hybrid_scores(
        [j.searchable_text() for j in jobs],
        [j.embedding_list() for j in jobs],
        req.query)
    ranked = []
    for job, relevance in zip(jobs, combined):
        scores, reasons = score_job(job, relevance, qu, profile)
        if constraint_note:
            reasons.insert(0, constraint_note)
        ranked.append(RankedJob(job=_job_out(job), scores=scores, reasons=reasons))
    ranked.sort(key=lambda r: r.scores.total, reverse=True)
    top = ranked[: max(1, min(req.k, 50))]
    return SearchResponse(query=req.query, count=len(top), results=top)


# --- assistant ---------------------------------------------------------------

@app.post("/api/assistant/chat", response_model=ChatResponse)
def chat(req: ChatRequest, db: Session = Depends(get_db)):
    METRICS["assistant_messages"] += 1
    if not req.message.strip():
        raise HTTPException(422, "Message must not be empty")
    _, profile = _get_profile(db)
    history = [{"role": m.role, "content": m.content}
               for m in db.query(ChatMessage).order_by(ChatMessage.id.desc()).limit(10)]
    history.reverse()
    result = assistant_service.answer(db, profile, history, req.message)
    db.add(ChatMessage(role="user", content=req.message))
    db.add(ChatMessage(role="assistant", content=result["answer"]))
    db.commit()
    return ChatResponse(answer=result["answer"], mode=result["mode"],
                        tool_trace=result["tool_trace"])


@app.get("/api/assistant/history")
def chat_history(db: Session = Depends(get_db)):
    rows = db.query(ChatMessage).order_by(ChatMessage.id.desc()).limit(50)
    return [{"role": m.role, "content": m.content} for m in reversed(rows)]


# --- tailor ------------------------------------------------------------------

@app.post("/api/tailor", response_model=TailorResponse)
def tailor(req: TailorRequest, db: Session = Depends(get_db)):
    _, profile = _get_profile(db)
    if profile is None:
        raise HTTPException(409, "Upload a resume before tailoring.")
    job = db.query(Job).filter_by(id=req.job_id).first()
    if job is None:
        raise HTTPException(404, f"Job {req.job_id} not found")
    draft, changes, mode = tailor_service.tailor(profile, job)
    violations = tailor_service.validate_draft(draft, profile)
    if violations:
        # Safety rule enforced in code: never save or show an inventing draft.
        METRICS["tailor_safety_rejections"] += 1
        raise HTTPException(500, "Tailored draft failed the no-invention check: "
                                 + "; ".join(violations))
    METRICS["tailored_drafts"] += 1
    db.add(TailoredDraft(job_id=job.id, draft=json.dumps(draft),
                         changes=json.dumps([c.model_dump() for c in changes])))
    db.commit()
    return TailorResponse(job=_job_out(job), draft=draft, changes=changes, mode=mode)


# --- frontend ---------------------------------------------------------------

app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
