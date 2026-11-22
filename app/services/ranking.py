"""Explainable ranking.

Each job is scored on four independent components - relevance, skills,
location, experience - and every component produces a human-readable reason.
The UI shows the breakdown, so recommendations are inspectable instead of a
single opaque number. Weights are constants on purpose: they are easy to
discuss in an interview and easy to tune.
"""
import re
from typing import Dict, List, Optional, Tuple

from ..schemas import ProfileData, ScoreBreakdown
from .embeddings import STOPWORDS, tokenize
from .parsing import SKILLS_LEXICON

WEIGHTS = {"relevance": 0.40, "skills": 0.30, "location": 0.15, "experience": 0.15}

# Cities we recognise in queries. Extending this list improves location
# understanding without touching scoring code.
KNOWN_LOCATIONS = {
    "india": "India", "bangalore": "Bangalore", "bengaluru": "Bangalore",
    "hyderabad": "Hyderabad", "pune": "Pune", "mumbai": "Mumbai",
    "delhi": "Delhi", "noida": "Noida", "gurgaon": "Gurgaon",
    "chennai": "Chennai", "kolkata": "Kolkata", "bhubaneswar": "Bhubaneswar",
    "remote": "Remote",
}

# Query-only stopwords on top of the shared set: words that say "this is a
# job search" without saying which job.
_QUERY_STOPWORDS = STOPWORDS | {
    "me", "my", "i", "job", "jobs", "role", "roles", "looking", "find",
    "search", "show", "any", "some", "internship", "internships",
    "position", "positions", "opening", "openings", "intern"}


class QueryUnderstanding(dict):
    """What we extracted from the natural-language query."""
    skills: List[str]
    location: Optional[str]
    terms: List[str]


def understand_query(query: str) -> QueryUnderstanding:
    lowered = query.lower()
    skills = [s for s in SKILLS_LEXICON
              if re.search(r"(?<![a-z0-9+#.])" + re.escape(s) + r"(?![a-z0-9])", lowered)]
    location = None
    for key, canonical in KNOWN_LOCATIONS.items():
        if re.search(r"\b" + re.escape(key) + r"\b", lowered):
            location = canonical
            break
    terms = [t for t in tokenize(query)
             if t not in _QUERY_STOPWORDS and t not in skills
             and t not in KNOWN_LOCATIONS]
    return QueryUnderstanding(skills=skills, location=location, terms=terms)


def apply_query_constraints(jobs, qu: QueryUnderstanding):
    """Hard constraints from the query, applied BEFORE scoring.

    "Remote" is a real constraint, not a hint: when the query asks for remote
    roles, non-remote jobs are excluded entirely instead of silently ranking
    below remote ones. Returns (filtered_jobs, note_or_None).
    """
    if (qu.get("location") or "").lower() == "remote":
        remote = [j for j in jobs if "remote" in (j.location or "").lower()]
        return remote, (f"Remote requested: showing only remote roles "
                        f"({len(remote)} of {len(jobs)} in the catalogue).")
    return jobs, None


def _norm_skills(skills: List[str]) -> set:
    return {s.lower() for s in skills}


def _experience_fit(job_level: str, job_type: str, candidate_years: float) -> Tuple[float, str]:
    """Entry-level friendly: a student matches internships/entry roles."""
    level = (job_level or "").lower()
    jtype = (job_type or "").lower()
    if jtype == "internship" or level == "entry":
        if candidate_years <= 2:
            return 1.0, "Role is entry-level/internship, which fits the candidate's experience."
        return 0.8, "Role is entry-level; candidate may be overqualified, which is usually fine."
    if level == "mid":
        if candidate_years >= 2:
            return 0.9, "Mid-level role matches the candidate's experience."
        return 0.35, f"Mid-level role typically expects 2+ years; candidate has ~{candidate_years:.1f}."
    if level == "senior":
        if candidate_years >= 5:
            return 0.9, "Senior role matches the candidate's experience."
        return 0.15, f"Senior role typically expects 5+ years; candidate has ~{candidate_years:.1f}."
    return 0.6, "Role seniority is unspecified; assumed neutral fit."


def score_job(job, retrieval_relevance: float, qu: QueryUnderstanding,
              profile: Optional[ProfileData]) -> Tuple[ScoreBreakdown, List[str]]:
    """`job` is the ORM Job row. Returns the breakdown and reasons."""
    reasons: List[str] = []
    job_skills = _norm_skills(job.skills_list())

    # 1. Relevance comes from the retrieval stage (BM25 + vector hybrid).
    relevance = max(0.0, min(1.0, retrieval_relevance))
    matched_terms = [t for t in qu["terms"]
                     if t in (job.title + " " + job.description).lower()]
    if matched_terms:
        reasons.append("Matched query terms: " + ", ".join(sorted(set(matched_terms))[:5]) + ".")

    # 2. Skills overlap between the job and (query skills + profile skills).
    candidate_skills = _norm_skills(profile.skills) if profile else set()
    wanted = set(qu["skills"]) | candidate_skills
    overlap = sorted(job_skills & wanted)
    skills_score = len(overlap) / len(job_skills) if job_skills else 0.0
    if overlap:
        reasons.append("Candidate/query skills match: " + ", ".join(overlap[:6]) + ".")
    elif job_skills:
        reasons.append("No overlap between the job's required skills and the candidate profile.")

    # 3. Location.
    job_loc = (job.location or "").lower()
    preferred = {l.lower() for l in (profile.preferences.get("locations", []) if profile else [])}
    wanted_loc = (qu["location"] or "").lower()
    if wanted_loc and wanted_loc in job_loc:
        location_score = 1.0
        reasons.append(f"Location matches the query ({job.location}).")
    elif job_loc and any(p in job_loc for p in preferred):
        location_score = 0.9
        reasons.append(f"Location matches the candidate's preferences ({job.location}).")
    elif "remote" in job_loc:
        location_score = 0.7
        reasons.append("Role is remote, so location is flexible.")
    elif wanted_loc == "india" and any(
            c in job_loc for c in ("india", "bangalore", "bengaluru", "hyderabad", "pune",
                                   "mumbai", "delhi", "noida", "gurgaon", "chennai",
                                   "kolkata", "bhubaneswar")):
        location_score = 0.8
        reasons.append(f"Role is in India ({job.location}).")
    else:
        location_score = 0.2
        reasons.append(f"Location ({job.location or 'unspecified'}) does not match a stated preference.")

    # 4. Experience fit.
    candidate_years = sum(e.years for e in profile.experience) if profile else 0.0
    exp_score, exp_reason = _experience_fit(job.level, job.job_type, candidate_years)
    reasons.append(exp_reason)

    total = (WEIGHTS["relevance"] * relevance + WEIGHTS["skills"] * skills_score
             + WEIGHTS["location"] * location_score + WEIGHTS["experience"] * exp_score)
    scores = ScoreBreakdown(relevance=round(relevance, 3),
                            skills=round(skills_score, 3),
                            location=round(location_score, 3),
                            experience=round(exp_score, 3),
                            total=round(total, 3))
    return scores, reasons
