"""Bounded tools the assistant may call, plus the Claude tool spec.

The assistant never answers from thin air: it must call these tools and
ground its answer in what they return. The tool set is deliberately small
and read-only.
"""
import json
from typing import Optional

from ..models import Job
from ..schemas import ProfileData
from . import vectorstore
from .ranking import apply_query_constraints, score_job, understand_query
from .retrieval import hybrid_scores
from .skillgap import analyze as skill_gap_analyze

SYSTEM = (
    "You are CareerOS, a career assistant. Answer only using the candidate "
    "profile and job data returned by the tools. If the tools return nothing "
    "relevant, say so instead of guessing. Keep answers short, concrete and "
    "friendly. Mention specific job titles and companies when recommending.")

TOOLS = [
    {
        "name": "search_jobs",
        "description": "Search the job catalogue with a natural-language query. "
                       "Returns ranked jobs with match explanations.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Job search query"},
                "k": {"type": "integer", "description": "How many jobs to return", "default": 5},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_candidate_profile",
        "description": "Get the candidate's parsed profile: skills, experience, "
                       "education and preferences.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "analyze_skill_gap",
        "description": "Compare one job's required skills against the candidate "
                       "profile: matched skills, gaps and how to close them.",
        "input_schema": {
            "type": "object",
            "properties": {
                "job_id": {"type": "integer", "description": "Job id from a search result"},
            },
            "required": ["job_id"],
        },
    },
]


def search_jobs_tool(db, profile: Optional[ProfileData], query: str, k: int = 5) -> str:
    qu = understand_query(query)
    jobs = vectorstore.candidate_jobs(
        db, query, constrained=bool(qu.get("entry_intent") or qu.get("location")))
    if jobs is None:
        jobs = db.query(Job).filter(Job.is_expired == 0).all()
    if not jobs:
        return "The job catalogue is empty."
    jobs, constraint_note = apply_query_constraints(jobs, qu)
    if not jobs:
        return ("No jobs in the catalogue satisfy the query's constraints. "
                + (constraint_note or ""))
    texts = [j.searchable_text() for j in jobs]
    combined, _ = hybrid_scores(texts, [j.embedding_list() for j in jobs], query)
    scored = []
    for job, rel in zip(jobs, combined):
        scores, reasons = score_job(job, rel, qu, profile)
        scored.append((job, scores, reasons))
    scored.sort(key=lambda t: t[1].total, reverse=True)
    lines = []
    if constraint_note:
        lines.append(constraint_note)
    for job, scores, reasons in scored[:k]:
        lines.append(json.dumps({
            "id": job.id, "title": job.title, "company": job.company,
            "location": job.location, "type": job.job_type,
            "skills": job.skills_list(), "match_score": scores.total,
            "reasons": reasons}))
    return "\n".join(lines)


def profile_tool(profile: Optional[ProfileData]) -> str:
    if profile is None:
        return "No candidate profile has been uploaded yet."
    return profile.model_dump_json()


def skill_gap_tool(db, profile: Optional[ProfileData], job_id: int) -> str:
    job = db.query(Job).filter_by(id=job_id).first()
    if job is None:
        return f"Job {job_id} not found."
    matched, missing, coverage, advice = skill_gap_analyze(profile, job)
    return json.dumps({
        "job": f"{job.title} at {job.company}",
        "matched": matched, "missing": missing,
        "coverage": coverage, "advice": advice})


def executor(db, profile: Optional[ProfileData]):
    def run(name: str, inputs: dict) -> str:
        if name == "search_jobs":
            return search_jobs_tool(db, profile, inputs.get("query", ""),
                                    int(inputs.get("k", 5)))
        if name == "get_candidate_profile":
            return profile_tool(profile)
        if name == "analyze_skill_gap":
            return skill_gap_tool(db, profile, int(inputs.get("job_id", 0)))
        return f"Unknown tool: {name}"
    return run
