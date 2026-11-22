"""Assistant orchestration as a LangGraph state machine.

One graph serves both modes:

    START -> decide -> (tool calls?) -> run_tools -> decide -> ... -> END

* decide: with Claude configured, one Claude tool-use round (via
  langchain-anthropic) either requests tools or answers. Offline, a
  transparent rule picks a tool and the loop runs exactly once.
* run_tools: executes the requested bounded tools locally and records the
  tool trace.
* compose (offline only): templates the answer from tool output, labelled
  offline so nobody mistakes it for model output.

Keeping the loop in the graph - not in a while-loop - means the
orchestration is testable offline and Claude only swaps the decision node.
"""
import json
from typing import Any, Dict, List, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from ..schemas import ProfileData
from . import assistant_tools
from .llm import llm

MAX_ROUNDS = 4
_PROFILE_WORDS = ("my skills", "my profile", "my experience",
                  "who am i", "my resume", "about me")


class AgentState(TypedDict, total=False):
    message: str
    history: List[dict]
    mode: str                       # "claude" or "offline"
    convo: List[Any]                # running Claude conversation (mode=claude)
    pending_calls: List[dict]       # tool calls requested by decide
    tool_results: List[dict]        # executed outputs (offline compose reads these)
    trace: List[dict]
    round: int
    answer: str


def _decide(state: AgentState, db, profile) -> AgentState:
    if state["mode"] == "claude":
        return _decide_claude(state)
    return _decide_offline(state, db, profile)


def _decide_claude(state: AgentState) -> AgentState:
    """One Claude tool-use round via langchain-anthropic."""
    from langchain_anthropic import ChatAnthropic
    from ..config import settings
    model = ChatAnthropic(model=settings.anthropic_model,
                          api_key=settings.anthropic_api_key,
                          max_tokens=2048, timeout=30)
    model_with_tools = model.bind_tools([
        {"name": t["name"], "description": t["description"],
         "input_schema": t["input_schema"]} for t in assistant_tools.TOOLS])
    convo = state.get("convo") or (
        [{"role": h["role"], "content": h["content"]} for h in state["history"][-10:]]
        + [{"role": "user", "content": state["message"]}])
    resp = model_with_tools.invoke(
        [{"role": "system", "content": assistant_tools.SYSTEM}] + convo)
    convo = convo + [resp]
    if resp.tool_calls:
        return {**state, "convo": convo,
                "pending_calls": resp.tool_calls,
                "round": state.get("round", 0) + 1}
    return {**state, "convo": convo, "pending_calls": [],
            "answer": str(resp.content)}


def _decide_offline(state: AgentState, db, profile) -> AgentState:
    lowered = state["message"].lower()
    if any(w in lowered for w in _PROFILE_WORDS):
        calls = [{"name": "get_candidate_profile", "args": {}, "id": "offline-1"}]
    else:
        calls = [{"name": "search_jobs",
                  "args": {"query": state["message"], "k": 3}, "id": "offline-1"}]
    return {**state, "pending_calls": calls, "round": state.get("round", 0) + 1}


def _run_tools(state: AgentState, db, profile) -> AgentState:
    run = assistant_tools.executor(db, profile)
    trace = list(state.get("trace", []))
    results = list(state.get("tool_results", []))
    convo = list(state.get("convo", []))
    tool_result_msgs = []
    for call in state["pending_calls"]:
        out = run(call["name"], call.get("args") or {})
        trace.append({"tool": call["name"], "input": call.get("args") or {},
                      "output_summary": out[:200]})
        results.append({"tool": call["name"], "output": out})
        tool_result_msgs.append({"role": "tool", "content": out,
                                 "tool_call_id": call.get("id", "")})
    if state["mode"] == "claude":
        convo = convo + tool_result_msgs
    return {**state, "trace": trace, "tool_results": results,
            "convo": convo, "pending_calls": []}


def _compose_offline(state: AgentState, profile) -> AgentState:
    result = state["tool_results"][0] if state["tool_results"] else {}
    out = result.get("output", "")
    if result.get("tool") == "get_candidate_profile":
        if profile is None:
            answer = ("You haven't uploaded a resume yet, so I don't have a "
                      "profile. Upload one from the Profile tab.")
        else:
            answer = (f"Here's your profile: {len(profile.skills)} skills "
                      f"(e.g. {', '.join(profile.skills[:6]) or 'none detected'}), "
                      f"{len(profile.experience)} experience entries and "
                      f"{len(profile.education)} education entries. "
                      "You can correct any field in the Profile tab.")
        return {**state, "answer": answer}
    jobs = [json.loads(ln) for ln in out.splitlines() if ln.startswith("{")]
    if not jobs:
        return {**state, "answer": "I couldn't find matching jobs in the catalogue. "
                "Try different keywords or ingest more jobs."}
    recs = []
    for j in jobs:
        reason = j["reasons"][0] if j["reasons"] else "good overall match"
        recs.append(f"- {j['title']} at {j['company']} ({j['location']}) - {reason}")
    return {**state, "answer": "Top matches from the catalogue:\n" + "\n".join(recs)}


def _route_after_decide(state: AgentState) -> str:
    if state["pending_calls"] and state.get("round", 0) < MAX_ROUNDS:
        return "run_tools"
    if state["mode"] == "offline" and not state.get("answer"):
        return "compose_offline"
    return END


def _route_after_tools(state: AgentState) -> str:
    return "decide" if state["mode"] == "claude" else "compose_offline"


def build_graph(db, profile: Optional[ProfileData]):
    """Compile the assistant graph with request-scoped db/profile bound in."""
    g = StateGraph(AgentState)
    g.add_node("decide", lambda s: _decide(s, db, profile))
    g.add_node("run_tools", lambda s: _run_tools(s, db, profile))
    g.add_node("compose_offline", lambda s: _compose_offline(s, profile))
    g.add_edge(START, "decide")
    g.add_conditional_edges("decide", _route_after_decide,
                            {"run_tools": "run_tools",
                             "compose_offline": "compose_offline", END: END})
    g.add_conditional_edges("run_tools", _route_after_tools,
                            {"decide": "decide", "compose_offline": "compose_offline"})
    g.add_edge("compose_offline", END)
    return g.compile()


def run(db, profile: Optional[ProfileData], history: list, message: str) -> dict:
    mode = "claude" if llm.enabled else "offline"
    state: AgentState = {"message": message, "history": history, "mode": mode,
                         "trace": [], "tool_results": [], "round": 0}
    try:
        final = build_graph(db, profile).invoke(state)
    except Exception as e:
        if mode == "offline":
            raise
        # Claude failed mid-graph: rerun the same graph deterministically.
        import logging
        logging.getLogger("careeros.agent").warning("claude graph failed, offline rerun: %s", e)
        return _offline_rerun(db, profile, history, message)
    return {"answer": final.get("answer", "I don't know."),
            "mode": mode, "tool_trace": final.get("trace", [])}


def _offline_rerun(db, profile, history, message) -> dict:
    state: AgentState = {"message": message, "history": history, "mode": "offline",
                         "trace": [], "tool_results": [], "round": 0}
    final = build_graph(db, profile).invoke(state)
    return {"answer": final.get("answer", "I don't know."),
            "mode": "offline", "tool_trace": final.get("trace", [])}
