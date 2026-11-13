"""Tender Impulse public keyword search + France country index (plain requests).

The public search box POSTs keyword=<term>&options=tenders to /global-tenders
and returns the matching *live* tenders as server-rendered rows (tested 13 Nov
2026): id, title, country, deadline. Narrow geophysics keywords return a
handful of rows each; a broad term returns the newest 25 ("more available").
Rows carry no publication date (live = deadline not yet passed), so ctx.since
cannot be applied server-side; the state file de-duplicates week to week.

The overseas-territory index pages (/all-tenders-from-country/get-guadeloupe-
tenders etc.) show only yearly archive counts, no current rows, so the
territories are covered by searching their names instead; /france-tenders
gives the newest 25 French rows as a page-health check.
"""
import html as _html
import re

from ..core import Candidate, PortalInfo, PortalResult, RunContext, get, parse_date, post

PORTAL = PortalInfo(key="tenderimpulse", name="Tender Impulse", region="Global",
                    method="Public keyword search (POST form) + country index page", min_rows=10,
                    url="https://tenderimpulse.com/global-tenders")

B = "https://tenderimpulse.com"
KEYWORDS = [
    "aeromagnetic", "airborne geophysical", "airborne geophysics", "magnetometry", "magnetism",
    "gamma spectrometry", "gamma-spectrometry", "radiometric survey", "airborne gravity",
    "gravimetric", "airborne electromagnetic", "electromagnetic survey", "airborne LiDAR",
    "aerial survey", "helicopter-borne", "heliborne", "geophysical survey", "geophysical",
    "géophysique", "aéroporté", "magnétisme", "heliporte",
]
TERRITORIES = ["Guadeloupe", "Martinique", "Guyane", "French Guiana", "Réunion", "Nouvelle-Calédonie",
               "New Caledonia"]

ROW = re.compile(r'<a class="tl-row" href="([^"]+)"[^>]*>(.*?)</a>', re.S)


def _txt(s):
    return _html.unescape(re.sub(r"<[^>]+>", " ", s or "")).strip()


def _parse(page, res, seen, query):
    n = 0
    for href, body in ROW.findall(page):
        n += 1
        res.rows_seen += 1
        rid = re.search(r'<span class="tl-id">(\d+)</span>', body)
        ref = rid[1] if rid else href.rsplit("-", 1)[-1]
        if ref in seen:
            seen[ref].extra["queries"].append(query)
            continue
        title = re.search(r'<span class="tl-title">(.*?)</span>', body, re.S)
        auth = re.search(r'<span class="tl-auth">(.*?)</span></span>', body, re.S)
        dl = re.search(r'<span class="k">Deadline</span><span class="v">(.*?)</span>', body, re.S)
        country = re.sub(r"^\s*Country:\s*", "", re.sub(r"\s+", " ", _txt(auth[1]))) if auth else ""
        seen[ref] = Candidate(
            portal=PORTAL.key, ref=ref, title=re.sub(r"\s+", " ", _txt(title[1] if title else "")),
            url=B + href if href.startswith("/") else href, country=country,
            deadline=parse_date(_txt(dl[1]) if dl else ""), notice_type="tender",
            extra={"queries": [query]},
        )
    return n


def fetch(ctx: RunContext) -> PortalResult:
    res = PortalResult(portal=PORTAL.key)
    seen = {}
    capped = []
    for kw in KEYWORDS + TERRITORIES:
        try:
            r = post(f"{B}/global-tenders", data={"keyword": kw, "options": "tenders"}, timeout=ctx.timeout)
            res.queries += 1
            if r.status_code != 200:
                res.errors.append(f"search '{kw}': HTTP {r.status_code}")
                continue
            _parse(r.text, res, seen, kw)
            if 'data-hasmore="1"' in r.text:
                capped.append(kw)
        except Exception as e:  # noqa: BLE001
            res.errors.append(f"search '{kw}': {type(e).__name__}: {e}")
    try:
        r = get(f"{B}/france-tenders", timeout=ctx.timeout)
        res.queries += 1
        if r.status_code != 200:
            res.errors.append(f"france-tenders: HTTP {r.status_code}")
        elif _parse(r.text, res, seen, "country:france") == 0:
            res.errors.append("france-tenders: no rows parsed (layout change?)")
    except Exception as e:  # noqa: BLE001
        res.errors.append(f"france-tenders: {type(e).__name__}: {e}")
    if capped:
        res.notes.append("first page only (more available) for: " + ", ".join(capped))
    res.candidates = list(seen.values())
    return res
