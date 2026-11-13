"""UK Find a Tender (FTS) via the public OCDS release-package API (keyless).

Notes (tested 13 Nov 2026):
  * The `stages=tender` filter is unreliable: on 12 Nov it returned 9 of the
    99 tender/tenderUpdate releases. So we page the unfiltered feed by
    updatedFrom/updatedTo (cursor in links.next, ~430 releases/day) and keep
    tender / tenderUpdate / planning releases client-side.
  * Award/contract releases are counted in rows_seen but not returned as
    candidates (they are results of procurements already closed).
"""
import time

from ..core import Candidate, PortalInfo, PortalResult, RunContext, get, parse_date

PORTAL = PortalInfo(key="fts", name="UK Find a Tender", region="Europe",
                    method="Official OCDS API (keyless), cursor pagination", min_rows=200,
                    url="https://www.find-tender.service.gov.uk/Search")

API = "https://www.find-tender.service.gov.uk/api/1.0/ocdsReleasePackages"
KEEP = {"tender", "tenderUpdate", "tenderAmendment", "planning", "planningUpdate"}
# FTS rate limit (measured 13 Nov 2026): ~7 requests in a 2 s-spaced burst, or
# ~14 at 5 s spacing, then HTTP 429 with Retry-After: 120. So ~10 req/min.
# A week is ~30 pages => ~3.5 min; this adapter is deliberately allowed to
# exceed the usual 2-minute guideline. Pages come newest-first, so if the
# budget runs out it is the oldest part of the window that is skipped.
PAUSE_S = 7.5
BUDGET_S = float(__import__("os").environ.get("FTS_BUDGET_S", "580"))


def paced_get(url, ctx, res, pause=PAUSE_S):
    """GET with pacing and one Retry-After back-off on 429."""
    time.sleep(pause)
    r = get(url, timeout=ctx.timeout, retries=1)
    if r.status_code == 429:
        wait = min(int(r.headers.get("Retry-After") or 120), 125)
        res.notes.append(f"HTTP 429 rate limit; backing off {wait}s once")
        time.sleep(wait)
        r = get(url, timeout=ctx.timeout, retries=1)
    return r


def release_to_candidate(x, portal, url):
    t = x.get("tender") or {}
    tags = x.get("tag") or []
    buyer = (x.get("buyer") or {}).get("name", "")
    country = ""
    for p in x.get("parties") or []:
        if "buyer" in (p.get("roles") or []):
            country = (p.get("address") or {}).get("countryName", "") or (p.get("address") or {}).get("country", "")
            break
    cpvs = []
    cl = t.get("classification") or {}
    if cl.get("id"):
        cpvs.append(cl["id"])
    for it in t.get("items") or []:
        for c in [it.get("classification") or {}] + (it.get("additionalClassifications") or []):
            if c.get("id") and c["id"] not in cpvs:
                cpvs.append(c["id"])
    desc = t.get("description") or x.get("description") or ""
    lots = t.get("lots") or []
    if lots:
        desc += " " + " ".join(f"{l.get('title', '')} {l.get('description', '')}" for l in lots[:10])
    val = t.get("value") or {}
    return Candidate(
        portal=portal, ref=x.get("id", ""), title=t.get("title", "") or "", url=url,
        buyer=buyer, country=country or "United Kingdom", published=parse_date(x.get("date")),
        deadline=parse_date((t.get("tenderPeriod") or {}).get("endDate")),
        description=desc[:2000], value=f"{val.get('amount')} {val.get('currency')}" if val.get("amount") else "",
        notice_type=",".join(tags), language=x.get("language", ""),
        extra={"cpv": cpvs, "ocid": x.get("ocid")},
    )


def fetch(ctx: RunContext) -> PortalResult:
    res = PortalResult(portal=PORTAL.key)
    t0 = time.time()
    seen = {}
    url = f"{API}?updatedFrom={ctx.since.isoformat()}T00:00:00&limit=100"
    try:
        while url:
            if time.time() - t0 > BUDGET_S:
                res.errors.append(f"time budget hit after {res.queries} pages; older releases skipped")
                break
            r = paced_get(url, ctx, res)
            res.queries += 1
            if r.status_code != 200:
                res.errors.append(f"HTTP {r.status_code}: {r.text[:200]}")
                break
            d = r.json()
            for x in d.get("releases") or []:
                res.rows_seen += 1
                if not KEEP.intersection(x.get("tag") or []):
                    continue
                nid = x.get("id", "")
                c = release_to_candidate(x, PORTAL.key, f"https://www.find-tender.service.gov.uk/Notice/{nid}")
                key = x.get("ocid") or nid
                if key not in seen or c.published > seen[key].published:
                    seen[key] = c
            url = (d.get("links") or {}).get("next")
    except Exception as e:  # noqa: BLE001
        res.errors.append(f"{type(e).__name__}: {e}")
    res.candidates = list(seen.values())
    res.notes.append(f"{len(res.candidates)} tender/planning notices kept of {res.rows_seen} releases (awards dropped)")
    return res
