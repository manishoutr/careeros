"""Arbeitnow job board API (https://www.arbeitnow.com/job-board-api).

Free public JSON feed; listings keep their original application URL and the
source is shown in the UI.
"""
from datetime import datetime, timezone
from typing import List

import requests

from .base import RawJob, infer_type_and_level, strip_html

API = "https://www.arbeitnow.com/api/job-board-api"
SOURCE = "arbeitnow"


def fetch(timeout: int = 20) -> List[RawJob]:
    resp = requests.get(API, timeout=timeout)
    resp.raise_for_status()
    out = []
    for j in resp.json().get("data", []):
        title = (j.get("title") or "").strip()
        company = (j.get("company_name") or "").strip()
        if not title or not company:
            continue
        tags = [t.lower() for t in (j.get("tags") or [])][:12]
        jtype, level = infer_type_and_level(title, j.get("job_types") or [])
        location = (j.get("location") or "").strip()
        if j.get("remote"):
            location = (location + " / Remote").strip(" /") if location else "Remote"
        created = j.get("created_at")
        posted = (datetime.fromtimestamp(created, tz=timezone.utc).date().isoformat()
                  if isinstance(created, (int, float)) else "")
        out.append(RawJob(
            source=SOURCE,
            source_id=str(j.get("slug") or ""),
            title=title,
            company=company,
            location=location,
            job_type=jtype,
            level=level,
            skills=tags,
            description=strip_html(j.get("description") or "")[:4000],
            url=j.get("url") or "",
            posted_date=posted,
        ))
    return out
