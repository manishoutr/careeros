"""Skill-gap analysis: what a job requires vs what the profile already has.

Deterministic and inspectable: the same lexicon that parses resumes defines
the skills universe, so 'missing' means 'required by the job, absent from
your profile' - never an invented requirement.
"""
from typing import Dict, List, Optional, Tuple

from ..schemas import ProfileData

# Plain-language next steps for the gaps students hit most. Anything not
# listed gets a generic pointer.
_ADVICE: Dict[str, str] = {
    "docker": "Containerize one of your own projects and push the image; a weekend is enough for working knowledge.",
    "kubernetes": "Deploy a small app to a free cluster (minikube or kind) and write the YAML yourself.",
    "aws": "Do the free-tier basics: S3, EC2, IAM; note exact services in your project READMEs.",
    "gcp": "Work through the free tier: Cloud Storage and one compute service.",
    "azure": "Try the free tier: Blob Storage and one app service deployment.",
    "postgresql": "Point an existing project at Postgres instead of SQLite and write one migration.",
    "redis": "Add Redis caching to a small API and measure the difference.",
    "react": "Rebuild one static page as React components with state; that covers the core mental model.",
    "typescript": "Convert one JS project file at a time; strict mode teaches the type system fastest.",
    "go": "Build one small CLI or HTTP service; Go's tour covers the language in a few hours.",
    "rust": "Work through the ownership chapters of the Rust book, then port a small script.",
    "kafka": "Run a local broker and produce/consume messages from a toy service.",
    "graphql": "Add one GraphQL endpoint to a REST project to feel the schema difference.",
    "terraform": "Write a config that creates one cloud resource, plan and apply it.",
    "ci/cd": "Add a GitHub Actions workflow that runs your tests on every push.",
    "machine learning": "Train a small scikit-learn model end to end: split, fit, evaluate.",
    "pytorch": "Recreate a tutorial training loop, then modify the model yourself.",
    "tensorflow": "Recreate a tutorial training loop, then modify the model yourself.",
}


def analyze(profile: Optional[ProfileData], job) -> Tuple[List[str], List[str], float, List[str]]:
    required = [s.lower() for s in job.skills_list()]
    if not required:
        return [], [], 0.0, ["This listing names no specific skills to compare against."]
    have = {s.lower() for s in (profile.skills if profile else [])}
    matched = sorted(set(required) & have)
    missing = sorted(set(required) - have)
    coverage = len(matched) / len(required)
    advice = []
    for skill in missing:
        tip = _ADVICE.get(skill)
        advice.append(f"{skill}: {tip}" if tip else
                      f"{skill}: build one small project that uses it and link it from your profile.")
    if not profile:
        advice.insert(0, "Upload your resume so CareerOS can compare your skills.")
    return matched, missing, round(coverage, 3), advice
