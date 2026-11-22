"""Fetch jobs from the configured external sources into the catalogue.

Usage: python3 scripts/fetch_jobs.py [source ...]   (default: all sources)
Sources: remotive (free API, remote jobs), arbeitnow (free API),
greenhouse (public company boards; CAREEROS_GREENHOUSE_BOARDS overrides).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import SessionLocal, init_db  # noqa: E402
from app.services.sources.sync import sync_sources  # noqa: E402


def main() -> int:
    names = sys.argv[1:] or None
    init_db()
    db = SessionLocal()
    try:
        report = sync_sources(db, names)
    finally:
        db.close()
    for k, v in report.items():
        print(f"{k}: {v}")
    return 0 if not any(str(v).startswith("error") for v in report["sources"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
