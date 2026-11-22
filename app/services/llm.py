"""LLM service layer.

All Claude calls live behind this class so product logic never touches the
SDK. Two rules from the blueprint are enforced here:

* Model output that will be saved or acted on is validated against a
  pydantic schema first; invalid output is discarded and the caller falls
  back to deterministic logic.
* The API key never leaves the backend (the frontend only sees `mode`).

When there is no API key the app runs in OFFLINE mode: every feature keeps
working with deterministic local logic and responses are labelled as such.
"""
import json
import logging
import time
from typing import Callable, Dict, List, Optional, Type

from pydantic import BaseModel, ValidationError

from ..config import settings

log = logging.getLogger("careeros.llm")

try:
    import anthropic
except ImportError:  # SDK is optional in offline mode
    anthropic = None

TIMEOUT_SECONDS = 30
MAX_RETRIES = 2


class LLMService:
    def __init__(self) -> None:
        self.enabled = settings.claude_enabled and anthropic is not None
        self.mode = "claude" if self.enabled else "offline"
        self._client = anthropic.Anthropic(
            api_key=settings.anthropic_api_key, timeout=TIMEOUT_SECONDS
        ) if self.enabled else None

    def complete_json(self, system: str, user: str,
                      schema: Type[BaseModel]) -> Optional[BaseModel]:
        """Ask Claude for JSON and validate it against `schema`.
        Returns None on any failure so callers can fall back safely."""
        if not self.enabled:
            return None
        prompt = user + "\n\nRespond with ONLY a JSON object, no markdown fences."
        for attempt in range(MAX_RETRIES + 1):
            try:
                resp = self._client.messages.create(
                    model=settings.anthropic_model,
                    max_tokens=2048,
                    system=system,
                    messages=[{"role": "user", "content": prompt}],
                )
                text = "".join(b.text for b in resp.content if b.type == "text")
                return schema.model_validate(json.loads(text))
            except (ValidationError, json.JSONDecodeError) as e:
                log.warning("claude output failed validation (id=%s): %s",
                            getattr(resp, "id", "?"), e)
                return None  # bad output: retrying rarely fixes schema issues
            except Exception as e:  # rate limit / network / server error
                log.warning("claude call failed (attempt %d): %s", attempt, e)
                if attempt < MAX_RETRIES:
                    time.sleep(2 ** attempt)
        return None

    def chat_with_tools(self, system: str, messages: List[dict],
                        tools: List[dict],
                        executor: Callable[[str, dict], str],
                        max_rounds: int = 4) -> dict:
        """Run a tool-use loop. `executor(name, input) -> str` performs the
        bounded action locally; Claude only chooses which tool to call.
        Returns {"answer": str, "tool_trace": [...]} or None on failure."""
        if not self.enabled:
            return None
        trace = []
        convo = list(messages)
        try:
            for _ in range(max_rounds):
                resp = self._client.messages.create(
                    model=settings.anthropic_model,
                    max_tokens=2048,
                    system=system,
                    tools=tools,
                    messages=convo,
                )
                tool_uses = [b for b in resp.content if b.type == "tool_use"]
                if not tool_uses:
                    answer = "".join(b.text for b in resp.content if b.type == "text")
                    return {"answer": answer, "tool_trace": trace}
                convo.append({"role": "assistant", "content": resp.content})
                results = []
                for tu in tool_uses:
                    out = executor(tu.name, tu.input)
                    trace.append({"tool": tu.name, "input": dict(tu.input),
                                  "output_summary": out[:200]})
                    results.append({"type": "tool_result", "tool_use_id": tu.id,
                                    "content": out})
                convo.append({"role": "user", "content": results})
        except Exception as e:
            log.warning("claude tool loop failed: %s", e)
        return None


llm = LLMService()
