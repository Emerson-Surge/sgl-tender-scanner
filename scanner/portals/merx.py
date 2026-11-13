"""MERX (Canadian public tenders) via its public open-solicitations search
page (merx.com/public/solicitations/open?keywords=...; plain HTML, no login;
tested 13 Nov 2026).

MERX has ~3,400 open notices, so the adapter uses MERX's own keyword search
(relevance-ranked, fairly fuzzy) with geophysics terms, up to MAX_PAGES
result pages each, and keeps rows published on/after ctx.since. Many federal
MERX notices also appear in the canadabuys adapter.
"""
import html as _html
import re

from ..core import Candidate, PortalInfo, PortalResult, RunContext, get

PORTAL = PortalInfo(key="merx", name="MERX (Canada)", region="Americas",
                    method="Public search page, keyword queries (plain HTML)", min_rows=5,
                    url="https://www.merx.com/public/solicitations/open")

SEARCH = "https://www.merx.com/public/solicitations/open"
KEYWORDS = ["geophysical", "airborne survey", "aeromagnetic", "magnetic survey", "gravity survey",
            "radiometric", "electromagnetic survey", "LiDAR", "géophysique", "levé aéroporté"]
MAX_PAGES = 3
ROW = re.compile(r'<tr\s+data-index="\d+"[^>]*>(.*?)</tr>', re.S)


def _f(cls, s):
    m = re.search(rf'<span class="{cls}[^"]*">(.*?)</span>', s, re.S)
    return re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", m[1]))).strip() if m else ""


def _date(cls, s):
    m = re.search(rf'<span class="{cls}[^"]*">.*?<span class="dateValue">(\d{{4}})/(\d{{2}})/(\d{{2}})', s, re.S)
    return f"{m[1]}-{m[2]}-{m[3]}" if m else ""


def fetch(ctx: RunContext) -> PortalResult:
    res = PortalResult(portal=PORTAL.key)
    seen = {}
    since = ctx.since.isoformat()
    for kw in KEYWORDS:
        for page in range(1, MAX_PAGES + 1):
            try:
                params = {"keywords": kw}
                if page > 1:
                    params["pageNumber"] = page
                r = get(SEARCH, params=params, timeout=ctx.timeout)
                res.queries += 1
                if r.status_code != 200:
                    res.errors.append(f"{kw} p{page}: HTTP {r.status_code}")
                    break
                rows = ROW.findall(r.text)
                if not rows and page == 1 and "results" not in r.text:
                    res.errors.append(f"{kw}: no result table (layout change?)")
                for row in rows:
                    res.rows_seen += 1
                    m = re.search(r'href="(/[^"]*solicitations/[^"]+)"', row)
                    if not m:
                        continue
                    href = _html.unescape(m[1]).replace("?origin=0", "")
                    ref = _f("accessibility-hidden", row) or href.rsplit("/", 1)[-1]
                    pub = _date("publicationDate", row)
                    if pub and pub < since:
                        continue
                    c = seen.get(ref)
                    if c:
                        c.extra["keywords"].append(kw)
                        continue
                    seen[ref] = Candidate(
                        portal=PORTAL.key, ref=ref, title=_f("rowTitle", row),
                        url="https://www.merx.com" + href, buyer=_f("buyer-name", row),
                        country="Canada", published=pub, deadline=_date("closingDate", row),
                        notice_type="tender", language="en",
                        extra={"location": _f("location", row), "keywords": [kw]},
                    )
                if f"pageNumber={page + 1}" not in r.text:
                    break
            except Exception as e:  # noqa: BLE001
                res.errors.append(f"{kw} p{page}: {type(e).__name__}: {e}")
                break
    res.candidates = list(seen.values())
    return res
