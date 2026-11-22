"""Grounded career assistant.

The assistant never answers from thin air: it must call bounded tools
(search_jobs, get_candidate_profile) and ground its answer in what those
tools return. With Claude configured, tool selection is the model's job;
offline, a transparent rule picks the tool and the answer is templated -
and labelled offline so nobody mistakes it for model output.
"""
import json
from typing import Optional

from ..models import Job
from ..schemas import ProfileData
from .llm import llm
from .ranking import score_job, understand_query
from .retrieval import hybrid_scores

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
]

SYSTEM = (
    "You are CareerOS, a career assistant. Answer only using the candidate "
    "profile and job data returned by the tools. If the tools return nothing "
    "relevant, say so instead of guessing. Keep answers short, concrete and "
    "friendly. Mention specific job titles and companies when recommending.")


def _search_jobs_tool(db, profile: Optional[ProfileData], query: str, k: int = 5) -> str:
    jobs = db.query(Job).all()
    if not jobs:
        return "The job catalogue is empty."
    qu = understand_query(query)
    texts = [f"{j.title} {j.company} {j.location} {' '.join(j.skills_list())} {j.description}"
             for j in jobs]
    combined, _ = hybrid_scores(texts, [j.embedding_list() for j in jobs], query)
    ranked = sorted(zip(jobs, combined), key=lambda t: t[1], reverse=True)[:k]
    lines = []
    for job, rel in ranked:
        scores, reasons = score_job(job, rel, qu, profile)
        lines.append(json.dumps({
            "id": job.id, "title": job.title, "company": job.company,
            "location": job.location, "type": job.job_type,
            "skills": job.skills_list(), "match_score": scores.total,
            "reasons": reasons}))
    return "\n".join(lines)


def _profile_tool(profile: Optional[ProfileData]) -> str:
    if profile is None:
        return "No candidate profile has been uploaded yet."
    return profile.model_dump_json()


def _offline_answer(db, profile: Optional[ProfileData], message: str) -> dict:
    """Deterministic fallback: pick a tool by simple rules, template the answer."""
    lowered = message.lower()
    trace = []
    if any(w in lowered for w in ("my skills", "my profile", "my experience",
                                  "who am i", "my resume", "about me")):
        out = _profile_tool(profile)
        trace.append({"tool": "get_candidate_profile", "input": {},
                      "output_summary": out[:200]})
        if profile is None:
            answer = "You haven't uploaded a resume yet, so I don't have a profile. Upload one from the Profile tab."
        else:
            answer = (f"Here's your profile: {len(profile.skills)} skills "
                      f"(e.g. {', '.join(profile.skills[:6]) or 'none detected'}), "
                      f"{len(profile.experience)} experience entries and "
                      f"{len(profile.education)} education entries. "
                      "You can correct any field in the Profile tab.")
        return {"answer": answer, "tool_trace": trace}

    out = _search_jobs_tool(db, profile, message, k=3)
    trace.append({"tool": "search_jobs", "input": {"query": message, "k": 3},
                  "output_summary": out[:200]})
    jobs = [json.loads(ln) for ln in out.splitlines()] if out.startswith("[") or "{" in out else []
    if not jobs:
        return {"answer": "I couldn't find matching jobs in the catalogue. "
                          "Try different keywords or ingest more jobs.", "tool_trace": trace}
    recs = []
    for j in jobs:
        reason = j["reasons"][0] if j["reasons"] else "good overall match"
        recs.append(f"- {j['title']} at {j['company']} ({j['location']}) - {reason}")
    answer = "Top matches from the catalogue:\n" + "\n".join(recs)
    return {"answer": answer, "tool_trace": trace}


def answer(db, profile: Optional[ProfileData], history: list, message: str) -> dict:
    """Answer one user message. Returns {answer, mode, tool_trace}."""

    def executor(name: str, inputs: dict) -> str:
        if name == "search_jobs":
            return _search_jobs_tool(db, profile, inputs.get("query", ""),
                                     int(inputs.get("k", 5)))
        if name == "get_candidate_profile":
            return _profile_tool(profile)
        return f"Unknown tool: {name}"

    if llm.enabled:
        messages = [{"role": h["role"], "content": h["content"]} for h in history[-10:]]
        messages.append({"role": "user", "content": message})
        result = llm.chat_with_tools(SYSTEM, messages, TOOLS, executor)
        if result is not None:
            return {"answer": result["answer"], "mode": "claude",
                    "tool_trace": result["tool_trace"]}

    result = _offline_answer(db, profile, message)
    result["mode"] = "offline"
    return result
