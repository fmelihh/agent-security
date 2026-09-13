"""The agent, built as a LangGraph state machine.

The graph is a classic tool-calling loop expressed as a `StateGraph`:

    START -> agent -> (tool_calls?) --yes--> tools -> agent
                          |
                          no
                          v
                         END

- `agent`  : the LLM proposes tool calls (or a final answer).
- `tools`  : a custom node that executes tool calls — and this is where the
             harness lives. An optional `policy` hook inspects every call
             BEFORE it runs and can block it (least privilege / allowlist /
             human-in-the-loop all plug in here).

We deliberately write the `tools` node ourselves (instead of the prebuilt
ToolNode) so the security boundary is explicit and easy to read.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Annotated, Callable, Optional, TypedDict

from dotenv import load_dotenv
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

load_dotenv()


# The lab is pinned to a small local model served by Docker Model Runner.
# These are intentionally hard-coded (not read from .env) so the whole thing
# runs on your machine with no hosted API. To try another model or endpoint,
# change these two constants.
MODEL = "ai/qwen2.5:1.5B-F16"
BASE_URL = "http://localhost:12434/engines/v1"


def build_llm(temperature: float = 0.0) -> ChatOpenAI:
    """Build a ChatOpenAI client for the local model (see MODEL / BASE_URL above)."""
    # The local runner ignores the key, but the client still needs a non-empty one.
    api_key = os.getenv("OPENAI_API_KEY") or "local"
    return ChatOpenAI(model=MODEL, temperature=temperature, api_key=api_key, base_url=BASE_URL)


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


# A policy returns None to ALLOW a call, or a string to BLOCK it (the string is
# fed back to the model as the tool result, e.g. "BLOCKED: external recipient").
Policy = Callable[[str, dict], Optional[str]]


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


def build_graph(
    llm: ChatOpenAI,
    tools: list,
    policy: Optional[Policy] = None,
    system_prompt: Optional[str] = None,
):
    """Compile the LangGraph agent. `policy` is the harness hook on tool calls.

    `system_prompt` is used by the LangGraph CLI / Studio entrypoints, where the
    caller only supplies a user message: if the incoming state has no system
    message, we prepend this one. run_agent passes its own system message, so it
    is left untouched."""
    llm_with_tools = llm.bind_tools(tools)
    tool_map = {t.name: t for t in tools}

    def agent_node(state: AgentState) -> dict:
        msgs = state["messages"]
        if system_prompt and not any(isinstance(m, SystemMessage) for m in msgs):
            msgs = [SystemMessage(content=system_prompt), *msgs]
        # The LLM decides what to do next (call a tool, or answer).
        return {"messages": [llm_with_tools.invoke(msgs)]}

    def tools_node(state: AgentState) -> dict:
        # Execute the proposed tool calls — through the harness policy.
        last: AIMessage = state["messages"][-1]
        out: list[BaseMessage] = []
        for tc in last.tool_calls:
            name, args, call_id = tc["name"], (tc.get("args") or {}), tc["id"]
            if policy is not None and (verdict := policy(name, args)) is not None:
                out.append(ToolMessage(content=verdict, tool_call_id=call_id, name=name))
                continue
            tool = tool_map.get(name)
            result = tool.invoke(args) if tool else f"ERROR: unknown tool '{name}'"
            out.append(ToolMessage(content=str(result), tool_call_id=call_id, name=name))
        return {"messages": out}

    def route(state: AgentState) -> str:
        last = state["messages"][-1]
        return "tools" if getattr(last, "tool_calls", None) else END

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tools_node)
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", route, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")
    return graph.compile()


def _to_run_result(messages: list[BaseMessage]) -> RunResult:
    """Reconstruct a flat trace (tool calls + final text) from the graph state."""
    result = RunResult()
    # Map tool_call_id -> (name, args) from every AIMessage that proposed calls.
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
        if isinstance(m, AIMessage) and not (getattr(m, "tool_calls", None)):
            result.final_text = m.content if isinstance(m.content, str) else str(m.content)
            break
    return result


def run_agent(
    llm: ChatOpenAI,
    tools: list,
    system_prompt: str,
    user_message: str,
    max_steps: int = 6,
    policy: Optional[Policy] = None,
) -> RunResult:
    app = build_graph(llm, tools, policy)
    init: AgentState = {
        "messages": [SystemMessage(content=system_prompt), HumanMessage(content=user_message)]
    }
    try:
        final = app.invoke(init, config={"recursion_limit": max_steps * 2 + 2})
    except Exception as exc:  # e.g. GraphRecursionError
        result = RunResult()
        result.final_text = f"[stopped: {type(exc).__name__}]"
        return result
    return _to_run_result(final["messages"])
