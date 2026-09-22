"""Decide how strongly each matter relates to AI.

Three buckets:
  substantive  - AI vocabulary in the title/name/summary, or used repeatedly in
                 the bill text. These are the matters the report is about.
  passing      - the vocabulary appears once or twice deep in the text of a bill
                 that is about something else. Listed in an appendix.
  excluded     - Legistar's word-splitting search matched, but no AI vocabulary
                 is actually present.
"""

from __future__ import annotations

from terms import UNAMBIGUOUS

REPEAT_THRESHOLD = 2


def total_count(bill: dict) -> int:
    return sum(t["count"] for t in bill["verified_terms"])


def classify(bill: dict) -> str:
    if not bill["verified_terms"]:
        return "excluded"
    if bill["subject_terms"]:
        return "substantive"
    if any(t["term"] in UNAMBIGUOUS for t in bill["verified_terms"]):
        return "substantive"
    if total_count(bill) >= REPEAT_THRESHOLD:
        return "substantive"
    return "passing"


def focus(bill: dict) -> str:
    """Short human label for why the matter is in the report."""
    subject_tiers = {t["tier"] for t in bill["subject_terms"]}
    all_tiers = {t["tier"] for t in bill["verified_terms"]}
    if "core" in subject_tiers:
        return "Directly about AI"
    if "adjacent" in subject_tiers:
        return "Subject is an AI-adjacent technology"
    if "core" in all_tiers:
        return "AI provisions inside a broader bill"
    return "Algorithmic / automated-decision provisions inside a broader bill"
