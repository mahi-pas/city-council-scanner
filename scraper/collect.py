"""Sweep Legistar for candidate AI-related matters and save the de-duplicated hits.

Multi-word queries are quoted so Legistar phrase-matches instead of AND-ing the
individual words. Precision is finished off in enrich.py, which re-checks the
bill's own text.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from legistar import LegistarClient
from terms import SEARCH_TERMS, TITLE_SEARCH_TERMS

DATA = Path(__file__).resolve().parent.parent / "data"


def matter_id(url: str) -> str:
    m = re.search(r"[?&]ID=(\d+)", url)
    return m.group(1) if m else url


def quoted(term: str) -> str:
    return f'"{term}"' if " " in term else term


def main() -> None:
    DATA.mkdir(exist_ok=True)
    client = LegistarClient(delay=0.8)
    client.open_advanced()

    matters: dict[str, dict] = {}

    def absorb(rows, term, where):
        for row in rows:
            key = matter_id(row.url)
            rec = matters.setdefault(
                key,
                {
                    "matter_id": key,
                    "file_number": row.file_number,
                    "url": row.url.split("&Options=")[0],
                    "law_number": row.law_number,
                    "type": row.type,
                    "status": row.status,
                    "committee": row.committee,
                    "prime_sponsor": row.prime_sponsor,
                    "sponsor_count": row.sponsor_count,
                    "title": row.title,
                    "search_hits": [],
                },
            )
            hit = {"query": term, "field": where}
            if hit not in rec["search_hits"]:
                rec["search_hits"].append(hit)

    for term in SEARCH_TERMS:
        q = quoted(term)
        rows = client.search_text(q)
        absorb(rows, term, "text")
        print(f"  text  {q:<40} {len(rows):>4} hits   (total {len(matters)})", flush=True)

    for term in TITLE_SEARCH_TERMS:
        q = quoted(term)
        rows = client.search_title(q)
        absorb(rows, term, "title")
        print(f"  title {q:<40} {len(rows):>4} hits   (total {len(matters)})", flush=True)

    out = DATA / "search_results.json"
    out.write_text(json.dumps(list(matters.values()), indent=2), encoding="utf-8")
    print(f"\n{len(matters)} candidate matters -> {out}")


if __name__ == "__main__":
    main()
