"""Pydantic schemas: API contracts and validation for model output."""
from typing import List, Optional

from pydantic import BaseModel, Field


class ExperienceItem(BaseModel):
    title: str = ""
    company: str = ""
    period: str = ""
    years: float = 0.0


class EducationItem(BaseModel):
    degree: str = ""
    institution: str = ""
    year: str = ""


class ProfileData(BaseModel):
    """Structured candidate profile. This is also the schema that Claude's
    extraction output is validated against before anything is saved."""
    name: str = ""
    skills: List[str] = Field(default_factory=list)
    experience: List[ExperienceItem] = Field(default_factory=list)
    education: List[EducationItem] = Field(default_factory=list)
    preferences: dict = Field(default_factory=lambda: {"locations": [], "roles": []})


class JobOut(BaseModel):
    id: int
    title: str
    company: str
    location: str
    job_type: str
    level: str
    skills: List[str]
    description: str
    url: str
    posted_date: str
    source: str = "seed"
    last_verified_at: str = ""
    is_expired: bool = False


class SkillGapResponse(BaseModel):
    """Job requirements vs the candidate profile."""
    job: JobOut
    matched: List[str]          # required skills the candidate has
    missing: List[str]          # required skills not in the profile
    coverage: float             # matched / required (0-1)
    advice: List[str]           # one plain suggestion per missing skill


class SyncResponse(BaseModel):
    fetched: int
    inserted: int
    updated: int
    skipped_duplicates: int
    expired: int
    sources: dict               # per-source counts or error message


class ScoreBreakdown(BaseModel):
    relevance: float
    skills: float
    location: float
    experience: float
    total: float


class SearchRequest(BaseModel):
    query: str
    k: int = 10


class RankedJob(BaseModel):
    job: JobOut
    scores: ScoreBreakdown
    reasons: List[str]


class SearchResponse(BaseModel):
    query: str
    count: int
    results: List[RankedJob]


class ChatRequest(BaseModel):
    message: str


class ToolTrace(BaseModel):
    tool: str
    input: dict
    output_summary: str


class ChatResponse(BaseModel):
    answer: str
    mode: str  # "claude" or "offline"
    tool_trace: List[ToolTrace] = Field(default_factory=list)


class ChangeEntry(BaseModel):
    section: str
    change: str   # reorder / emphasize / keyword / summary
    before: str
    after: str
    source: str   # where the supporting fact came from


class TailorRequest(BaseModel):
    job_id: int


class TailorResponse(BaseModel):
    job: JobOut
    draft: dict
    changes: List[ChangeEntry]
    mode: str
