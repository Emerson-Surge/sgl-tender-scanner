"""dgMarket public notice listing, by CPV code (headless render).

A plain `requests` GET answers HTTP 500 here, but a plain headless render of
https://www2.dgmarket.com/NoticeList?cpv=<code> shows the public listing
(tested 13 Nov 2026). Paging is session-based (/NoticeList/changePageSize,
/NoticeList/gotoPage/N), and browser() keeps one cookie context per call, so the
whole sequence goes in one call. Listing fields only: detail pages are
login-gated and are not opened. Rows older than ctx.since (by Create/Change
Date) are counted in rows_seen but not returned.
"""
import html as _html
import re

from ..core import Candidate, PortalInfo, PortalResult, RunContext, browser, parse_date

PORTAL = PortalInfo(key="dgmarket", name="dgMarket (CPV listing)", region="Global",
                    method="Public CPV listing, headless render (listing fields only)", min_rows=10,
                    url="https://www2.dgmarket.com/NoticeList?cpv=71351710", uses_browser=True)

B = "https://www2.dgmarket.com"
CPVS = ["71351710", "71353000", "71351100", "71352300", "71355000"]
PAGES = 3  # x 50 rows per CPV

CARD = re.compile(r'<a class="card-link" href="/Notice/(\d+)">(.*?)</a>(.*?)</table>', re.S)


def _field(block, label):
    m = re.search(r'>\s*' + re.escape(label) + r'\s*:\s*</span>\s*<span>(.*?)</span>', block, re.S)
    return _html.unescape(re.sub(r"<[^>]+>", "", m[1])).strip() if m else ""


def fetch(ctx: RunContext) -> PortalResult:
    res = PortalResult(portal=PORTAL.key)
    since = ctx.since.isoformat()
    seen = {}
    try:
        urls = []
        for i, cpv in enumerate(CPVS):
            urls.append(f"{B}/NoticeList?cpv={cpv}")
            if i == 0:
                urls.append(f"{B}/NoticeList/changePageSize?newPageSize=50")
            urls += [f"{B}/NoticeList/gotoPage/{p}" for p in range(2, PAGES + 1)]
        pages = browser(urls, wait_ms=1200, html=True, timeout_ms=45000)
        res.queries = len(urls)
        cpv = None
        for u, pg in zip(urls, pages):
            m = re.search(r"cpv=(\d+)", u)
            if m:
                cpv = m[1]
            if pg.get("error"):
                res.errors.append(f"{u}: {pg['error'][:200]}")
                continue
            if pg.get("status") and pg["status"] >= 400:
                res.errors.append(f"{u}: HTTP {pg['status']}")
                continue
            for nid, title, block in CARD.findall(pg.get("html", "")):
                if nid in seen:
                    lists = seen[nid].extra["cpv_lists"]
                    if cpv not in lists:
                        lists.append(cpv)
                    continue
                res.rows_seen += 1
                pub = parse_date(_field(block, "Create/Change Date"))
                c = Candidate(
                    portal=PORTAL.key, ref=nid,
                    title=_html.unescape(re.sub(r"<[^>]+>", "", title)).strip(),
                    url=f"{B}/Notice/{nid}",
                    buyer=_field(block, "Buyer"),
                    country=_field(block, "Countries").strip("[]"),
                    published=pub,
                    deadline=parse_date(_field(block, "Deadline")),
                    notice_type=_field(block, "Type"),
                    language=_field(block, "Original Language"),
                    value=_field(block, "Estimated Value"),
                    extra={"cpv_lists": [cpv]},
                )
                seen[nid] = c
        res.candidates = [c for c in seen.values() if not c.published or c.published >= since]
        if not seen and not res.errors:
            res.errors.append("no notice cards parsed (layout change?)")
    except Exception as e:  # noqa: BLE001
        res.errors.append(f"{type(e).__name__}: {e}")
    return res
