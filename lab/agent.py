"""A small, transparent tool-calling loop built on LangChain.

We intentionally avoid heavy agent abstractions so you can see exactly what
happens on every step: the model proposes tool calls, we execute them, feed
results back, and repeat until the model produces a final answer.

An optional `policy` hook lets a hardened agent inspect (and block) any tool
call before it runs — this is where least-privilege / allowlist /
human-in-the-loop live in defense.py.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Callable, Optional

from dotenv import load_dotenv
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_openai import ChatOpenAI

load_dotenv()


def build_llm(temperature: float = 0.0) -> ChatOpenAI:
    """Build a ChatOpenAI client pointed at an OpenAI-compatible endpoint (Fireworks)."""
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("FIREWORKS_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.fireworks.ai/inference/v1")
    model = os.getenv("MODEL", "accounts/fireworks/models/llama-v3p1-70b-instruct")
    if not api_key:
        raise RuntimeError(
            "No API key found. Copy .env.example to .env and set OPENAI_API_KEY "
            "to your Fireworks key."
        )
    return ChatOpenAI(model=model, temperature=temperature, api_key=api_key, base_url=base_url)


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


def run_agent(
    llm: ChatOpenAI,
    tools: list,
    system_prompt: str,
    user_message: str,
    max_steps: int = 6,
    policy: Optional[Policy] = None,
) -> RunResult:
    tool_map = {t.name: t for t in tools}
    llm_with_tools = llm.bind_tools(tools)
    messages: list[BaseMessage] = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_message),
    ]
    result = RunResult()

    for _ in range(max_steps):
        ai: AIMessage = llm_with_tools.invoke(messages)
        messages.append(ai)

        if not ai.tool_calls:
            result.final_text = ai.content if isinstance(ai.content, str) else str(ai.content)
            return result

        for tc in ai.tool_calls:
            name = tc["name"]
            args = tc.get("args", {}) or {}

            # Policy hook: a hardened agent can block the call here.
            if policy is not None:
                verdict = policy(name, args)
                if verdict is not None:
                    result.tool_calls.append(ToolCallRecord(name, args, verdict, blocked=True))
                    messages.append(ToolMessage(content=verdict, tool_call_id=tc["id"]))
                    continue

            tool = tool_map.get(name)
            if tool is None:
                output = f"ERROR: unknown tool '{name}'"
            else:
                output = tool.invoke(args)
                if not isinstance(output, str):
                    output = str(output)

            result.tool_calls.append(ToolCallRecord(name, args, output))
            messages.append(ToolMessage(content=output, tool_call_id=tc["id"]))

    result.final_text = "[max steps reached without a final answer]"
    return result
