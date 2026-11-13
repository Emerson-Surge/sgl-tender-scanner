"""Tenders WA (Western Australia): public "Open tenders" list (plain requests).

The home page links the public open-tender search with a per-session
CSRFNONCE; following that link in the same session returns every current
tender on one page (~180 rows, tested 13 Nov 2026): agency, category,
reference, type, title, UNSPSC, closing date, tender id. No publication date
on the list, so ctx.since is not applicable (state de-duplicates).
"""
import html as _html
import re

import requests

from ..core import HEADERS, Candidate, PortalInfo, PortalResult, RunContext, parse_date

PORTAL = PortalInfo(key="tenderswa", name="Tenders WA (Western Australia)", region="Asia-Pacific",
                    method="Public open-tender list", min_rows=50,
                    url="https://www.tenders.wa.gov.au/watenders/index.do")

B = "https://www.tenders.wa.gov.au"
ROW = re.compile(r'<tr class=\s*"(?:even|odd)"\s*>(.*?)</tr>', re.S)


def _t(s):
    return re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def fetch(ctx: RunContext) -> PortalResult:
    res = PortalResult(portal=PORTAL.key)
    try:
        s = requests.Session()
        s.headers.update(HEADERS)
        r = s.get(f"{B}/watenders/index.do", timeout=ctx.timeout)
        res.queries += 1
        m = re.search(r'(/watenders/tender/search/tender-search\.action\?action=advanced-tender-search-open-tender'
                      r'&(?:amp;)?CSRFNONCE=\w+)', r.text)
        if r.status_code != 200 or not m:
            res.errors.append(f"home page HTTP {r.status_code}; open-tender link {'found' if m else 'missing'}")
            return res
        r = s.get(B + _html.unescape(m[1]), timeout=ctx.timeout)
        res.queries += 1
        if r.status_code != 200:
            res.errors.append(f"open tenders: HTTP {r.status_code}")
            return res
        seen = {}
        for body in ROW.findall(r.text):
            tid = re.search(r"tender-details\.action\?id=(\d+)", body)
            if not tid:
                continue
            res.rows_seen += 1
            if tid[1] in seen:
                continue
            tds = re.findall(r"<td[^>]*>(.*?)</td>", body, re.S)
            title = re.search(r'<a href="/watenders/tender/display/tender-details[^"]*"\s*>(.*?)</a>', body, re.S)
            refcell = tds[2] if len(tds) > 2 else ""
            ref = re.search(r"<b>(.*?)</b>", refcell, re.S)
            ttype = _t(refcell.rsplit("<br>", 1)[-1]) if "<br>" in refcell else ""
            issued = re.search(r"Issued by\s*(.*?)\s*<br>", body, re.S)
            unspsc = re.search(r"UNSPSC:\s*(.*?)</span>", body, re.S)
            closing = re.search(r'SUMMARY_CLOSINGDATE">(.*?)</span>', body, re.S)
            seen[tid[1]] = Candidate(
                portal=PORTAL.key, ref=tid[1], title=_t(title[1] if title else ""),
                url=f"{B}/watenders/tender/display/tender-details.action?id={tid[1]}&action=display-tender-details",
                buyer=_t(issued[1]) if issued else _t(tds[0] if tds else ""), country="Australia (WA)",
                deadline=parse_date(_t(closing[1]) if closing else ""), notice_type=ttype,
                description=("UNSPSC: " + _t(unspsc[1])) if unspsc else "",
                extra={"reference": _t(ref[1]) if ref else "", "category": _t(tds[1]) if len(tds) > 1 else ""},
            )
        res.candidates = list(seen.values())
        if not seen:
            res.errors.append("no tender rows parsed (layout change?)")
    except Exception as e:  # noqa: BLE001
        res.errors.append(f"{type(e).__name__}: {e}")
    return res
