"""Ghana GHANEPS (ePPS platform) public "Current Tenders" list:
https://www.ghaneps.gov.gh/epps/quickSearchAction.do?searchSelect=6
Plain HTML displaytag table, 10 rows/page (~12 pages), no login/captcha.
We read every page sorted by publication date (newest first) and stop once a
page is entirely older than ctx.since.
"""
import html as _html
import re

from ..core import Candidate, PortalInfo, PortalResult, RunContext, get, parse_date

PORTAL = PortalInfo(key="ghaneps", name="Ghana GHANEPS current tenders", region="Africa",
                    method="Public HTML list (ePPS displaytag)", min_rows=20,
                    url="https://www.ghaneps.gov.gh/epps/quickSearchAction.do?searchSelect=6")

BASE = "https://www.ghaneps.gov.gh"
LIST = BASE + "/epps/quickSearchAction.do"
MAX_PAGES = 40


def _t(s):
    return re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def _rows(page):
    tb = re.search(r'<table id="T01".*?<tbody>(.*?)</tbody>', page, re.S)
    if not tb:
        return None
    out = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", tb[1], re.S):
        tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
        if len(tds) < 9:
            continue
        link = re.search(r'href="(/epps/cft/prepareViewCfTWS\.do\?resourceId=(\d+))"', tds[1])
        info = re.search(r"title='([^']*)'", tds[3]) or re.search(r'title="([^"]*)"', tds[3])
        out.append(dict(title=_t(tds[1]), url=BASE + _html.unescape(link[1]) if link else "",
                        rid=link[2] if link else "", buyer=_t(tds[2]), info=_html.unescape(info[1]) if info else "",
                        deadline=_t(tds[4]), procedure=_t(tds[5]), status=_t(tds[6]), published=_t(tds[8])))
    return out


def fetch(ctx: RunContext) -> PortalResult:
    res = PortalResult(portal=PORTAL.key)
    since = ctx.since.isoformat()
    seen = {}
    try:
        for p in range(1, MAX_PAGES + 1):
            # displaytag: s=sort column, o=1 descending
            r = get(LIST, params={"searchSelect": 6, "d-3680175-s": "datePublished", "d-3680175-o": 1,
                                  "d-3680175-p": p}, timeout=ctx.timeout)
            res.queries += 1
            if r.status_code != 200:
                res.errors.append(f"page {p}: HTTP {r.status_code}")
                break
            rows = _rows(r.text)
            if rows is None:
                if p == 1:
                    res.errors.append("results table T01 not found (layout change?)")
                break
            res.rows_seen += len(rows)
            fresh = 0
            for d in rows:
                pub = parse_date(d["published"])
                if pub and pub < since:
                    continue
                fresh += 1
                seen.setdefault(d["rid"] or d["title"], Candidate(
                    portal="ghaneps", ref=d["rid"], title=d["title"], url=d["url"] or PORTAL.url,
                    buyer=d["buyer"], country="Ghana", published=pub, deadline=parse_date(d["deadline"]),
                    description=d["info"], notice_type="tender", language="en",
                    extra={"procedure": d["procedure"], "status": d["status"]}))
            if len(rows) < 10 or fresh == 0:
                break
    except Exception as e:  # noqa: BLE001
        res.errors.append(f"{type(e).__name__}: {e}")
    res.candidates = list(seen.values())
    return res
