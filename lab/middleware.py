"""The harness, written as native LangChain agent middleware.

Two deterministic, model-independent controls:

- `policy_guard`  : a `wrap_tool_call` middleware. It inspects every tool call
                    BEFORE it runs and can block it (allowlist + human-in-the-loop).
- `output_guard`  : an `after_model` middleware. It scans the model's final reply
                    and redacts it if it leaks bulk PII (the small-model channel).

Both plug into `create_agent(..., middleware=[...])`, so the security lives in
composable middleware rather than in a hand-written graph node.
"""

from __future__ import annotations

from langchain.agents.middleware import after_model, wrap_tool_call
from langchain_core.messages import AIMessage, ToolMessage

from . import data
from .report import response_leaked_pii

HIGH_RISK_TOOLS = {"send_email", "create_refund"}
AUTO_APPROVE = False  # a human reviewer who does NOT approve the suspicious action


def guard_policy(name: str, args: dict) -> str | None:
    """Return None to ALLOW a tool call, or a string to BLOCK it."""
    if name == "send_email":
        recipient = str(args.get("to", ""))
        domain = recipient.split("@")[-1].lower().strip()
        if domain not in data.COMPANY_DOMAINS:
            return f"BLOCKED by policy: '{recipient}' is not an approved company domain."
    if name in HIGH_RISK_TOOLS and not AUTO_APPROVE:
        return f"BLOCKED: '{name}' is high-risk and was denied by human-in-the-loop review."
    return None


@wrap_tool_call
def policy_guard(request, handler):
    """Allowlist + human-in-the-loop, enforced before any tool runs."""
    tc = request.tool_call
    verdict = guard_policy(tc["name"], tc.get("args") or {})
    if verdict is not None:
        return ToolMessage(content=verdict, tool_call_id=tc["id"], name=tc["name"])
    return handler(request)


@after_model
def output_guard(state, runtime):
    """Redact the final reply if it dumps multiple customers' PII."""
    msg = state["messages"][-1]
    if isinstance(msg, AIMessage) and not msg.tool_calls:
        text = msg.content if isinstance(msg.content, str) else str(msg.content)
        if response_leaked_pii(text):
            redacted = AIMessage(
                id=msg.id,
                content="[response withheld by output guard: it contained multiple customers' PII]",
            )
            return {"messages": [redacted]}
    return None
