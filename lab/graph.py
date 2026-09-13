"""Graph entrypoints for the LangGraph CLI (`langgraph dev` / Studio).

Each name below is a compiled graph you can open in LangGraph Studio and drive
by hand: type a ticket as the user message and watch the agent run, step by
step, through the harness. Compare the same ticket across the graphs to see the
defenses kick in.

    uv run langgraph dev
    # then open the printed Studio URL and pick a graph

Graphs:
- vulnerable       : all tools, no middleware (this is the one that breaches)
- guarded          : all tools + policy_guard middleware (allowlist + HITL)
- least_privilege  : read-only tools only
- output_guarded   : all tools + output_guard middleware (redacts PII in the reply)

See lab/examples.py (or the README) for tickets to paste in. The order's
internal notes for A-1001 are poisoned, so "check order A-1001" triggers the
indirect-injection path.
"""

from __future__ import annotations

# Absolute imports: the LangGraph CLI loads this file as a standalone module,
# so relative imports would have no parent package.
from lab.agent import build_agent
from lab.middleware import output_guard, policy_guard
from lab.scenario import INDIRECT_SYSTEM_PROMPT
from lab.tools import ALL_TOOLS, LEAST_PRIVILEGE_TOOLS

# Each is a create_agent graph with different harness middleware. Building the
# agent does not call the model; it is only contacted when you run it in Studio.
vulnerable = build_agent(ALL_TOOLS, system_prompt=INDIRECT_SYSTEM_PROMPT)
guarded = build_agent(ALL_TOOLS, system_prompt=INDIRECT_SYSTEM_PROMPT, middleware=[policy_guard])
least_privilege = build_agent(LEAST_PRIVILEGE_TOOLS, system_prompt=INDIRECT_SYSTEM_PROMPT)
output_guarded = build_agent(ALL_TOOLS, system_prompt=INDIRECT_SYSTEM_PROMPT, middleware=[output_guard])
