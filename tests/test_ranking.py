"""Ranking: component scores stay in range and reasons are always produced."""
from app.schemas import ProfileData
from app.services.ranking import score_job, understand_query


class FakeJob:
    def __init__(self):
        self.title = "Backend Developer Intern"
        self.company = "Zoho"
        self.location = "Chennai"
        self.job_type = "internship"
        self.level = "entry"
        self._skills = ["python", "fastapi", "postgresql"]
        self.description = "Build REST APIs with FastAPI and PostgreSQL"

    def skills_list(self):
        return self._skills


PROFILE = ProfileData(
    name="Aarav Sharma",
    skills=["python", "fastapi", "docker"],
    experience=[],
    education=[],
    preferences={"locations": ["Chennai", "Bangalore"], "roles": []},
)


def test_component_scores_in_range():
    qu = understand_query("backend internships using Python in India")
    scores, reasons = score_job(FakeJob(), 0.8, qu, PROFILE)
    for value in (scores.relevance, scores.skills, scores.location,
                  scores.experience, scores.total):
        assert 0.0 <= value <= 1.0
    assert reasons  # explainability: every result carries reasons


def test_skills_overlap_counts_profile_and_query():
    qu = understand_query("python backend internship")
    scores, reasons = score_job(FakeJob(), 0.5, qu, PROFILE)
    # python + fastapi overlap out of 3 required skills
    assert scores.skills == round(2 / 3, 3)
    assert any("python" in r for r in reasons)


def test_location_mismatch_is_penalised():
    job = FakeJob()
    job.location = "Berlin"  # neither in the query nor in preferences
    qu = understand_query("python internship in Mumbai")
    scores, _ = score_job(job, 0.5, qu, PROFILE)
    assert scores.location < 0.5


def test_preferred_location_is_rewarded():
    qu = understand_query("python internship in Mumbai")  # query misses, preference hits
    scores, _ = score_job(FakeJob(), 0.5, qu, PROFILE)
    assert scores.location >= 0.9  # Chennai is a stated preference


def test_senior_role_penalised_for_student():
    job = FakeJob()
    job.job_type, job.level = "full-time", "senior"
    qu = understand_query("backend engineer")
    scores, reasons = score_job(job, 0.5, qu, PROFILE)
    assert scores.experience < 0.5
    assert any("senior" in r.lower() or "5+" in r for r in reasons)


def test_query_understanding_finds_skills_and_location():
    qu = understand_query("backend internships using Python in India")
    assert "python" in qu["skills"]
    assert qu["location"] == "India"
