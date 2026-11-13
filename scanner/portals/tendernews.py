"""TenderNews.com public keyword listing pages (plain requests).

The category URLs first suggested (/geological-survey.html,
/airborne-equipment.html) are soft-404 pages; the live public keyword pages are
/tenders/latest-tender/<slug>.html (tested 13 Nov 2026). Each shows the newest
rows (~20-60) as a table: ref, published, closing date, country[/state], value,
"Tender For <title>". The site's own search is loose (any word), so broad slugs
pull unrelated rows; the matcher sorts that out. Detail pages need a login and
are not opened; url points at the public tenderdetail.aspx?ref= link.
"""
import html as _html
import re

from ..core import Candidate, PortalInfo, PortalResult, RunContext, get, parse_date

PORTAL = PortalInfo(key="tendernews", name="TenderNews (India/global)", region="Asia-Pacific",
                    method="Public keyword listing pages", min_rows=20,
                    url="https://www.tendernews.com/tenders/latest-tender/geological-survey.html")

B = "https://www.tendernews.com/tenders/latest-tender/"
SLUGS = [
    "geological-survey", "airborne-equipment", "geophysical", "geophysical-survey", "aero-geophysical",
    "aeromagnetic", "airborne-survey", "heliborne", "magnetometer", "gravimeter", "magnetic-survey",
    "gravity-survey", "radiometric", "gamma-ray-spectrometer", "electromagnetic-survey", "lidar",
    "aerial-survey", "mineral-exploration", "gradiometer", "geophysical-surveys",
]
ROW = re.compile(
    r'<tr>\s*<td class="hide">(\d+)</td>\s*<td>([^<]*)</td>\s*<td>([^<]*)</td>\s*<td>([^<]*)</td>\s*'
    r'<td class="hide">([^<]*)</td>\s*<td>(.*?)<br\s*/?>\s*<a[^>]*href=\'([^\']+)\'', re.S)


def fetch(ctx: RunContext) -> PortalResult:
    res = PortalResult(portal=PORTAL.key)
    since = ctx.since.isoformat()
    seen = {}
    for slug in SLUGS:
        url = B + slug + ".html"
        try:
            r = get(url, timeout=ctx.timeout)
            res.queries += 1
            if r.status_code != 200:
                res.errors.append(f"{slug}: HTTP {r.status_code}")
                continue
            if "Page Not Found" in r.text[:20000] and "View Tender Detail" not in r.text:
                res.notes.append(f"{slug}: no page")
                continue
            for ref, pub, dl, country, value, title, link in ROW.findall(r.text):
                res.rows_seen += 1
                if ref in seen:
                    if slug not in seen[ref].extra["slugs"]:
                        seen[ref].extra["slugs"].append(slug)
                    continue
                title = re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", title))).strip()
                title = re.sub(r"^Tender For\s+", "", title)
                value = value.strip()
                seen[ref] = Candidate(
                    portal=PORTAL.key, ref=ref, title=title, url=_html.unescape(link),
                    country=_html.unescape(country).strip(), published=parse_date(pub),
                    deadline=parse_date(dl), value="" if value.startswith("Refer") else value,
                    notice_type="tender", extra={"slugs": [slug]},
                )
        except Exception as e:  # noqa: BLE001
            res.errors.append(f"{slug}: {type(e).__name__}: {e}")
    if res.queries and not seen and not res.errors:
        res.errors.append("no rows parsed on any keyword page (layout change?)")
    res.candidates = [c for c in seen.values() if not c.published or c.published >= since]
    return res
