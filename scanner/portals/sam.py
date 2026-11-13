"""SAM.gov contract opportunities via the official public Opportunities API v2
(api.sam.gov/opportunities/v2/search). Needs a free api.data.gov / SAM.gov
key in SAM_API_KEY; without it the adapter makes no calls. sam.gov's own
website endpoints are deliberately not used.

Legs (each one call, up to 1,000 rows, posted ctx.since..today):
  * NAICS 541360 Geophysical Surveying and Mapping, 541370 Surveying and
    Mapping (except Geophysical);
  * title keywords.
Keys without a SAM.gov role are limited to ~10 calls/day, so the leg list is
kept short (MAX_CALLS). Award notices (ptype a) get notice_type="award".
Live-tested 13 Nov 2026 with a key sent as the X-Api-Key header.
"""
import os

from ..core import Candidate, PortalInfo, PortalResult, RunContext, get, parse_date

PORTAL = PortalInfo(key="sam", name="SAM.gov (USA)", region="Americas",
                    method="Official Opportunities API v2 (free key in SAM_API_KEY)", min_rows=1,
                    url="https://sam.gov/search/?index=opp")

API = "https://api.sam.gov/opportunities/v2/search"
LEGS = [("ncode", "541360"), ("ncode", "541370"), ("title", "geophysical"), ("title", "airborne"),
        ("title", "aeromagnetic"), ("title", "LiDAR"), ("title", "magnetic survey"), ("title", "gravity")]
MAX_CALLS = 8
AWARD_TYPES = {"a", "award notice"}


def _us(d):
    return d.strftime("%m/%d/%Y")


def fetch(ctx: RunContext) -> PortalResult:
    res = PortalResult(portal=PORTAL.key)
    # The real key is normally injected into the X-Api-Key header by the environment's
    # credential store (network secret for api.sam.gov); SAM_API_KEY overrides it locally.
    key = os.environ.get("SAM_API_KEY", "").strip() or "injected-by-proxy"
    seen = {}
    for field, value in LEGS[:MAX_CALLS]:
        try:
            r = get(API, headers={"X-Api-Key": key}, params={"postedFrom": _us(ctx.since), "postedTo": _us(ctx.today),
                                 field: value, "limit": 1000, "offset": 0}, timeout=max(ctx.timeout, 60))
            res.queries += 1
            if r.status_code == 429:
                res.errors.append(f"{field}={value}: HTTP 429 (daily key quota used)")
                break
            if r.status_code in (401, 403):
                res.errors.append(f"HTTP {r.status_code}: SAM key missing or rejected (store it as a network secret for api.sam.gov)")
                break
            if r.status_code != 200:
                res.errors.append(f"{field}={value}: HTTP {r.status_code}: {r.text[:200]}")
                continue
            data = r.json()
            opps = data.get("opportunitiesData") or []
            if int(data.get("totalRecords") or 0) > len(opps):
                res.notes.append(f"{field}={value}: {data.get('totalRecords')} records, first {len(opps)} read")
            for o in opps:
                res.rows_seen += 1
                nid = o.get("noticeId") or ""
                pop = o.get("placeOfPerformance") or {}
                desc_link = o.get("description") or ""  # the API returns a link to the description, not text
                award = o.get("award") or {}
                ptype = (o.get("type") or "").lower()
                seen.setdefault(nid, Candidate(
                    portal=PORTAL.key, ref=nid, title=o.get("title") or "",
                    url=o.get("uiLink") or f"https://sam.gov/opp/{nid}/view",
                    buyer=o.get("fullParentPathName") or o.get("department") or "",
                    country=((pop.get("country") or {}).get("code") or "USA"),
                    published=parse_date(o.get("postedDate")),
                    deadline=parse_date(o.get("responseDeadLine")),
                    description=" | ".join(s for s in (o.get("classificationCode") and
                                                       f"PSC {o.get('classificationCode')}",
                                                       o.get("naicsCode") and f"NAICS {o.get('naicsCode')}") if s),
                    value=str(award.get("amount") or ""),
                    notice_type="award" if ptype in AWARD_TYPES or award else (ptype or "tender"),
                    language="en",
                    extra={"solicitation": o.get("solicitationNumber", ""), "naics": o.get("naicsCode", ""),
                           "psc": o.get("classificationCode", ""), "set_aside": o.get("typeOfSetAside", ""),
                           "description_api_link": desc_link, "leg": f"{field}={value}",
                           "awardee": (award.get("awardee") or {}).get("name", "")},
                ))
        except Exception as e:  # noqa: BLE001
            res.errors.append(f"{field}={value}: {type(e).__name__}: {e}")
    res.candidates = list(seen.values())
    return res
