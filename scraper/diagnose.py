"""Audit what the classifier kept, demoted and dropped, with matching context."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from classify import classify, focus, total_count

DATA = Path(__file__).resolve().parent.parent / "data"


def main() -> None:
    bills = json.loads((DATA / "bills.json").read_text(encoding="utf-8"))
    buckets: dict[str, list[dict]] = {"substantive": [], "passing": [], "excluded": []}
    for b in bills:
        buckets[classify(b)].append(b)
    print({k: len(v) for k, v in buckets.items()})

    print("\n--- PASSING MENTIONS (appendix A) ---")
    for b in sorted(buckets["passing"], key=lambda b: b["file_number"]):
        terms = "; ".join(f"{x['term']} x{x['count']}" for x in b["verified_terms"])
        print(f"  {b['file_number']:<15} {(b.get('name') or b.get('title', ''))[:55]:<57} {terms[:60]}")
        ctx = b["verified_terms"][0].get("context", "")
        if ctx:
            print(f"        ctx: {ctx[:150]}")

    print("\n--- EXCLUDED (appendix B) ---")
    for b in sorted(buckets["excluded"], key=lambda b: b["file_number"]):
        q = ", ".join(sorted({h["query"] for h in b["search_hits"]}))
        print(f"  {b['file_number']:<15} {(b.get('name') or b.get('title', ''))[:55]:<57} <- {q}")

    print("\n--- SUBSTANTIVE, adjacent-only, weakest evidence last ---")
    adj = [b for b in buckets["substantive"]
           if "core" not in {t["tier"] for t in b["verified_terms"]}]
    for b in sorted(adj, key=lambda b: -total_count(b)):
        terms = "; ".join(f"{x['term']} x{x['count']}" for x in b["verified_terms"])
        print(f"  {total_count(b):>3}  {b['file_number']:<15} "
              f"{(b.get('name') or b.get('title', ''))[:50]:<52} {terms[:55]}")

    print("\n--- focus labels ---")
    for label, n in Counter(focus(b) for b in buckets["substantive"]).most_common():
        print(f"  {n:>4}  {label}")
    print("\n--- statuses ---")
    for status, n in Counter(b["status"] for b in buckets["substantive"]).most_common():
        print(f"  {n:>4}  {status}")
    print(f"\n{len({b['committee'] for b in buckets['substantive']})} committees")


if __name__ == "__main__":
    main()
