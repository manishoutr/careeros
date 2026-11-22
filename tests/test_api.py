"""End-to-end API flow, offline mode: upload -> search -> chat -> tailor.

Runs against a throwaway SQLite database in a temp directory, so it never
touches the developer's real data.
"""
import os
import tempfile

os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tempfile.mkdtemp(), "test.db")
os.environ["LLM_MODE"] = "offline"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)

RESUME = b"""Aarav Sharma
Bhubaneswar, India

Skills
Python, FastAPI, PostgreSQL, Docker

Experience
Backend Intern at Odisha Web Works (Jun 2025 - Aug 2025)

Education
B.Tech Computer Science, OUTR, 2027
"""


def test_health_and_seed():
    with client:  # triggers startup: creates tables and seeds jobs
        res = client.get("/api/health")
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "ok"
        assert body["llm_mode"] == "offline"
        assert body["jobs"] >= 30  # seed catalogue loaded


def test_full_demo_flow():
    with client:
        # 1. upload resume
        res = client.post("/api/profile/resume",
                          files={"file": ("resume.txt", RESUME, "text/plain")})
        assert res.status_code == 200, res.text
        profile = res.json()
        assert profile["name"] == "Aarav Sharma"
        assert "python" in profile["skills"]

        # 2. natural-language search with explanations
        res = client.post("/api/search",
                          json={"query": "backend internships using Python in India", "k": 5})
        assert res.status_code == 200
        data = res.json()
        assert data["count"] > 0
        top = data["results"][0]
        assert top["reasons"]
        assert 0 <= top["scores"]["total"] <= 1
        titles = [r["job"]["title"].lower() for r in data["results"]]
        assert any("backend" in t or "python" in t for t in titles)

        # 3. assistant answers grounded in the catalogue
        res = client.post("/api/assistant/chat",
                          json={"message": "Which jobs fit my profile?"})
        assert res.status_code == 200
        chat = res.json()
        assert chat["mode"] == "offline"
        assert chat["tool_trace"]  # a tool was actually called
        assert chat["answer"]

        # 4. tailoring with safety validation
        job_id = top["job"]["id"]
        res = client.post("/api/tailor", json={"job_id": job_id})
        assert res.status_code == 200
        tailored = res.json()
        profile_skills = {s.lower() for s in profile["skills"]}
        for skill in tailored["draft"]["skills"]:
            assert skill.lower() in profile_skills  # no invented skills


def test_upload_rejects_bad_file_type():
    with client:
        res = client.post("/api/profile/resume",
                          files={"file": ("resume.exe", b"nope", "application/octet-stream")})
        assert res.status_code == 415


def test_tailor_without_profile_is_409():
    from app.db import SessionLocal
    from app.models import Profile
    with client:
        db = SessionLocal()  # ensure no profile exists, regardless of test order
        db.query(Profile).delete()
        db.commit()
        db.close()
        res = client.post("/api/tailor", json={"job_id": 1})
        assert res.status_code in (404, 409)


def test_metrics_endpoint():
    with client:
        client.get("/api/health")
        res = client.get("/api/metrics")
        assert res.status_code == 200
        assert res.json()["requests"] >= 1


def test_remote_query_is_a_hard_constraint():
    """Asking for remote roles must not return non-remote jobs, even weakly
    ranked ones - remote is a constraint, not a hint."""
    with client:
        res = client.post("/api/search", json={"query": "remote python internships", "k": 10})
    assert res.status_code == 200
    data = res.json()
    assert data["results"], "expected the two seeded remote roles"
    for r in data["results"]:
        assert "remote" in r["job"]["location"].lower()


def test_assistant_respects_remote_constraint():
    """The assistant's job tool applies the same hard remote constraint, so
    it never recommends a non-remote job for a remote request."""
    with client:
        res = client.post("/api/assistant/chat",
                          json={"message": "find me remote python internships"})
        assert res.status_code == 200
        body = res.json()
        assert "Hasura" in body["answer"] or "Postman" in body["answer"]
        assert "Bhubaneswar" not in body["answer"] and "TCS" not in body["answer"]
