"""Oman Tender Board e-Tendering public dashboard, "New Tenders" list:
https://etendering.tenderboard.gov.om/product/publicDash?viewFlag=NewTenders&pageNo=N
Server-rendered HTML, 50 rows/page, newest tenders first; no login.
The list shows no publication date, only sales-end / bid-closing dates, and
older stale entries trail at the end (2024 closings by page ~30). We read
pages until every closing date on a page is before ctx.since (or a time
budget). Notice (NIT) pages need a signed session URL, so url points to the
list; the tender number is the ref (search it on the portal).
Titles are Arabic (the full title comes from the hidden tendDesc field).
"""
import html as _html
import re
import time

from ..core import Candidate, PortalInfo, PortalResult, RunContext, get, parse_date

PORTAL = PortalInfo(key="omantb", name="Oman Tender Board e-Tendering", region="Middle East",
                    method="Public dashboard HTML (New Tenders, paged)", min_rows=50,
                    url="https://etendering.tenderboard.gov.om/product/publicDash?viewFlag=NewTenders")

LIST = "https://etendering.tenderboard.gov.om/product/publicDash"
BUDGET_S = 100
MAX_PAGES = 60


def _t(s):
    return re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def _parse(page):
    out = []
    for tr in re.findall(r"<tr class='(?:oddo|even) gradeA'>(.*?)</tr>", page, re.S):
        no = re.search(r"showTndDesc\('tendDesc','\d+'\)\"\s*>(.*?)</span>", tr, re.S)
        full = re.search(r'name="tendDesc\d+" value="([^"]*)"', tr)
        tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
        nit = re.search(r"getNit\('(\d+)'\)", tr)
        dates = re.search(r"Sales EndDate:([\d-]*)-Bid Closing Date:([\d-]*)", tr)
        txt = [_t(x) for x in tds]
        out.append(dict(no=_t(no[1]) if no else "", title=_t(full[1]) if full else (txt[2] if len(txt) > 2 else ""),
                        entity=txt[3] if len(txt) > 3 else "", category=txt[4] if len(txt) > 4 else "",
                        ttype=txt[5] if len(txt) > 5 else "", sales_end=dates[1] if dates else "",
                        closing=dates[2] if dates else "", nit=nit[1] if nit else "",
                        fee=txt[7] if len(txt) > 7 else ""))
    return out


def fetch(ctx: RunContext) -> PortalResult:
    res = PortalResult(portal=PORTAL.key)
    since = ctx.since.isoformat()
    seen = {}
    t0 = time.time()
    try:
        for p in range(1, MAX_PAGES + 1):
            if time.time() - t0 > BUDGET_S:
                res.notes.append(f"stopped at time budget after page {p - 1}")
                break
            r = get(LIST, params={"viewFlag": "NewTenders", "pageNo": p}, timeout=ctx.timeout)
            res.queries += 1
            if r.status_code != 200:
                res.errors.append(f"page {p}: HTTP {r.status_code}")
                break
            rows = _parse(r.text)
            res.rows_seen += len(rows)
            if not rows:
                if p == 1:
                    res.errors.append("no rows on page 1 (layout change?)")
                break
            live = 0
            for d in rows:
                closing = parse_date(d["closing"])
                if closing and closing < since:
                    continue  # closed before the window started: cannot be new
                live += 1
                key = d["nit"] or d["no"]
                seen.setdefault(key, Candidate(
                    portal="omantb", ref=d["no"] or d["nit"], title=d["title"], url=PORTAL.url,
                    buyer=d["entity"], country="Oman", deadline=closing,
                    description=" | ".join(x for x in [d["category"], d["ttype"]] if x),
                    notice_type="tender", language="ar",
                    extra={"nit_id": d["nit"], "sales_end": parse_date(d["sales_end"]), "fee": d["fee"]}))
            if live == 0 or len(rows) < 50:
                break
    except Exception as e:  # noqa: BLE001
        res.errors.append(f"{type(e).__name__}: {e}")
    res.candidates = list(seen.values())
    return res
