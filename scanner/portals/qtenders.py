"""QTenders (Queensland): public tender search, headless render.

The site is a Blazor app (a plain GET returns only the shell), but a plain
headless render of https://qtenders.hpw.qld.gov.au/search?keywords=&statuses=1
&page=N lists all open tenders, 20 per page, newest opened first (tested
13 Nov 2026, 116 open = 6 pages): title + public link (often a VendorPanel
preview), issuer, reference, details, categories, products, regions, opens,
closes. Rows opened before ctx.since are counted but not returned.
"""
import html as _html
import math
import re

from ..core import Candidate, PortalInfo, PortalResult, RunContext, browser, parse_date

PORTAL = PortalInfo(key="qtenders", name="QTenders (Queensland)", region="Asia-Pacific",
                    method="Public search, headless render (all open tenders)", min_rows=40,
                    url="https://qtenders.hpw.qld.gov.au/search?keywords=&statuses=1", uses_browser=True)

SEARCH = "https://qtenders.hpw.qld.gov.au/search?keywords=&statuses=1&page={}"
CARD_SPLIT = "tw:bg-white tw:rounded-lg tw:shadow-md"
PER_PAGE = 20
MAX_PAGES = 12


def _card_text(c):
    t = re.sub(r"<!--!-->", "", c)
    t = re.sub(r"<[^>]+>", "\n", t)
    return re.sub(r"[ \t]*\n\s*", "\n", _html.unescape(t)).strip()


def _between(txt, a, b_list):
    i = txt.find(a)
    if i < 0:
        return ""
    i += len(a)
    while i < len(txt) and txt[i].isspace():
        i += 1
    j = min([k for k in (txt.find(b, i) for b in b_list) if k >= 0] or [len(txt)])
    return txt[i:j].strip()


def _parse(page_html, res, seen):
    n = 0
    for c in page_html.split(CARD_SPLIT)[1:]:
        if "Reference number" not in c:
            continue
        n += 1
        res.rows_seen += 1
        link = re.search(r'<h4[^>]*>\s*<a href="([^"]+)"', c)
        title = re.search(r"<h4[^>]*>.*?<a [^>]*>(.*?)</a>", c, re.S)
        txt = _card_text(c)
        ref = _between(txt, "Reference number:", ["\n"]) or (link[1] if link else "")
        if ref in seen:
            continue
        stops = ["Categories:", "Products/Services:", "Regions:", "\nOpen\n", "Opens:"]
        details = _between(txt, "Details:", stops[0:])
        cats = _between(txt, "Categories:", stops[1:]).replace("\n", "; ")
        prods = _between(txt, "Products/Services:", stops[2:]).replace("\n", "; ")
        regions = _between(txt, "Regions:", stops[3:]).replace("\n", "; ")
        seen[ref] = Candidate(
            portal=PORTAL.key, ref=ref,
            title=re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", "", title[1]))).strip() if title else "",
            url=_html.unescape(link[1]) if link else PORTAL.url,
            buyer=_between(txt, "Issued by:", ["\n"]), country="Australia (QLD)",
            published=parse_date(_between(txt, "Opens:", ["\n"])),
            deadline=parse_date(_between(txt, "Closes:", ["\n"])),
            description=f"{details}\nCategories: {cats}\nProducts/Services: {prods}"[:2000],
            notice_type="tender", extra={"regions": regions},
        )
    return n


def fetch(ctx: RunContext) -> PortalResult:
    res = PortalResult(portal=PORTAL.key)
    since = ctx.since.isoformat()
    seen = {}
    try:
        first = browser([SEARCH.format(1)], wait_ms=2500, html=True)[0]
        res.queries += 1
        if first.get("error") or (first.get("status") or 0) >= 400:
            res.errors.append(f"page 1: {first.get('error') or first.get('status')}")
            return res
        total = re.search(r"(\d+) tenders found", first.get("text", ""))
        if not total:
            res.errors.append("result count not found (layout change?)")
        _parse(first.get("html", ""), res, seen)
        pages = min(math.ceil(int(total[1]) / PER_PAGE), MAX_PAGES) if total else 1
        if pages > 1:
            urls = [SEARCH.format(p) for p in range(2, pages + 1)]
            for u, pg in zip(urls, browser(urls, wait_ms=2500, html=True)):
                res.queries += 1
                if pg.get("error"):
                    res.errors.append(f"{u}: {pg['error'][:200]}")
                    continue
                _parse(pg.get("html", ""), res, seen)
        if not seen:
            res.errors.append("no tender cards parsed (layout change?)")
    except Exception as e:  # noqa: BLE001
        res.errors.append(f"{type(e).__name__}: {e}")
    res.candidates = [c for c in seen.values() if not c.published or c.published >= since]
    return res
