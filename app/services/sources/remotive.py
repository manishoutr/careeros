"""Remotive remote-jobs API (https://remotive.com/api/remote-jobs).

Their API legal notice allows developers to share jobs further as long as
listings link back to the Remotive job URL - which is exactly what we store
as the application URL and show as the source.
"""
from typing import List

import requests

from .base import RawJob, infer_type_and_level, strip_html

API = "https://remotive.com/api/remote-jobs"
SOURCE = "remotive"


def fetch(limit: int = 100, timeout: int = 20) -> List[RawJob]:
    resp = requests.get(API, params={"limit": limit}, timeout=timeout)
    resp.raise_for_status()
    out = []
    for j in resp.json().get("jobs", []):
        title = (j.get("title") or "").strip()
        company = (j.get("company_name") or "").strip()
        if not title or not company:
            continue
        tags = [t.lower() for t in (j.get("tags") or [])][:12]
        jtype, level = infer_type_and_level(title, [j.get("job_type") or ""])
        out.append(RawJob(
            source=SOURCE,
            source_id=str(j.get("id") or ""),
            title=title,
            company=company,
            location=(j.get("candidate_required_location") or "Remote").strip() or "Remote",
            job_type=jtype,
            level=level,
            skills=tags,
            description=strip_html(j.get("description") or "")[:4000],
            url=j.get("url") or "",
            posted_date=(j.get("publication_date") or "")[:10],
        ))
    return out
