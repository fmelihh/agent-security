"""Run the agent yourself, interactively.

Pick one of the 5 examples (or paste your own ticket), choose how hardened the
agent is, and watch it run autonomously. This is a sandbox, not a test suite.

Run:  uv run python -m lab.interactive
"""

from __future__ import annotations

from . import data
from .agent import build_llm, run_agent
from .defense import guard_policy, quarantine_extract
from .examples import EXAMPLES, get
from .report import print_trace, print_verdict
from .scenario import INDIRECT_SYSTEM_PROMPT
from .tools import ALL_TOOLS, LEAST_PRIVILEGE_TOOLS

# One triage prompt for every mode: it tells the agent to read order notes, so
# both direct (in-ticket) and indirect (poisoned-note) injections are in play.
TRIAGE_PROMPT = INDIRECT_SYSTEM_PROMPT

MODES = {
    "1": "vulnerable",       # all tools, permissive prompt, no policy
    "2": "least_privilege",  # read-only tool only
    "3": "guarded",          # all tools + allowlist/human-in-the-loop policy + hardened prompt
    "4": "dual_llm",         # quarantine LLM (no tools) -> privileged LLM
}


def run_once(llm, ticket: str, mode: str) -> None:
    data.reset()
    print("\n" + "-" * 72)
    print(f"MODE: {mode}")
    print("-" * 72)

    if mode == "least_privilege":
        result = run_agent(llm, LEAST_PRIVILEGE_TOOLS, TRIAGE_PROMPT, ticket)
    elif mode == "guarded":
        result = run_agent(llm, ALL_TOOLS, TRIAGE_PROMPT, ticket, policy=guard_policy)
    elif mode == "dual_llm":
        clean = quarantine_extract(llm, ticket)
        print(f"quarantine LLM (no tools) extracted: {clean!r}")
        result = run_agent(llm, ALL_TOOLS, TRIAGE_PROMPT,
                           f"A customer needs help with: {clean}")
    else:  # vulnerable
        result = run_agent(llm, ALL_TOOLS, TRIAGE_PROMPT, ticket)

    print_trace(result)
    print_verdict(result.final_text)


def choose_ticket() -> str | None:
    print("\nExamples:")
    for i, ex in enumerate(EXAMPLES, 1):
        print(f"  {i}. {ex['title']}  ({ex['technique']})")
    print("  c. paste your own ticket")
    print("  q. quit")
    choice = input("Pick an example [1-6 / c / q]: ").strip().lower()
    if choice == "q":
        return None
    if choice == "c":
        print("Paste the ticket, end with an empty line:")
        lines = []
        while True:
            line = input()
            if line == "":
                break
            lines.append(line)
        return "\n".join(lines)
    try:
        return get(choice)["ticket"]
    except KeyError:
        print("  (unknown choice)")
        return ""


def main() -> None:
    llm = build_llm()
    print("prompt-injection-lab — interactive agent")
    while True:
        ticket = choose_ticket()
        if ticket is None:
            print("bye.")
            return
        if not ticket:
            continue
        print("\nModes:")
        for k, v in MODES.items():
            print(f"  {k}. {v}")
        mode = MODES.get(input("Pick a mode [1-4] (default 1): ").strip(), "vulnerable")
        run_once(llm, ticket, mode)


if __name__ == "__main__":
    main()
