"""Skill-gap analysis: matched/missing/coverage/advice from profile vs job."""
from app.schemas import ExperienceItem, ProfileData
from app.services.skillgap import analyze


class FakeJob:
    def __init__(self, skills):
        self._skills = skills
    def skills_list(self):
        return list(self._skills)


PROFILE = ProfileData(
    name="Aarav",
    skills=["python", "fastapi", "postgresql", "docker"],
    experience=[ExperienceItem(title="Backend Intern", company="Odisha Web Works",
                               period="Jun 2025 - Aug 2025", years=0.2)],
)


def test_matched_missing_and_coverage():
    job = FakeJob(["python", "fastapi", "kubernetes", "aws"])
    matched, missing, coverage, advice = analyze(PROFILE, job)
    assert matched == ["fastapi", "python"]
    assert missing == ["aws", "kubernetes"]
    assert coverage == 0.5
    assert len(advice) == 2
    assert all(":" in a for a in advice)  # each gap carries a concrete tip


def test_no_profile_still_reports_gaps():
    job = FakeJob(["python", "aws"])
    matched, missing, coverage, advice = analyze(None, job)
    assert matched == [] and missing == ["aws", "python"]
    assert any("resume" in a.lower() for a in advice)


def test_job_without_skills_is_honest():
    matched, missing, coverage, advice = analyze(PROFILE, FakeJob([]))
    assert coverage == 0.0
    assert advice and "no specific skills" in advice[0]
