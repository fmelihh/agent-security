"""LangServe app — run the agent from a browser UI.

Start it, then open the playground and try the tickets yourself:

    uv run uvicorn lab.serve:app --reload
    # open http://127.0.0.1:8000/triage/playground/

The agent runs autonomously on whatever ticket you submit. Pick a `mode` to
compare the vulnerable agent against each defense. See lab/examples.py (or the
README) for tickets to paste in.
"""

from __future__ import annotations

from functools import lru_cache

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from langchain_core.runnables import RunnableLambda
from langserve import add_routes
from pydantic import BaseModel, Field

from . import data
from .agent import build_llm, run_agent
from .defense import apply_output_guard, guard_policy, quarantine_extract
from .report import exfiltrated_emails, response_leaked_pii
from .scenario import INDIRECT_SYSTEM_PROMPT
from .tools import ALL_TOOLS, LEAST_PRIVILEGE_TOOLS

# The triage prompt reads order notes, so both direct and indirect injections apply.
TRIAGE_PROMPT = INDIRECT_SYSTEM_PROMPT


class TriageInput(BaseModel):
    ticket: str = Field(..., description="The support ticket text to process.")
    mode: str = Field(
        "vulnerable",
        description="One of: vulnerable | least_privilege | guarded | dual_llm | output_guard",
    )


@lru_cache(maxsize=1)
def _llm():
    return build_llm()


def _triage(inp: dict) -> dict:
    if isinstance(inp, BaseModel):
        inp = inp.model_dump()
    ticket = inp["ticket"]
    mode = inp.get("mode", "vulnerable")
    llm = _llm()
    data.reset()

    if mode == "least_privilege":
        result = run_agent(llm, LEAST_PRIVILEGE_TOOLS, TRIAGE_PROMPT, ticket)
    elif mode == "guarded":
        result = run_agent(llm, ALL_TOOLS, TRIAGE_PROMPT, ticket, policy=guard_policy)
    elif mode == "dual_llm":
        clean = quarantine_extract(llm, ticket)
        result = run_agent(llm, ALL_TOOLS, TRIAGE_PROMPT,
                           f"A customer needs help with: {clean}")
    else:
        result = run_agent(llm, ALL_TOOLS, TRIAGE_PROMPT, ticket)

    final_text = result.final_text
    output_redacted = False
    if mode == "output_guard":
        final_text, output_redacted = apply_output_guard(final_text)

    leaked = exfiltrated_emails()
    response_leak = response_leaked_pii(final_text)
    return {
        "mode": mode,
        "final": final_text,
        "output_redacted": output_redacted,
        "tool_calls": [
            {"name": c.name, "args": c.args, "blocked": c.blocked, "result": c.result}
            for c in result.tool_calls
        ],
        "data_breach": bool(leaked or response_leak),
        "leaked_via_email_to": [m["to"] for m in leaked],
        "leaked_via_response": len(response_leak),
        "refunds_issued": list(data.REFUNDS),
    }


triage = RunnableLambda(_triage).with_types(input_type=TriageInput)

app = FastAPI(
    title="prompt-injection-lab",
    description="Reproduce and defend against prompt injection in a tool-using agent.",
)


@app.get("/")
def root():
    return RedirectResponse("/triage/playground/")


add_routes(app, triage, path="/triage")
