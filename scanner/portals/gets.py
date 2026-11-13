"""New Zealand GETS: public "Current tenders" list (plain requests).

https://www.gets.govt.nz/ExternalIndex.htm?page=N&orderBy=date lists every open
public tender, 25 per page, ~16 pages (tested 13 Nov 2026): RFx ID, reference,
title, type, close date, organisation. No publication date on the list, so the
whole open set is returned each run (state de-duplicates); ctx.since is not
applicable. The keyword search box (ExternalTenderSearching.htm) returned no
rows for plain requests, so the full list is walked instead.
"""
import html as _html
import re

from ..core import Candidate, PortalInfo, PortalResult, RunContext, get, parse_date

PORTAL = PortalInfo(key="gets", name="GETS (New Zealand)", region="Asia-Pacific",
                    method="Public current-tenders list (all pages)", min_rows=100,
                    url="https://www.gets.govt.nz/ExternalIndex.htm")

B = "https://www.gets.govt.nz/"
ROW = re.compile(r'<tr id="tender-(\d+)"[^>]*>(.*?)</tr>', re.S)
TD = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
MAX_PAGES = 40


def _t(s):
    return re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def fetch(ctx: RunContext) -> PortalResult:
    res = PortalResult(portal=PORTAL.key)
    seen = {}
    page, last = 1, 1
    while page <= min(last, MAX_PAGES):
        url = f"{B}ExternalIndex.htm?page={page}&orderBy=date"
        try:
            r = get(url, timeout=ctx.timeout)
            res.queries += 1
            if r.status_code != 200:
                res.errors.append(f"page {page}: HTTP {r.status_code}")
                break
            pages = [int(p) for p in re.findall(r"ExternalIndex\.htm\?page=(\d+)", r.text)]
            last = max(pages + [last])
            rows = ROW.findall(r.text)
            if not rows:
                if page == 1:
                    res.errors.append("no tender rows on page 1 (layout change?)")
                break
            for rid, body in rows:
                res.rows_seen += 1
                tds = TD.findall(body)
                if rid in seen or len(tds) < 6:
                    continue
                href = re.search(r'href="([^"]+)"', tds[0])
                seen[rid] = Candidate(
                    portal=PORTAL.key, ref=rid, title=_t(tds[2]),
                    url=B + href[1].lstrip("/") if href else f"{B}ExternalIndex.htm",
                    buyer=_t(tds[5]), country="New Zealand", deadline=parse_date(_t(tds[4])),
                    notice_type=_t(tds[3]), extra={"reference": _t(tds[1])},
                )
        except Exception as e:  # noqa: BLE001
            res.errors.append(f"page {page}: {type(e).__name__}: {e}")
            break
        page += 1
    res.candidates = list(seen.values())
    return res
