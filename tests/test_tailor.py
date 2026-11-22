"""Safety: tailored drafts must never invent qualifications."""
from app.schemas import ProfileData
from app.services.tailor import tailor, validate_draft


class FakeJob:
    def __init__(self, skills):
        self.title = "Backend Developer Intern"
        self.company = "Zoho"
        self._skills = skills

    def skills_list(self):
        return self._skills


PROFILE = ProfileData(
    name="Aarav Sharma",
    skills=["python", "fastapi", "docker"],
    experience=[{"title": "Backend Intern", "company": "Odisha Web Works",
                 "period": "Jun 2025 - Aug 2025", "years": 0.2}],
    education=[{"degree": "B.Tech Computer Science",
                "institution": "OUTR", "year": "2027"}],
)


def test_draft_skills_are_subset_of_profile():
    job = FakeJob(["python", "fastapi", "kubernetes"])  # kubernetes NOT in profile
    draft, changes, mode = tailor(PROFILE, job)
    assert validate_draft(draft, PROFILE) == []
    assert "kubernetes" not in draft["skills"]


def test_matched_skills_come_first():
    job = FakeJob(["docker"])
    draft, _, _ = tailor(PROFILE, job)
    assert draft["skills"][0] == "docker"


def test_every_change_has_a_source():
    job = FakeJob(["python"])
    _, changes, _ = tailor(PROFILE, job)
    assert changes
    assert all(c.source for c in changes)


def test_validator_catches_invented_skill():
    draft = {"skills": ["python", "rocket-science"], "experience": [], "education": []}
    violations = validate_draft(draft, PROFILE)
    assert any("rocket-science" in v for v in violations)


def test_validator_catches_invented_employer():
    draft = {"skills": [], "education": [],
             "experience": [{"title": "CEO", "company": "FakeCorp", "period": "", "years": 1}]}
    violations = validate_draft(draft, PROFILE)
    assert any("FakeCorp" in v for v in violations)
