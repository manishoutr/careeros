"""The LangGraph assistant: offline mode runs the real graph end to end."""
import json

import pytest

from app.db import SessionLocal, init_db
from app.models import Job
from app.schemas import ProfileData
from app.services import agent_graph


@pytest.fixture(scope="module")
def db():
    init_db()
    session = SessionLocal()
    yield session
    session.close()


PROFILE = ProfileData(name="Aarav", skills=["python", "fastapi"])


def test_graph_compiles_and_has_expected_nodes():
    g = agent_graph.build_graph(None, None)
    assert set(g.get_graph().nodes) >= {"decide", "run_tools", "compose_offline"}


def test_offline_profile_question(db):
    result = agent_graph.run(db, PROFILE, [], "what are my skills?")
    assert result["mode"] == "offline"
    assert "python" in result["answer"].lower() or "skills" in result["answer"].lower()
    assert result["tool_trace"][0]["tool"] == "get_candidate_profile"


def test_offline_job_question_uses_search_tool(db):
    result = agent_graph.run(db, PROFILE, [], "python backend internships in India")
    assert result["mode"] == "offline"
    assert result["tool_trace"][0]["tool"] == "search_jobs"
    assert result["answer"]


def test_unknown_tool_is_safe(db):
    run = __import__("app.services.assistant_tools", fromlist=["executor"]).executor(db, PROFILE)
    assert "Unknown tool" in run("drop_everything", {})
