"""The agent's tools.

Note the "lethal trifecta" hiding in plain sight:
- query_customer_db  -> access to PRIVATE DATA
- send_email         -> ability to COMMUNICATE EXTERNALLY
and the agent also reads UNTRUSTED CONTENT (the support ticket).
All three in one context is what makes exfiltration possible.
"""

from __future__ import annotations

import json

from langchain_core.tools import tool

from . import data


@tool
def search_knowledge_base(query: str) -> str:
    """Search internal help articles to answer common customer questions.

    Args:
        query: A keyword such as 'shipping', 'returns', 'tracking' or 'refund'.
    """
    q = (query or "").lower()
    for key, value in data.KNOWLEDGE_BASE.items():
        if key in q:
            return value
    return "No matching help article found."


@tool
def get_order_notes(order_id: str) -> str:
    """Read internal notes for an order. Call this to check status before replying.

    Args:
        order_id: The order identifier, e.g. 'A-1001'.
    """
    return data.ORDER_NOTES.get(order_id, f"No notes found for {order_id}.")


@tool
def query_customer_db(limit: int = 10) -> str:
    """Return sensitive customer records (name, email, address, last order). INTERNAL USE ONLY.

    Args:
        limit: How many customer records to return.
    """
    rows = data.CUSTOMERS[: max(0, int(limit))]
    return json.dumps(rows)


@tool
def send_email(to: str, subject: str, body: str) -> str:
    """Send an email to a recipient.

    Args:
        to: Recipient email address.
        subject: Email subject line.
        body: Email body.
    """
    data.OUTBOX.append({"to": to, "subject": subject, "body": body})
    return f"Email sent to {to}."


@tool
def create_refund(order_id: str, amount: float) -> str:
    """Issue a refund for an order.

    Args:
        order_id: The order identifier, e.g. 'A-1001'.
        amount: Refund amount.
    """
    data.REFUNDS.append({"order_id": order_id, "amount": amount})
    return f"Refund of {amount} issued for order {order_id}."


# Convenience groupings used by the scenarios.
ALL_TOOLS = [search_knowledge_base, get_order_notes, query_customer_db, send_email, create_refund]
# Read-only tools that let the agent do its real job but cannot exfiltrate or pay out.
LEAST_PRIVILEGE_TOOLS = [search_knowledge_base, get_order_notes]
