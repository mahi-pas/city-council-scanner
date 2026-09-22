"""Client for the NYC Council Legistar InSite web UI.

The public Legistar Web API (webapi.legistar.com) now returns "403 Token is
required" and tokens are only issued by email request, so this drives the
ASP.NET advanced-search form on legistar.council.nyc.gov directly.

Two quirks of the Telerik/WebForms page drive the design here:

* The year, result-limit, committee and sponsor filters only exist on the
  *advanced* search panel, reached by posting ``btnSwitch``.
* Telerik RadComboBox posts its selection in a hidden ``_ClientState`` field
  whose form name uses underscores (``ctl00_..._lstYearsAdvanced_ClientState``)
  even though every other control on the page uses ``$`` separators. Posting
  the ``$`` variant silently leaves the server-side selection unchanged.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Iterable

import requests
from bs4 import BeautifulSoup

BASE = "https://legistar.council.nyc.gov"
SEARCH_URL = f"{BASE}/Legislation.aspx"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

HIDDEN_FIELDS = (
    "__VIEWSTATE",
    "__VIEWSTATEGENERATOR",
    "__EVENTVALIDATION",
    "__PREVIOUSPAGE",
    "__VIEWSTATEENCRYPTED",
    "ctl00_RadScriptManager1_TSM",
)


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\xa0", " ")).strip()


def combo_state(value: str) -> str:
    return json.dumps(
        {
            "logEntries": [],
            "value": value,
            "text": value,
            "enabled": True,
            "checkedIndices": [],
            "checkedItemsTextOverflows": False,
        }
    )


@dataclass
class SearchResult:
    file_number: str
    url: str
    law_number: str = ""
    type: str = ""
    status: str = ""
    committee: str = ""
    prime_sponsor: str = ""
    sponsor_count: str = ""
    title: str = ""
    matched_terms: set[str] = field(default_factory=set)


class LegistarClient:
    def __init__(self, delay: float = 1.0):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.delay = delay
        self.soup: BeautifulSoup | None = None
        self.advanced = False

    # -- transport ---------------------------------------------------------
    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        last: Exception | None = None
        for attempt in range(5):
            try:
                resp = self.session.request(method, url, timeout=90, **kwargs)
                resp.raise_for_status()
                return resp
            except requests.RequestException as exc:
                last = exc
                time.sleep(2 * (attempt + 1))
        raise RuntimeError(f"{method} {url} failed after retries: {last}")

    def get(self, url: str) -> str:
        time.sleep(self.delay)
        return self._request("GET", url).text

    def post(self, url: str, data: dict) -> str:
        time.sleep(self.delay)
        return self._request("POST", url, data=data).text

    # -- form plumbing -----------------------------------------------------
    def _state(self) -> dict:
        assert self.soup is not None
        out = {}
        for name in HIDDEN_FIELDS:
            tag = self.soup.find("input", {"name": name})
            if tag is not None:
                out[name] = tag.get("value", "")
        return out

    def open_advanced(self) -> None:
        """Load Legislation.aspx and switch it into advanced-search mode."""
        self.soup = BeautifulSoup(self.get(SEARCH_URL), "lxml")
        payload = self._state()
        payload.update(
            {
                "__EVENTTARGET": "",
                "__EVENTARGUMENT": "",
                "ctl00$ContentPlaceHolder1$txtSearch": "",
                "ctl00$ContentPlaceHolder1$lstYears": "This Year",
                "ctl00$ContentPlaceHolder1$lstTypeBasic": "All Types",
                "ctl00$ContentPlaceHolder1$btnSwitch": "Advanced search >>>",
            }
        )
        self.soup = BeautifulSoup(self.post(SEARCH_URL, payload), "lxml")
        self.advanced = True

    def _advanced_payload(self, **overrides) -> dict:
        payload = self._state()
        payload.update(
            {
                "__EVENTTARGET": "ctl00$ContentPlaceHolder1$btnSearch",
                "__EVENTARGUMENT": "",
                "ctl00$ContentPlaceHolder1$lstMax": "10000",
                "ctl00_ContentPlaceHolder1_lstMax_ClientState": combo_state("10000"),
                "ctl00$ContentPlaceHolder1$lstYearsAdvanced": "All Years",
                "ctl00_ContentPlaceHolder1_lstYearsAdvanced_ClientState": combo_state("All Years"),
                "ctl00$ContentPlaceHolder1$txtText": "",
                "ctl00$ContentPlaceHolder1$txtTit": "",
                "ctl00$ContentPlaceHolder1$txtFil": "",
                "ctl00$ContentPlaceHolder1$lstType": "-Select-",
                "ctl00$ContentPlaceHolder1$lstStatus": "-Select-",
                "ctl00$ContentPlaceHolder1$lstInControlOf": "-Select-",
                "ctl00$ContentPlaceHolder1$radOnAgenda": "=",
                "ctl00$ContentPlaceHolder1$lstSponsoredBy": "-Select-",
                "ctl00$ContentPlaceHolder1$lstIndexedUnder": "-Select-",
                "ctl00$ContentPlaceHolder1$txtAtt": "",
            }
        )
        payload.update(overrides)
        return payload

    # -- searching ---------------------------------------------------------
    def search_text(self, term: str) -> list[SearchResult]:
        """Full-text search over bill text across all years."""
        if not self.advanced:
            self.open_advanced()
        payload = self._advanced_payload(
            **{"ctl00$ContentPlaceHolder1$txtText": term}
        )
        self.soup = BeautifulSoup(self.post(SEARCH_URL, payload), "lxml")
        rows = list(self._parse_rows())
        for row in rows:
            row.matched_terms.add(term)
        return rows

    def search_title(self, term: str) -> list[SearchResult]:
        """Search bill titles across all years."""
        if not self.advanced:
            self.open_advanced()
        payload = self._advanced_payload(
            **{"ctl00$ContentPlaceHolder1$txtTit": term}
        )
        self.soup = BeautifulSoup(self.post(SEARCH_URL, payload), "lxml")
        rows = list(self._parse_rows())
        for row in rows:
            row.matched_terms.add(term)
        return rows

    def record_count(self) -> int | None:
        assert self.soup is not None
        m = re.search(r"([\d,]+) records", self.soup.get_text())
        return int(m.group(1).replace(",", "")) if m else None

    def _parse_rows(self) -> Iterable[SearchResult]:
        assert self.soup is not None
        grid = self.soup.find("table", id="ctl00_ContentPlaceHolder1_gridMain_ctl00")
        if grid is None:
            return
        body = grid.find("tbody")
        if body is None:
            return
        for tr in body.find_all("tr", recursive=False):
            cells = tr.find_all("td", recursive=False)
            if len(cells) < 8:
                continue
            link = cells[0].find("a")
            if link is None or not link.get("href"):
                continue
            href = link["href"].replace("&amp;", "&")
            yield SearchResult(
                file_number=clean(link.get_text()),
                url=f"{BASE}/{href.lstrip('/')}",
                law_number=clean(cells[1].get_text()),
                type=clean(cells[2].get_text()),
                status=clean(cells[3].get_text()),
                committee=clean(cells[4].get_text()),
                prime_sponsor=clean(cells[5].get_text()),
                sponsor_count=clean(cells[6].get_text()),
                title=clean(cells[7].get_text()),
            )
