"""PhilGEPS (Philippines), Modernized PhilGEPS public "Open Opportunities".

https://philgeps.gov.ph/Indexes/viewMoreOpenTenders is the public bulletin
board (~15,000 open notices, 20 per page; tested 13 Nov 2026). Its search form
(searchKeyword + the page's own _csrfToken, same session) filters by keyword;
re-posting the form to ?page=N pages through the filtered result. Fields:
reference no., title, mode, classification, agency, publish date, closing date. Rows published before ctx.since are counted, not returned.

The legacy board (notices.philgeps.gov.ph/GEPSNONPILOT, PhilGEPS 1.5) only
renders its category index without interactive ASP.NET postbacks, and a plain
GET there redirects to its error page, so it is not covered here.
"""
import html as _html
import re

import requests

from ..core import HEADERS, Candidate, PortalInfo, PortalResult, RunContext, parse_date

PORTAL = PortalInfo(key="philgeps", name="PhilGEPS (Philippines)", region="Asia-Pacific",
                    method="Public open-opportunities keyword search (form)", min_rows=10,
                    url="https://philgeps.gov.ph/Indexes/viewMoreOpenTenders")

B = "https://philgeps.gov.ph"
URL = B + "/Indexes/viewMoreOpenTenders"
KEYWORDS = ["geophysical", "geophysics", "airborne", "aerial", "magnetic", "magnetometer", "gravity",
            "radiometric", "gamma", "electromagnetic", "lidar", "survey", "geological", "geohazard",
            "mineral", "exploration", "photogrammetry", "mapping"]
MAX_PAGES = 8
ROW = re.compile(r"<tr>\s*<td data-label=\"Bid Notice Reference Number\">(.*?)</tr>", re.S)


def _t(s):
    return re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def _cell(row, label):
    m = re.search(r'data-label="' + re.escape(label) + r'"[^>]*>(.*?)</td>', row, re.S)
    return _t(m[1]) if m else ""


def _parse(page, res, seen, kw):
    rows = ROW.findall(page)
    for body in rows:
        row = '<td data-label="Bid Notice Reference Number">' + body
        m = re.search(r'href="([^"]*viewLiveTenderDetails/(\d+)[^"]*)"', row)
        if not m:
            continue
        res.rows_seen += 1
        ref = m[2]
        if ref in seen:
            if kw not in seen[ref].extra["keywords"]:
                seen[ref].extra["keywords"].append(kw)
            continue
        seen[ref] = Candidate(
            portal=PORTAL.key, ref=ref, title=_cell(row, "Control Number"),
            url=f"{B}/Indexes/viewLiveTenderDetails/{ref}", buyer=_cell(row, "Agency Name"),
            country="Philippines", published=parse_date(_cell(row, "Publish Date")),
            deadline=parse_date(_cell(row, "Closing date")), notice_type=_cell(row, "Mode of Procurement"),
            extra={"classification": _cell(row, "Business Category"), "keywords": [kw]},
        )
    return len(rows)


def fetch(ctx: RunContext) -> PortalResult:
    res = PortalResult(portal=PORTAL.key)
    since = ctx.since.isoformat()
    seen = {}
    try:
        s = requests.Session()
        s.headers.update(HEADERS)
        r = s.get(URL, timeout=ctx.timeout)
        res.queries += 1
        tok = re.search(r'name="_csrfToken"[^>]*value="([^"]+)"', r.text)
        if r.status_code != 200 or not tok:
            res.errors.append(f"bulletin page HTTP {r.status_code}; form token {'found' if tok else 'missing'}")
            return res
        for kw in KEYWORDS:
            try:
                form = {"_csrfToken": tok[1], "searchKeyword": kw, "searchModeProc": "",
                        "searchClassification": "", "searchApplicableProcRule": ""}
                r = s.post(URL, data=form, timeout=ctx.timeout)
                res.queries += 1
                if r.status_code != 200:
                    res.errors.append(f"search '{kw}': HTTP {r.status_code}")
                    continue
                n = re.search(r"Page \d+ of (\d+), showing \d+ record\(s\) out of ([\d,]+) total", r.text)
                if not n:
                    res.errors.append(f"search '{kw}': result counter missing (layout change?)")
                    continue
                _parse(r.text, res, seen, kw)
                pages = int(n[1])
                for p in range(2, min(pages, MAX_PAGES) + 1):
                    # the form re-posted with ?page=N keeps the keyword filter
                    rp = s.post(f"{URL}?page={p}", data=form, timeout=ctx.timeout)
                    res.queries += 1
                    dates = [parse_date(d) for d in re.findall(r'data-label="Publish Date"><span>([^<]*)', rp.text)]
                    if rp.status_code != 200 or _parse(rp.text, res, seen, kw) == 0:
                        break
                    if dates and all(d and d < since for d in dates):
                        break  # newest first: whole page older than the window
                if pages > MAX_PAGES:
                    res.notes.append(f"'{kw}': {n[2]} hits, first {MAX_PAGES} pages read")
            except Exception as e:  # noqa: BLE001
                res.errors.append(f"search '{kw}': {type(e).__name__}: {e}")
    except Exception as e:  # noqa: BLE001
        res.errors.append(f"{type(e).__name__}: {e}")
    res.candidates = [c for c in seen.values() if not c.published or c.published >= since]
    return res
