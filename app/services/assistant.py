"""Grounded career assistant.

The implementation lives in agent_graph (a LangGraph state machine shared by
both modes) and assistant_tools (the bounded tool set). This module stays as
the stable import surface for the API layer.
"""
from typing import Optional

from ..schemas import ProfileData
from . import agent_graph


def answer(db, profile: Optional[ProfileData], history: list, message: str) -> dict:
    """Answer one user message. Returns {answer, mode, tool_trace}."""
    return agent_graph.run(db, profile, history, message)
