"""Parsing quality: the offline parser must extract the fields we claim."""
from app.services.parsing import parse_resume_text

SAMPLE = """Aarav Sharma
Bhubaneswar, India | aarav.sharma@example.com

Skills
Python, FastAPI, PostgreSQL, Docker, React, Git

Experience
Backend Intern at Odisha Web Works (Jun 2025 - Aug 2025)
- Built FastAPI endpoints

Education
B.Tech Computer Science, Odisha University of Technology and Research, 2027
"""


def test_extracts_name():
    assert parse_resume_text(SAMPLE).name == "Aarav Sharma"


def test_extracts_skills_from_lexicon():
    skills = parse_resume_text(SAMPLE).skills
    for expected in ("python", "fastapi", "postgresql", "docker", "react", "git"):
        assert expected in skills


def test_extracts_experience_with_period_and_years():
    exp = parse_resume_text(SAMPLE).experience
    assert len(exp) == 1
    assert exp[0].title == "Backend Intern"
    assert exp[0].company == "Odisha Web Works"
    assert exp[0].years > 0  # Jun-Aug 2025 is about 0.2 years


def test_extracts_education():
    edu = parse_resume_text(SAMPLE).education
    assert edu and "B.Tech" in edu[0].degree
    assert "Odisha University" in edu[0].institution
