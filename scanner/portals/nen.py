"""Czech Republic NEN (nen.nipez.cz). The public procurement list is a JS app
whose data calls (/api/datarows) carry a client-side signature (TescoSW-Crypto)
and return 400 when replayed outside the page, so we do NOT call them. Instead
we headless-render the public quick-search URLs
  https://nen.nipez.cz/verejne-zakazky/p:vz:query=<term>
(the page loads normally) and parse the first result page (50 rows, newest
first). Full-text search also matches buyer names, so "Česká geologická
služba" is one of the queries. The list has no publication date: we keep rows
whose tender deadline is on/after ctx.since or blank (rows_seen counts all)."""
import re
from urllib.parse import quote

from ..core import Candidate, PortalInfo, PortalResult, RunContext, browser

PORTAL = PortalInfo(key="nen", name="NEN (Czech Republic)", region="Europe",
                    method="Headless render of public quick-search pages", min_rows=20,
                    url="https://nen.nipez.cz/verejne-zakazky", uses_browser=True)

# Queries with no hits cost ~25 s each (the results-table wait times out), so
# keep this list short. "geofyzik" also matches geofyzikální etc.
QUERIES = ["geofyzik", "letecké měření", "magnetometr", "gama spektrometr", "radiometr",
           "Česká geologická služba", "LiDAR"]
LINE = re.compile(r"^Detail\t(N\d{3}/\d{2}/[A-Z]\d+)\t(.*?)\t(.*?)\t(.*?)\t(.*)$", re.M)


def _us_date(s):
    m = re.search(r"(\d{2})/(\d{2})/(\d{4})", s or "")
    if m:
        return f"{m[3]}-{m[1]}-{m[2]}"
    m = re.search(r"(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})", s or "")
    return f"{m[3]}-{int(m[2]):02d}-{int(m[1]):02d}" if m else ""


def fetch(ctx: RunContext) -> PortalResult:
    res = PortalResult(portal=PORTAL.key)
    seen = {}
    urls = [f"https://nen.nipez.cz/verejne-zakazky/p:vz:query={quote(q)}" for q in QUERIES]
    try:
        pages = browser(urls, wait_ms=2000, wait_for="td[data-title]", timeout_ms=45000)
    except Exception as e:  # noqa: BLE001
        res.errors.append(f"browser: {type(e).__name__}: {e}")
        return res
    since = ctx.since.isoformat()
    for q, p in zip(QUERIES, pages):
        res.queries += 1
        if p.get("error"):
            res.errors.append(f"'{q}': {p['error'][:200]}")
            continue
        text = p.get("text") or ""
        rows = LINE.findall(text)
        if not rows:
            if "No records" not in text and "Žádné záznamy" not in text and "nejsou" not in text:
                res.errors.append(f"'{q}': results table not rendered (status {p.get('status')})")
            continue
        for num, title, status, buyer, deadline in rows:
            res.rows_seen += 1
            dl = _us_date(deadline)
            if dl and dl < since:
                continue
            if not dl and int(num[5:7]) < ctx.since.year % 100:  # N006/YY/...: drop old undated
                continue
            slug = num.replace("/", "-")
            seen[num] = Candidate(
                portal=PORTAL.key, ref=num, title=title.strip(),
                url=f"https://nen.nipez.cz/verejne-zakazky/detail-zakazky/{slug}",
                buyer=buyer.strip(), country="CZ", deadline=dl, notice_type=status.strip(),
                language="cs", extra={"query": q},
            )
    res.candidates = list(seen.values())
    return res
