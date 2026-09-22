"""Fetch each matter's detail page, full text, action history and roll-call votes.

Requesting the page with ``&FullText=1`` returns the metadata, the action
history and the bill text in one response, which is also what lets us confirm
that the AI vocabulary really appears rather than trusting Legistar's
word-splitting search index.

Writes data/bills.json incrementally so an interrupted run can resume.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from bs4 import BeautifulSoup

from legistar import BASE, LegistarClient, clean
from terms import verify

DATA = Path(__file__).resolve().parent.parent / "data"
RESULTS = DATA / "search_results.json"
OUT = DATA / "bills.json"
TEXTS = DATA / "fulltext.json"

RADOPEN = re.compile(r"radopen\('([^']+)'")

# Actions that end a matter's life, used to date "completed".
# Legistar writes the Council's own vote as "Approved, by Council" (with the
# comma) to distinguish it from "Approved by Committee", which is not final.
FINAL_ACTIONS = re.compile(
    r"approved,\s*by\s+council|adopted|signed into law|returned unsigned"
    r"|vetoed|filed|withdrawn|disapproved|failed",
    re.I,
)


def text_of(soup, element_id: str) -> str:
    tag = soup.find(id=element_id)
    return clean(tag.get_text(" ", strip=True)) if tag else ""


def parse_votes(soup) -> dict:
    grid = soup.find("table", id="ctl00_ContentPlaceHolder1_gridVote_ctl00")
    tally: dict[str, list[str]] = {}
    if grid is not None:
        body = grid.find("tbody")
        for tr in (body.find_all("tr", recursive=False) if body else []):
            cells = tr.find_all("td", recursive=False)
            if len(cells) < 2:
                continue
            person, vote = clean(cells[0].get_text()), clean(cells[1].get_text())
            if person:
                tally.setdefault(vote or "Unrecorded", []).append(person)
    return {
        "mover": text_of(soup, "ctl00_ContentPlaceHolder1_lblMover"),
        "seconder": text_of(soup, "ctl00_ContentPlaceHolder1_lblSeconder"),
        "result": text_of(soup, "ctl00_ContentPlaceHolder1_lblResult"),
        "action": text_of(soup, "ctl00_ContentPlaceHolder1_lblAction"),
        "action_text": text_of(soup, "ctl00_ContentPlaceHolder1_lblActionText"),
        "agenda_note": text_of(soup, "ctl00_ContentPlaceHolder1_lblAgendaNote"),
        "minutes_note": text_of(soup, "ctl00_ContentPlaceHolder1_lblMinutesNote"),
        "votes": tally,
    }


def parse_history(client: LegistarClient, soup) -> list[dict]:
    grid = soup.find("table", id="ctl00_ContentPlaceHolder1_gridLegislation_ctl00")
    if grid is None:
        return []
    body = grid.find("tbody")
    history = []
    for tr in (body.find_all("tr", recursive=False) if body else []):
        cells = tr.find_all("td", recursive=False)
        if len(cells) < 6:
            continue
        entry = {
            "date": clean(cells[0].get_text()),
            "version": clean(cells[1].get_text()),
            "prime_sponsor": clean(cells[2].get_text()),
            "action_by": clean(cells[3].get_text()),
            "action": clean(cells[4].get_text()),
            "result": clean(cells[5].get_text()),
            "detail_url": "",
        }
        link = tr.find("a", id=re.compile("hypDetails"))
        if link is not None:
            m = RADOPEN.search(link.get("onclick", "") or "")
            if m:
                entry["detail_url"] = f"{BASE}/{m.group(1).replace('&amp;', '&')}"
        # Only recorded votes have a Result; skip the rest to save requests.
        if entry["result"] and entry["detail_url"]:
            vsoup = BeautifulSoup(client.get(entry["detail_url"]), "lxml")
            entry.update(parse_votes(vsoup))
        history.append(entry)
    return history


def scrape_bill(client: LegistarClient, rec: dict, texts: dict[str, str]) -> dict:
    soup = BeautifulSoup(client.get(rec["url"] + "&FullText=1"), "lxml")
    sponsors_cell = soup.find(id="ctl00_ContentPlaceHolder1_lblSponsors2")
    sponsors = (
        [clean(a.get_text()) for a in sponsors_cell.find_all("a")]
        if sponsors_cell
        else []
    )
    if sponsors_cell is not None and not sponsors:
        sponsors = [s for s in re.split(r"\s+,\s+", clean(sponsors_cell.get_text())) if s]

    bill = dict(rec)
    bill.update(
        {
            "file_number": text_of(soup, "ctl00_ContentPlaceHolder1_lblFile2") or rec["file_number"],
            "name": text_of(soup, "ctl00_ContentPlaceHolder1_lblName2"),
            "type": text_of(soup, "ctl00_ContentPlaceHolder1_lblType2") or rec["type"],
            "status": text_of(soup, "ctl00_ContentPlaceHolder1_lblStatus2") or rec["status"],
            "committee": text_of(soup, "ctl00_ContentPlaceHolder1_hypInControlOf2") or rec["committee"],
            "intro_date": text_of(soup, "ctl00_ContentPlaceHolder1_lblOnAgenda2"),
            "enactment_date": text_of(soup, "ctl00_ContentPlaceHolder1_lblEnactmentDate2"),
            "law_number": text_of(soup, "ctl00_ContentPlaceHolder1_lblEnactmentNumber2") or rec["law_number"],
            "title": text_of(soup, "ctl00_ContentPlaceHolder1_lblTitle2") or rec["title"],
            "summary": text_of(soup, "ctl00_ContentPlaceHolder1_lblSummary2"),
            "indexes": text_of(soup, "ctl00_ContentPlaceHolder1_lblIndexes2"),
            "sponsors": sponsors,
            "prime_sponsor": sponsors[0] if sponsors else rec["prime_sponsor"],
            "sponsor_count": text_of(soup, "ctl00_ContentPlaceHolder1_lblCMSponsors2") or rec["sponsor_count"],
        }
    )
    text_div = soup.find(id="ctl00_ContentPlaceHolder1_divText")
    full_text = clean(text_div.get_text(" ", strip=True)) if text_div else ""
    subject = " ".join([bill["name"], bill["title"], bill["summary"]])
    bill["has_full_text"] = bool(full_text)
    bill["subject_terms"] = verify(subject)
    bill["verified_terms"] = verify(subject + " " + full_text, with_context=True)
    texts[rec["matter_id"]] = f"{subject}\n{full_text}"

    bill["history"] = parse_history(client, soup)

    introduced = [h for h in bill["history"] if "introduced" in h["action"].lower()]
    bill["introduced_date"] = introduced[-1]["date"] if introduced else bill["intro_date"]
    finals = [h for h in bill["history"] if FINAL_ACTIONS.search(h["action"])]
    bill["completed_date"] = bill["enactment_date"] or (finals[0]["date"] if finals else "")
    bill["final_action"] = finals[0]["action"] if finals else ""
    return bill


def main() -> None:
    records = json.loads(RESULTS.read_text(encoding="utf-8"))
    done: dict[str, dict] = {}
    if OUT.exists():
        done = {b["matter_id"]: b for b in json.loads(OUT.read_text(encoding="utf-8"))}
    texts: dict[str, str] = {}
    if TEXTS.exists():
        texts = json.loads(TEXTS.read_text(encoding="utf-8"))

    client = LegistarClient(delay=0.4)
    for i, rec in enumerate(records, 1):
        if rec["matter_id"] in done:
            continue
        try:
            bill = scrape_bill(client, rec, texts)
        except Exception as exc:  # keep going; report gaps at the end
            print(f"  [{i}/{len(records)}] FAILED {rec['file_number']}: {exc}", flush=True)
            continue
        done[rec["matter_id"]] = bill
        votes = sum(1 for h in bill["history"] if h.get("votes"))
        print(
            f"  [{i}/{len(records)}] {bill['file_number']:<16} {bill['status']:<12}"
            f" {len(bill['history']):>2} actions, {votes} roll calls",
            flush=True,
        )
        if i % 10 == 0:
            OUT.write_text(json.dumps(list(done.values()), indent=2), encoding="utf-8")
            TEXTS.write_text(json.dumps(texts), encoding="utf-8")

    OUT.write_text(json.dumps(list(done.values()), indent=2), encoding="utf-8")
    TEXTS.write_text(json.dumps(texts), encoding="utf-8")
    print(f"\n{len(done)}/{len(records)} bills -> {OUT}")


if __name__ == "__main__":
    main()
