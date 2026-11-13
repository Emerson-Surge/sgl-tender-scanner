"""Netherlands TenderNed public API (keyless):
GET https://www.tenderned.nl/papi/tenderned-rs-tns/v2/publicaties
    ?publicatieDatumVanaf=YYYY-MM-DD&page=N&size=100
Spring-style paging; size max 100 (500 errors). ~650 publications/week, so we
page the full window."""
import time

from ..core import Candidate, PortalInfo, PortalResult, RunContext, get, parse_date

PORTAL = PortalInfo(key="tenderned", name="TenderNed (Netherlands)", region="Europe",
                    method="Official public API (keyless), full window", min_rows=200,
                    url="https://www.tenderned.nl/aankondigingen/overzicht")

API = "https://www.tenderned.nl/papi/tenderned-rs-tns/v2/publicaties"
BUDGET_S = 100


def fetch(ctx: RunContext) -> PortalResult:
    res = PortalResult(portal=PORTAL.key)
    seen = {}
    t0 = time.time()
    page = 0
    try:
        while page < 200:
            if time.time() - t0 > BUDGET_S:
                res.errors.append(f"time budget hit at page {page}")
                break
            r = get(API, params={"publicatieDatumVanaf": ctx.since.isoformat(), "page": page, "size": 100},
                    headers={"Accept": "application/json"}, timeout=ctx.timeout)
            res.queries += 1
            if r.status_code != 200:
                res.errors.append(f"page {page} HTTP {r.status_code}: {r.text[:200]}")
                break
            d = r.json()
            for x in d.get("content") or []:
                res.rows_seen += 1
                pid = str(x.get("publicatieId", ""))
                seen[pid] = Candidate(
                    portal=PORTAL.key, ref=pid, title=x.get("aanbestedingNaam") or "",
                    url=(x.get("link") or {}).get("href") or f"https://www.tenderned.nl/aankondigingen/overzicht/{pid}",
                    buyer=x.get("opdrachtgeverNaam") or "", country="NL",
                    published=parse_date(x.get("publicatieDatum")),
                    deadline=parse_date(x.get("sluitingsDatum") or x.get("sluitingsDatumMarktconsultatie")),
                    description=(x.get("opdrachtBeschrijving") or "")[:2000],
                    notice_type=(x.get("typePublicatie") or {}).get("omschrijving", ""), language="nl",
                    extra={"kenmerk": x.get("kenmerk"), "code": (x.get("publicatiecode") or {}).get("code")},
                )
            if d.get("last", True):
                break
            page += 1
    except Exception as e:  # noqa: BLE001
        res.errors.append(f"{type(e).__name__}: {e}")
    res.candidates = list(seen.values())
    return res
