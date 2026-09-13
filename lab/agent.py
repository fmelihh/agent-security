"""The agent, assembled with LangChain's native `create_agent` + middleware.

Instead of a hand-written tool loop, we use LangChain's agent (which compiles to
a LangGraph graph) and express the harness as middleware:

- `policy_guard`  : a `wrap_tool_call` middleware (allowlist + human-in-the-loop)
- `output_guard`  : an `after_model` middleware (redacts bulk PII from the reply)

Those live in lab/middleware.py. This module just builds the model and the
agent, and flattens a run into a small trace for the reports.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional, Sequence

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_openai import ChatOpenAI

load_dotenv()

# The lab is pinned to a small local model served by Docker Model Runner.
# Hard-coded on purpose so the whole thing runs on your machine with no hosted
# API. To try another model or endpoint, change these two constants.
MODEL = "ai/qwen2.5:1.5B-F16"
BASE_URL = "http://localhost:12434/engines/v1"


def build_llm(temperature: float = 0.0) -> ChatOpenAI:
    """Build a ChatOpenAI client for the local model (see MODEL / BASE_URL)."""
    api_key = os.getenv("OPENAI_API_KEY") or "local"  # local runner ignores it
    return ChatOpenAI(model=MODEL, temperature=temperature, api_key=api_key, base_url=BASE_URL)


def build_agent(tools: list, system_prompt: Optional[str] = None, middleware: Sequence = ()):
    """Compile a LangChain agent (a LangGraph graph) with the given harness middleware."""
    return create_agent(
        build_llm(),
        tools,
        system_prompt=system_prompt,
        middleware=list(middleware),
    )


@dataclass
class ToolCallRecord:
    name: str
    args: dict
    result: str
    blocked: bool = False


@dataclass
class RunResult:
    final_text: str = ""
    tool_calls: list[ToolCallRecord] = field(default_factory=list)


def _to_run_result(messages: list[BaseMessage]) -> RunResult:
    """Flatten the agent's message history into a trace (tool calls + final text)."""
    result = RunResult()
    proposed: dict[str, tuple[str, dict]] = {}
    for m in messages:
        for tc in getattr(m, "tool_calls", None) or []:
            proposed[tc["id"]] = (tc["name"], tc.get("args") or {})
    for m in messages:
        if isinstance(m, ToolMessage):
            name, args = proposed.get(m.tool_call_id, (m.name or "?", {}))
            content = m.content if isinstance(m.content, str) else str(m.content)
            result.tool_calls.append(
                ToolCallRecord(name, args, content, blocked=content.startswith("BLOCKED"))
            )
    for m in reversed(messages):
        if isinstance(m, AIMessage) and not getattr(m, "tool_calls", None):
            result.final_text = m.content if isinstance(m.content, str) else str(m.content)
            break
    return result


def run_agent(
    tools: list,
    system_prompt: str,
    user_message: str,
    middleware: Sequence = (),
    max_steps: int = 6,
) -> RunResult:
    app = build_agent(tools, system_prompt=system_prompt, middleware=middleware)
    try:
        final = app.invoke(
            {"messages": [HumanMessage(content=user_message)]},
            config={"recursion_limit": max_steps * 2 + 2},
        )
    except Exception as exc:  # e.g. recursion limit
        result = RunResult()
        result.final_text = f"[stopped: {type(exc).__name__}]"
        return result
    return _to_run_result(final["messages"])
