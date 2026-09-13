"""Graph entrypoints for the LangGraph CLI (`langgraph dev` / Studio).

Each name below is a compiled graph you can open in LangGraph Studio and drive
by hand: type a ticket as the user message and watch the agent run, step by
step, through the harness. Compare the same ticket across the graphs to see the
defenses kick in.

    uv run langgraph dev
    # then open the printed Studio URL and pick a graph

Graphs:
- vulnerable       : all tools, no policy (this is the one that breaches)
- guarded          : all tools + allowlist / human-in-the-loop policy
- least_privilege  : read-only tools only

See lab/examples.py (or the README) for tickets to paste in. The order's
internal notes for A-1001 are poisoned, so "check order A-1001" triggers the
indirect-injection path.
"""

from __future__ import annotations

# Absolute imports: the LangGraph CLI loads this file as a standalone module,
# so relative imports would have no parent package.
from lab.agent import build_graph, build_llm
from lab.defense import guard_policy
from lab.scenario import INDIRECT_SYSTEM_PROMPT
from lab.tools import ALL_TOOLS, LEAST_PRIVILEGE_TOOLS

# Constructing the client does not open a connection; the local model is only
# contacted when a graph is actually invoked from Studio.
_llm = build_llm()

vulnerable = build_graph(_llm, ALL_TOOLS, system_prompt=INDIRECT_SYSTEM_PROMPT)
guarded = build_graph(_llm, ALL_TOOLS, policy=guard_policy, system_prompt=INDIRECT_SYSTEM_PROMPT)
least_privilege = build_graph(_llm, LEAST_PRIVILEGE_TOOLS, system_prompt=INDIRECT_SYSTEM_PROMPT)
