"""Shared types and helpers for external job sources."""
import html
import re
from dataclasses import dataclass, field
from typing import List, Optional

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def strip_html(text: str) -> str:
    return _WS_RE.sub(" ", html.unescape(_TAG_RE.sub(" ", text or ""))).strip()


@dataclass
class RawJob:
    source: str
    source_id: str
    title: str
    company: str
    location: str = ""
    job_type: str = ""       # internship / full-time / contract
    level: str = ""          # entry / mid / senior
    skills: List[str] = field(default_factory=list)
    description: str = ""
    url: str = ""            # application URL on the source
    posted_date: str = ""    # ISO date


def infer_type_and_level(title: str, job_types: Optional[List[str]] = None) -> tuple:
    """Best-effort job_type/level from the title and source tags."""
    blob = " ".join([title or ""] + (job_types or [])).lower()
    if "intern" in blob or "working student" in blob or "trainee" in blob:
        return "internship", "entry"
    jtype = "contract" if "contract" in blob or "freelance" in blob else "full-time"
    if any(w in blob for w in ("senior", "sr.", "lead", "principal", "staff")):
        level = "senior"
    elif any(w in blob for w in ("junior", "entry", "graduate", "associate", "fresher")):
        level = "entry"
    elif any(w in blob for w in ("mid", "ii", "2+")):
        level = "mid"
    else:
        level = "entry" if "intern" in blob else ""
    return jtype, level


def skills_from(text: str, lexicon) -> List[str]:
    """Lexicon scan used when a source provides no tags."""
    lowered = " " + (text or "").lower() + " "
    found = []
    for s in lexicon:
        if re.search(r"(?<![a-z0-9+#.])" + re.escape(s) + r"(?![a-z0-9])", lowered):
            found.append(s)
    return found[:12]
