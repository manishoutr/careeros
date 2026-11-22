"""Public Greenhouse job-board APIs for individual companies.

These are the same JSON endpoints a candidate's browser hits when viewing a
company's careers board; each listing keeps its original application URL.
The company list is configuration (CAREEROS_GREENHOUSE_BOARDS), not hidden
in code.
"""
import os
from typing import List

import requests

from .base import RawJob, infer_type_and_level, strip_html

SOURCE = "greenhouse"
API = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"

# Verified public boards (checked 2026-11). Override with
# CAREEROS_GREENHOUSE_BOARDS="slug1,slug2".
DEFAULT_BOARDS = ["airbnb", "cloudflare", "figma", "stripe", "databricks", "gitlab",
                  "coinbase", "razorpaysoftwareprivatelimited", "groww", "druva",
                  "mongodb", "twilio", "okta", "zscaler", "datadog", "elastic"]


def configured_boards() -> List[str]:
    raw = os.getenv("CAREEROS_GREENHOUSE_BOARDS")
    return [s.strip() for s in raw.split(",") if s.strip()] if raw else list(DEFAULT_BOARDS)


MAX_PER_BOARD = 60  # keeps the free-tier catalogue bounded
_INDIA = ("india", "bengaluru", "bangalore", "mumbai", "hyderabad", "pune",
          "delhi", "gurgaon", "gurugram", "noida", "chennai", "kolkata")


def _priority(job: dict) -> tuple:
    """Entry-level and India/remote roles first, then most recently updated.
    Sorted descending, so True sorts before False."""
    loc = ((job.get("location") or {}).get("name") or "").lower()
    title = (job.get("title") or "").lower()
    entry = any(w in title for w in ("intern", "graduate", "junior", "entry", "associate"))
    india = any(w in loc for w in _INDIA)
    return (entry, india, "remote" in loc, job.get("updated_at") or "")


def fetch(slugs: List[str] = None, timeout: int = 20) -> List[RawJob]:
    out = []
    for slug in (slugs or configured_boards()):
        resp = requests.get(API.format(slug=slug), timeout=timeout)
        if resp.status_code == 404:
            continue  # board moved; skip rather than fail the whole sync
        resp.raise_for_status()
        jobs = sorted(resp.json().get("jobs", []),
                      key=_priority, reverse=True)
        for j in jobs[:MAX_PER_BOARD]:
            title = (j.get("title") or "").strip()
            if not title:
                continue
            loc = (j.get("location") or {}).get("name") or ""
            jtype, level = infer_type_and_level(title)
            out.append(RawJob(
                source=SOURCE,
                source_id=f"{slug}:{j.get('id')}",
                title=title,
                company=slug.capitalize(),
                location=loc,
                job_type=jtype,
                level=level,
                skills=[],  # boards give no tags; the pipeline lexicon-scans below
                description="",  # content=false keeps the sync light; title+dept indexed
                url=j.get("absolute_url") or "",
                posted_date=(j.get("updated_at") or "")[:10],
            ))
    return out
