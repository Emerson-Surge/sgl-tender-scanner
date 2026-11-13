"""Shared types and helpers for portal adapters.

Adapter contract (every module in scanner/portals/ exposes):
    PORTAL = PortalInfo(key="ted", name="TED (EU)", region="Europe", method="Official API v3", min_rows=1)
    def fetch(ctx: RunContext) -> PortalResult

`fetch` must never raise for network/parse trouble: catch, put the message in
result.errors, and return. rows_seen counts every row the portal returned
(matching or not) so the health check can tell "quiet week" from "page broke".
Adapters return ALL rows as Candidates (matched or not); the runner applies the
matcher. If a portal supports server-side keyword search, the adapter may
search with keywords, but should still return every row it got back.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import gzip
import json
import os
import subprocess
import time
import zlib
from dataclasses import dataclass, field
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0 Safari/537.36")
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json;q=0.8,*/*;q=0.7",
    "Accept-Language": "en-US,en;q=0.9,fr;q=0.8,pt;q=0.7,es;q=0.6",
}


@dataclass
class PortalInfo:
    key: str
    name: str
    region: str
    method: str
    min_rows: int = 1          # fewer rows than this => "possible layout change" warning
    url: str = ""              # human URL to open when checking by hand
    uses_browser: bool = False


@dataclass
class Candidate:
    portal: str
    ref: str                   # portal's own reference/ID; "" if none
    title: str
    url: str
    buyer: str = ""
    country: str = ""
    published: str = ""        # ISO date if known
    deadline: str = ""         # ISO date if known
    description: str = ""
    value: str = ""
    notice_type: str = ""      # tender / award / prior-info / etc.
    language: str = ""
    extra: dict = field(default_factory=dict)
    match: dict | None = None  # filled by runner

    def key(self) -> str:
        return f"{self.portal}:{self.ref or self.url}"

    def to_dict(self):
        return dataclasses.asdict(self)


@dataclass
class PortalResult:
    portal: str
    rows_seen: int = 0
    queries: int = 0
    candidates: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    seconds: float = 0.0

    @property
    def status(self) -> str:
        if self.errors and self.rows_seen == 0:
            return "FAIL"
        if self.errors:
            return "WARN"
        return "OK"


@dataclass
class RunContext:
    since: dt.date            # include notices published on/after this date
    today: dt.date
    timeout: int = 40
    cache_dir: Path = ROOT / "cache"

    def log(self, *a):
        print(*a, flush=True)


_session = requests.Session()
_session.headers.update(HEADERS)


def http(method: str, url: str, *, retries: int = 2, timeout: int = 40, **kw) -> requests.Response:
    """HTTP with browser headers and retry on transport errors / 5xx / 429."""
    last = None
    for attempt in range(retries + 1):
        try:
            r = _session.request(method, url, timeout=timeout, **kw)
            if r.status_code in (429, 500, 502, 503, 504) and attempt < retries:
                time.sleep(2 + attempt * 3)
                continue
            return r
        except requests.RequestException as e:  # transport failure
            last = e
            if attempt < retries:
                time.sleep(2 + attempt * 3)
    raise last  # type: ignore[misc]


def get(url, **kw):
    return http("GET", url, **kw)


def post(url, **kw):
    return http("POST", url, **kw)


def browser(urls: list[str], *, wait_ms: int = 4000, wait_for: str | None = None,
            timeout_ms: int = 60000, html: bool = False) -> list[dict]:
    """Render pages in headless Chromium (Node Playwright). Returns
    [{url, final_url, status, text, html?, error?}] in input order."""
    payload = json.dumps({"urls": urls, "wait_ms": wait_ms, "wait_for": wait_for,
                          "timeout_ms": timeout_ms, "html": html})
    p = subprocess.run(["node", str(ROOT / "scanner" / "render.js")], input=payload,
                       capture_output=True, text=True, timeout=60 + len(urls) * (timeout_ms / 1000 + wait_ms / 1000 + 10))
    if p.returncode != 0:
        return [{"url": u, "error": p.stderr[-500:]} for u in urls]
    return json.loads(p.stdout)


def parse_date(s) -> str:
    """Best-effort to ISO yyyy-mm-dd; returns '' if unparseable."""
    if not s:
        return ""
    s = str(s).strip()
    import re
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return f"{m[1]}-{m[2]}-{m[3]}"
    m = re.search(r"(\d{4})(\d{2})(\d{2})", s)
    if m and 1990 < int(m[1]) < 2100 and int(m[2]) <= 12:
        return f"{m[1]}-{m[2]}-{m[3]}"
    m = re.search(r"(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})", s)
    if m:  # assume day-first (most portals in scope); US portals should parse themselves
        d, mo, y = int(m[1]), int(m[2]), int(m[3])
        if mo > 12:
            d, mo = mo, d
        try:
            return dt.date(y, mo, d).isoformat()
        except ValueError:
            return ""
    months = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8,
              "sep": 9, "oct": 10, "nov": 11, "dec": 12}
    m = re.search(r"(\d{1,2})[\s\-]([A-Za-z]{3})[A-Za-z]*[\s\-,]+(\d{4})", s)
    if m and m[2].lower() in months:
        return dt.date(int(m[3]), months[m[2].lower()], int(m[1])).isoformat()
    m = re.search(r"([A-Za-z]{3})[A-Za-z]*\.?\s+(\d{1,2}),?\s+(\d{4})", s)
    if m and m[1].lower() in months:
        return dt.date(int(m[3]), months[m[1].lower()], int(m[2])).isoformat()
    return ""
