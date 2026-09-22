# NYC Council AI legislation scanner

Scrapes the New York City Council's Legistar Legislative Research Center for
every matter touching artificial intelligence, and writes
[`AI_LEGISLATION_BY_COMMITTEE.md`](AI_LEGISLATION_BY_COMMITTEE.md) — a report
broken down committee by committee, with each bill's status, sponsors, dates,
and full roll-call votes.

## Why it scrapes instead of using the API

Legistar publishes a Web API at `webapi.legistar.com/v1/nyc`, but it now answers
`403 Token is required`, and the Council only issues tokens by email request.
The scraper therefore drives the advanced-search form on
`legistar.council.nyc.gov` directly. Two details make that work:

- The year, result-limit and committee filters exist only on the **advanced**
  search panel, reached by posting the `btnSwitch` button.
- Telerik's `RadComboBox` posts its selection in a hidden `_ClientState` field
  whose form name uses **underscores**
  (`ctl00_ContentPlaceHolder1_lstYearsAdvanced_ClientState`) while every other
  control on the page uses `$`. Post the `$` variant and the server silently
  keeps its old selection — which is why a naive scrape only ever returns the
  current year.

## Why every hit is re-verified

Legistar treats an unquoted multi-word query as an AND of its separate words.
Searching `large language model` returns a 2003 campaign-finance law that
contains "large", "language" and "model" in unrelated sentences. Queries are
quoted for phrase matching, and then every hit is re-checked against the bill's
own text before it is reported. Matters are sorted into three buckets:

| Bucket | Meaning |
| --- | --- |
| substantive | AI vocabulary in the title/summary, an unambiguous term anywhere, or repeated use |
| passing | one incidental mention inside a bill about something else (Appendix A) |
| excluded | no AI vocabulary at all — a pure search artefact (Appendix B) |

## Running it

```bash
pip install -r requirements.txt
cd scraper
python collect.py    # sweep the search form -> data/search_results.json
python enrich.py     # detail pages, histories, roll calls -> data/bills.json
python report.py     # -> AI_LEGISLATION_BY_COMMITTEE.md
```

`enrich.py` is resumable: it skips matters already in `data/bills.json`, so an
interrupted run can simply be restarted. A full run takes about six minutes and
makes roughly 200 requests, paced by the `delay` argument in `LegistarClient`.

`python diagnose.py` prints what the classifier kept, demoted and dropped, with
the matching sentence for each borderline case.

## Layout

| File | Purpose |
| --- | --- |
| `scraper/legistar.py` | Session, ASP.NET form plumbing, search-result parsing |
| `scraper/terms.py` | Search vocabulary and the verification patterns |
| `scraper/collect.py` | Runs the searches, de-duplicates by matter ID |
| `scraper/enrich.py` | Detail page, sponsors, dates, action history, roll calls |
| `scraper/classify.py` | Substantive / passing / excluded decision |
| `scraper/report.py` | Renders the markdown report |
| `data/bills.json` | Structured record of every matter, including vote rosters |
| `data/fulltext.json` | Cached bill text, so classification can be retuned offline |
