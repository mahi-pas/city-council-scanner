"""Turn data/bills.json into a committee-by-committee markdown report."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from classify import classify, focus, total_count

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = ROOT / "AI_LEGISLATION_BY_COMMITTEE.md"

VOTE_ORDER = ["Affirmative", "Negative", "Abstain", "Absent", "Non-voting", "Excused", "Medical", "Unrecorded"]
VOTE_LABEL = {
    "Negative": "Voted **against**",
    "Abstain": "Abstained",
    "Absent": "Absent",
    "Non-voting": "Present, not voting",
    "Excused": "Excused",
    "Medical": "Medical leave",
    "Unrecorded": "Unrecorded",
}
PASSED = {"Enacted", "Adopted", "Approved"}


def datekey(value: str) -> tuple:
    m = re.match(r"(\d+)/(\d+)/(\d{4})", value or "")
    return (int(m.group(3)), int(m.group(1)), int(m.group(2))) if m else (0, 0, 0)


def outcome(bill: dict) -> str:
    status = bill["status"]
    if status == "Enacted":
        return f"passed and became **Local Law {bill.get('law_number') or '(number pending)'}**"
    if status == "Adopted":
        return "**adopted** by the full Council"
    if status == "Approved":
        return "**approved**"
    if status.startswith("Filed (End of Session)"):
        return "**did not pass** — it died in committee and was filed at the end of the session"
    if status == "Filed":
        return "**closed out** with no further action"
    if status == "Committee":
        return "**still pending** in committee — no vote taken yet"
    if status == "Laid Over in Committee":
        return "**laid over** in committee — heard but not voted out"
    if status == "Withdrawn":
        return "**withdrawn** by its sponsor"
    if status == "Vetoed":
        return "**vetoed**"
    return f"status: {status}"


def tally(votes: dict[str, list[str]]) -> str:
    seen = [k for k in VOTE_ORDER if votes.get(k)] + [k for k in votes if k not in VOTE_ORDER]
    return ", ".join(f"{len(votes[k])} {k.lower()}" for k in seen)


def render_votes(bill: dict, L: list[str]) -> None:
    recorded = [h for h in bill["history"] if h.get("votes")]
    if not recorded:
        acted = [h for h in bill["history"] if h.get("result")]
        if acted:
            L.append("- **Votes:** actions were recorded but no roll call is published for this file.")
        else:
            L.append("- **Votes:** none — this file never reached a recorded vote.")
        return
    L.append(f"- **Recorded votes ({len(recorded)}):**")
    for h in recorded:
        votes = h["votes"]
        yes = len(votes.get("Affirmative", []))
        no = len(votes.get("Negative", []))
        L.append("")
        L.append(f"  - **{h['date']} — {h['action_by']}** — {h['action']} — **{h['result']}** "
                 f"by {yes}\u2013{no} ({tally(votes)})")
        if h.get("mover"):
            second = f", seconded by {h['seconder']}" if h.get("seconder") else ""
            L.append(f"    - Moved by {h['mover']}{second}")
        for key in ("Negative", "Abstain", "Non-voting", "Absent", "Excused", "Medical", "Unrecorded"):
            if votes.get(key):
                L.append(f"    - {VOTE_LABEL[key]} ({len(votes[key])}): {', '.join(votes[key])}")
        if votes.get("Affirmative"):
            L.append("")
            L.append(f"    <details><summary>Voted <b>for</b> ({yes})</summary>")
            L.append("")
            L.append(f"    {', '.join(votes['Affirmative'])}")
            L.append("")
            L.append("    </details>")
    L.append("")


def render_bill(bill: dict, L: list[str]) -> None:
    name = bill.get("name") or bill.get("title") or bill["file_number"]
    L.append(f"#### [{bill['file_number']}]({bill['url']}) — {name}")
    L.append("")
    L.append(f"- **Type:** {bill['type']} &nbsp;·&nbsp; **Relevance:** {focus(bill)}")
    L.append(f"- **Status:** {bill['status']} — {outcome(bill)}")
    L.append(f"- **Proposed:** {bill.get('introduced_date') or bill.get('intro_date') or 'date not published'}")
    if bill.get("completed_date"):
        how = "enacted" if bill.get("enactment_date") else (bill.get("final_action") or "final action").lower()
        L.append(f"- **Completed:** {bill['completed_date']} ({how})")
    else:
        L.append("- **Completed:** not completed — no final action on record")
    sponsors = bill.get("sponsors") or []
    if sponsors:
        L.append(f"- **Proposed by (prime sponsor):** {sponsors[0]}")
        if len(sponsors) > 1:
            L.append(f"- **Co-sponsors ({len(sponsors) - 1}):** {', '.join(sponsors[1:])}")
    else:
        who = bill.get("prime_sponsor") or "none listed (committee-filed oversight item)"
        L.append(f"- **Proposed by (prime sponsor):** {who}")
    if bill.get("summary"):
        L.append(f"- **What it does:** {bill['summary']}")
    elif bill.get("title"):
        L.append(f"- **Title:** {bill['title']}")
    terms = ", ".join(f"{t['term']} (×{t['count']})" for t in bill["verified_terms"])
    L.append(f"- **AI language found:** {terms}")
    if not bill["subject_terms"] and bill["verified_terms"]:
        ctx = bill["verified_terms"][0].get("context", "")
        if ctx:
            L.append(f"  - In context: *{ctx}*")
    L.append(f"- **Link:** {bill['url']}")
    render_votes(bill, L)
    L.append("")


def main() -> None:
    bills = json.loads((DATA / "bills.json").read_text(encoding="utf-8"))
    buckets: dict[str, list[dict]] = defaultdict(list)
    for b in bills:
        buckets[classify(b)].append(b)
    kept = buckets["substantive"]

    by_committee: dict[str, list[dict]] = defaultdict(list)
    for b in kept:
        by_committee[b["committee"] or "(No committee of record)"].append(b)
    for rows in by_committee.values():
        rows.sort(key=lambda b: datekey(b.get("introduced_date") or b.get("intro_date")), reverse=True)

    order = sorted(by_committee, key=lambda c: (-len(by_committee[c]), c))
    counts = Counter(b["status"] for b in kept)
    enacted = [b for b in kept if b["status"] == "Enacted"]
    adopted = [b for b in kept if b["status"] == "Adopted"]
    pending = [b for b in kept if b["status"] in {"Committee", "Laid Over in Committee"}]
    roll_calls = sum(1 for b in kept for h in b["history"] if h.get("votes"))

    L: list[str] = []
    L.append("# AI-Related Legislation in the New York City Council — by Committee")
    L.append("")
    today = f"{date.today():%B} {date.today().day}, {date.today():%Y}"
    L.append(f"*Compiled {today} from the Council's Legistar Legislative Research Center, "
             f"[legistar.council.nyc.gov](https://legistar.council.nyc.gov/Legislation.aspx). Covers all years "
             f"in the system (1994 to present).*")
    L.append("")
    L.append(f"**{len(kept)} matters** spread across **{len(by_committee)} committees** deal with artificial "
             f"intelligence or the algorithmic and automated-decision technologies the Council regulates alongside it. "
             f"**{len(enacted)} became local law** and **{len(adopted)} resolutions were adopted**; "
             f"**{len(pending)} are still alive in committee** and the rest died at the end of a session. "
             f"{roll_calls} roll-call votes are reproduced below, member by member.")
    L.append("")
    top = order[0]
    L.append(f"The {top} is the center of gravity with {len(by_committee[top])} of them, but the work is spread "
             f"widely: education, consumer and worker protection, public safety, housing and civil service "
             f"committees have all moved AI bills of their own.")
    L.append("")

    L.append("## Contents")
    L.append("")
    L.append("- [How this was compiled](#how-this-was-compiled)")
    L.append("- [Committee scorecard](#committee-scorecard)")
    L.append("- [What became law](#what-became-law)")
    L.append("- [Legislation by committee](#legislation-by-committee)")
    for c in order:
        anchor = re.sub(r"[^a-z0-9 -]", "", c.lower()).replace(" ", "-")
        L.append(f"  - [{c}](#{anchor}) ({len(by_committee[c])})")
    L.append("- [Appendix A — passing mentions](#appendix-a--passing-mentions)")
    L.append("- [Appendix B — search hits rejected on inspection](#appendix-b--search-hits-rejected-on-inspection)")
    L.append("")

    L.append("## How this was compiled")
    L.append("")
    L.append("Legistar's public Web API now answers `403 Token is required` and tokens are issued only by email "
             "request, so the data was taken from the site's own advanced-search form, driven directly and set to "
             "**All Years**. For every matter found, its Legistar detail page supplied the sponsors, dates, committee "
             "and full action history, and each action carrying a recorded result was followed to its roll-call page "
             "for the individual member votes.")
    L.append("")
    L.append("**Search terms.** Full bill text and titles were searched for:")
    L.append("")
    L.append("> artificial intelligence · generative AI · A.I. · machine learning · deep learning · large language "
             "model · neural network · natural language processing · computer vision · chatbot(s) · deepfake / deep "
             "fake · synthetic media · digital replica · voice cloning · emotion recognition · algorithm(s) / "
             "algorithmic · automated decision (system / -making) · automated employment decision tool · automated "
             "hiring · automated tool · decision-making tool · intelligence tool · bias audit · facial recognition · "
             "biometric identifier · biometric recognition · predictive analytics · predictive policing · robot / "
             "robotic · autonomous vehicle · surveillance technology · automated system")
    L.append("")
    L.append("**A caveat about the search index, and what was done about it.** Legistar treats an unquoted multi-word "
             "query as an AND of its separate words, so `large language model` returned a 2003 campaign-finance law "
             "containing \"large\", \"language\" and \"model\" in unrelated sentences. Queries were therefore quoted "
             "for phrase matching, and every hit was then re-checked against the bill's own text before being "
             "included. That re-check is why each entry below lists the AI wording actually found and how many times "
             "it occurs.")
    L.append("")
    L.append(f"Of {len(bills)} matters the search returned, **{len(kept)}** are reported here. "
             f"{len(buckets['passing'])} that mention the vocabulary only once, in passing, inside a bill about "
             f"something else are in [Appendix A](#appendix-a--passing-mentions); "
             f"{len(buckets['excluded'])} that contain no AI wording at all are in "
             f"[Appendix B](#appendix-b--search-hits-rejected-on-inspection).")
    L.append("")
    L.append("**Committee attribution.** A matter is filed under the committee Legistar lists as having it in "
             "control, which is where it ended up rather than everywhere it was heard. A few bills were heard "
             "jointly — Res 0766-2023, for instance, was laid over in both Technology and Education before "
             "Education reported it out — and each committee's action history appears in that matter's entry.")
    L.append("")
    L.append("Each entry is labelled by how central AI is to it:")
    L.append("")
    L.append("| Label | Meaning |")
    L.append("| --- | --- |")
    L.append("| Directly about AI | AI is named in the bill's title or summary |")
    L.append("| Subject is an AI-adjacent technology | The bill is about facial recognition, biometrics, "
             "algorithmic tools, robots or autonomous vehicles |")
    L.append("| AI provisions inside a broader bill | AI is regulated by a bill whose headline subject is something else |")
    L.append("| Algorithmic / automated-decision provisions inside a broader bill | Same, for the adjacent vocabulary |")
    L.append("")

    L.append("## Committee scorecard")
    L.append("")
    L.append("| Committee | Matters | Became law | Resolutions adopted | Still pending | Died / filed |")
    L.append("| --- | ---: | ---: | ---: | ---: | ---: |")
    for c in order:
        rows = by_committee[c]
        n = Counter(b["status"] for b in rows)
        dead = sum(v for k, v in n.items() if k.startswith("Filed") or k in {"Withdrawn", "Vetoed"})
        live = n["Committee"] + n["Laid Over in Committee"]
        L.append(f"| {c} | {len(rows)} | {n['Enacted']} | {n['Adopted']} | {live} | {dead} |")
    L.append(f"| **Total** | **{len(kept)}** | **{counts['Enacted']}** | **{counts['Adopted']}** | "
             f"**{len(pending)}** | **{sum(v for k, v in counts.items() if k.startswith('Filed') or k in {'Withdrawn', 'Vetoed'})}** |")
    L.append("")

    L.append("## What became law")
    L.append("")
    L.append("| Local Law | File | Committee | Subject | Enacted |")
    L.append("| --- | --- | --- | --- | --- |")
    for b in sorted(enacted, key=lambda b: datekey(b.get("enactment_date")), reverse=True):
        L.append(f"| {b.get('law_number') or 'pending'} | [{b['file_number']}]({b['url']}) | "
                 f"{b['committee']} | {(b.get('name') or '').rstrip('.')} | {b.get('enactment_date') or 'n/a'} |")
    L.append("")
    L.append("Adopted resolutions (Council positions, not binding law):")
    L.append("")
    L.append("| File | Committee | Subject | Adopted |")
    L.append("| --- | --- | --- | --- |")
    for b in sorted(adopted, key=lambda b: datekey(b.get("completed_date")), reverse=True):
        L.append(f"| [{b['file_number']}]({b['url']}) | {b['committee']} | "
                 f"{(b.get('name') or '').rstrip('.')} | {b.get('completed_date') or 'n/a'} |")
    L.append("")

    L.append("## Legislation by committee")
    L.append("")
    for c in order:
        rows = by_committee[c]
        n = Counter(b["status"] for b in rows)
        L.append(f"### {c}")
        L.append("")
        bits = [f"**{len(rows)}** AI-related matters"]
        if n["Enacted"]:
            bits.append(f"{n['Enacted']} became law")
        if n["Adopted"]:
            bits.append(f"{n['Adopted']} adopted")
        live = n["Committee"] + n["Laid Over in Committee"]
        if live:
            bits.append(f"{live} still pending")
        dead = sum(v for k, v in n.items() if k.startswith("Filed"))
        if dead:
            bits.append(f"{dead} died in committee")
        L.append(f"{'; '.join(bits)}.")
        L.append("")
        for bill in rows:
            render_bill(bill, L)
        L.append("---")
        L.append("")

    L.append("## Appendix A — passing mentions")
    L.append("")
    L.append("These bills use AI or algorithmic vocabulary once, incidentally, inside legislation about something "
             "else — a fire-code formula called an \"algorithm\", a surveillance-reporting bill that lists "
             "\"biometric\" among data types. They are listed for completeness with the sentence that matched.")
    L.append("")
    for b in sorted(buckets["passing"], key=lambda b: (b["committee"], b["file_number"])):
        terms = ", ".join(f"{t['term']} (×{t['count']})" for t in b["verified_terms"])
        L.append(f"- **[{b['file_number']}]({b['url']})** — {b.get('name') or b.get('title', '')} "
                 f"*({b['committee']}; {b['status']})*")
        L.append(f"  - Matched: {terms}")
        ctx = b["verified_terms"][0].get("context", "")
        if ctx:
            L.append(f"  - In context: *{ctx}*")
    L.append("")

    L.append("## Appendix B — search hits rejected on inspection")
    L.append("")
    L.append("Legistar returned these because its index matched the words of a query separately. None contains any "
             "AI vocabulary, so none is counted above.")
    L.append("")
    for b in sorted(buckets["excluded"], key=lambda b: b["file_number"]):
        q = ", ".join(sorted({h["query"] for h in b["search_hits"]}))
        L.append(f"- [{b['file_number']}]({b['url']}) — {b.get('name') or b.get('title', '')} "
                 f"*(returned by: {q})*")
    L.append("")

    OUT.write_text("\n".join(L), encoding="utf-8")
    print(f"{len(kept)} substantive, {len(buckets['passing'])} passing, {len(buckets['excluded'])} excluded")
    print(f"{roll_calls} roll calls rendered -> {OUT}")


if __name__ == "__main__":
    main()
