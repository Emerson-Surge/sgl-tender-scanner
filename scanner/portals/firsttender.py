"""FirstTender (India aggregator) public keyword and buyer pages, via JSON-LD.

Each public page /bids/<keyword>-tenders.html and /authotirytender/<buyer>.html
embeds one schema.org Event per live tender (tested 13 Nov 2026): url (the
tenders-detail-<FtId>.html page), name (buyer), description (tender work
text), identifier (the buyer's own tender / GeM bid number), startDate
(published), endDate (bid due). A keyword with no hits 302-redirects away; a
page shows at most ~20 rows. Buyer pages only show the newest 10, so they are a
supplement to the keyword pages, not a substitute. ref = FtId.
"""
import json
import re

from ..core import Candidate, PortalInfo, PortalResult, RunContext, get, parse_date

PORTAL = PortalInfo(key="firsttender", name="FirstTender (India)", region="Asia-Pacific",
                    method="Public keyword/buyer pages, schema.org JSON-LD", min_rows=15,
                    url="https://www.firsttender.com/bids/geophysical-tenders.html")

B = "https://www.firsttender.com"
KEYWORDS = [
    "geophysical", "geophysical-survey", "geophysics", "aero-geophysical", "airborne", "airborne-survey",
    "aeromagnetic", "heliborne", "magnetic-survey", "magnetometer", "magnetic-gradiometer",
    "gravity-survey", "gravimeter", "radiometric", "gamma-ray-spectrometer", "electromagnetic-survey",
    "lidar", "lidar-survey", "aerial-survey", "aerial-photography", "mineral-exploration", "exploration",
    "geological-survey",
]
BUYERS = [
    "geological-survey-of-india-755", "atomic-minerals-directorate-for-exploration-and-research-6223",
    "atomic-minerals-department-2654", "mineral-exploration-corporation-limited-2348",
    "national-mineral-development-corporation-limited-9141", "oil-and-natural-gas-corporation-limited-8885",
]
LD = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)


def _events(page):
    for blob in LD.findall(page):
        try:
            d = json.loads(blob)
        except ValueError:
            continue
        for e in d if isinstance(d, list) else [d]:
            if isinstance(e, dict) and e.get("@type") == "Event":
                yield e


def fetch(ctx: RunContext) -> PortalResult:
    res = PortalResult(portal=PORTAL.key)
    since = ctx.since.isoformat()
    seen = {}
    pages = [f"{B}/bids/{k}-tenders.html" for k in KEYWORDS] + [f"{B}/authotirytender/{b}.html" for b in BUYERS]
    ok_pages = 0
    for url in pages:
        try:
            r = get(url, timeout=ctx.timeout, allow_redirects=False)
            res.queries += 1
            if r.status_code in (301, 302):
                continue  # keyword with no live hits
            if r.status_code != 200:
                res.errors.append(f"{url}: HTTP {r.status_code}")
                continue
            ok_pages += 1
            src = url.rsplit("/", 1)[-1].replace(".html", "")
            for e in _events(r.text):
                res.rows_seen += 1
                link = e.get("url", "")
                m = re.search(r"tenders-detail-(\d+)\.html", link)
                ref = m[1] if m else link
                if ref in seen:
                    if src not in seen[ref].extra["pages"]:
                        seen[ref].extra["pages"].append(src)
                    continue
                addr = (e.get("location") or {}).get("address") or {}
                offers = e.get("offers") or {}
                desc = (e.get("description") or "").strip()
                price = str(offers.get("price") or "")
                seen[ref] = Candidate(
                    portal=PORTAL.key, ref=ref, title=desc[:1].upper() + desc[1:300],
                    url=link, buyer=e.get("name", ""), country=addr.get("addressCountry") or "India",
                    published=parse_date(e.get("startDate")), deadline=parse_date(e.get("endDate")),
                    description=desc,
                    value=f"{price} {offers.get('priceCurrency', '')}".strip() if price not in ("", "0") else "",
                    notice_type="tender",
                    extra={"tender_id": e.get("identifier", ""), "region": addr.get("addressRegion", ""),
                           "pages": [src]},
                )
        except Exception as e:  # noqa: BLE001
            res.errors.append(f"{url}: {type(e).__name__}: {e}")
    if ok_pages and not seen:
        res.errors.append("pages loaded but no JSON-LD Event rows parsed (layout change?)")
    res.candidates = [c for c in seen.values() if not c.published or c.published >= since]
    return res
