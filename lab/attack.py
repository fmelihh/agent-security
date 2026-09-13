"""Scenario 1 — the VULNERABLE agent, two ways.

A) Direct injection: the attacker's instruction is in the ticket the agent is
   handed. Well-aligned models often shrug this off (it looks like a crude
   override), so the result is model-dependent.

B) Indirect injection: the user's request is benign, but the agent reads
   attacker-controlled text from a TOOL (get_order_notes) while doing its job.
   Framed as a routine internal process, this reliably hijacks the agent — this
   is the real-world pattern behind incidents like EchoLeak.

Run:  uv run python -m lab.attack
"""

from __future__ import annotations

from . import data
from .agent import run_agent
from .report import print_trace, print_verdict
from .scenario import (
    INDIRECT_SYSTEM_PROMPT,
    INDIRECT_USER_REQUEST,
    INJECTED_TICKET,
    TRIAGE_SYSTEM_PROMPT,
)
from .tools import ALL_TOOLS


def _run(title: str, system_prompt: str, user_message: str) -> bool:
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)
    print("Agent input:")
    print("  " + user_message.replace("\n", "\n  "))
    print("-" * 72)
    data.reset()
    result = run_agent(ALL_TOOLS, system_prompt, user_message)  # no middleware = vulnerable
    print("Agent trace:")
    print_trace(result)
    return print_verdict(result.final_text)


def main() -> None:
    # A) Direct injection in the ticket.
    _run(
        "A) DIRECT INJECTION (instruction sits in the ticket)",
        TRIAGE_SYSTEM_PROMPT,
        INJECTED_TICKET,
    )

    # B) Indirect injection via a poisoned tool result.
    breached = _run(
        "B) INDIRECT INJECTION (instruction rides in via get_order_notes)",
        INDIRECT_SYSTEM_PROMPT,
        INDIRECT_USER_REQUEST,
    )

    print("\n" + "-" * 72)
    if breached:
        print(
            "The customer asked nothing malicious. The attack lived in data the\n"
            "agent RETRIEVED while doing its job. The model followed it because it\n"
            "cannot tell 'retrieved data' from 'instructions'. Fix = architecture,\n"
            "not prompt wording. See lab/defense.py."
        )
    else:
        print(
            "No breach this run. Injection success is model- and phrasing-dependent;\n"
            "try 'make dev' (LangGraph Studio) with different tickets and models."
        )


if __name__ == "__main__":
    main()
