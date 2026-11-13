"""Saudi Arabia Etimad public tender search (visitor view, no login):
https://tenders.etimad.sa/Tender/AllTendersForVisitor loads cards from
GET /Tender/AllSupplierTendersForVisitorAsync (JSON). PageSize is capped at 24
server-side; PublishDateId: 2=last 2 days, 3=last week, 4=last month, 1=any.

Leg 1: crawl everything in the smallest PublishDateId window covering
ctx.since, newest first, within a time budget (a weekly run is ~600 tenders /
~25 pages, which fits). Leg 2 (only if leg 1 hit the budget): Arabic/English
keyword searches (MultipleSearch) so SGS / Ma'aden geoscience work still shows.
Titles are Arabic; the matcher has Arabic geophysics terms.
"""
import time
from urllib.parse import quote

from ..core import Candidate, PortalInfo, PortalResult, RunContext, get, parse_date

PORTAL = PortalInfo(key="etimad", name="Etimad (Saudi Arabia)", region="Middle East",
                    method="Public visitor search JSON (AllSupplierTendersForVisitorAsync)", min_rows=100,
                    url="https://tenders.etimad.sa/Tender/AllTendersForVisitor")

BASE = "https://tenders.etimad.sa"
API = BASE + "/Tender/AllSupplierTendersForVisitorAsync"
BUDGET_S = 95
KW_BUDGET_S = 15
PACE_S = 2.0  # site returns 429 after ~20 rapid requests
TERMS = ["جيوفيزيائي", "جيوفيزيائية", "المسح الجيوفيزيائي", "مغناطيسي", "مغناطيسية", "الجاذبية", "إشعاعي",
         "المسح الجوي", "مسح جوي", "جيولوجي", "جيولوجية", "الخرائط الجيولوجية", "ليدار", "هيئة المساحة الجيولوجية",
         "geophysical", "airborne", "aeromagnetic", "LiDAR"]


def _cand(t):
    sid = t.get("tenderIdString") or ""
    path = "/Tender/DetailsTenderAnnouncement" if t.get("tenderTypeId") == 15 else "/Tender/DetailsForVisitor"
    url = t.get("ugrpRfxUrl") if t.get("isUGRP") and t.get("ugrpRfxUrl") else f"{BASE}{path}?STenderId={quote(sid)}"
    return Candidate(
        portal="etimad", ref=str(t.get("referenceNumber") or t.get("tenderId") or ""),
        title=(t.get("tenderName") or "").strip(), url=url,
        buyer=" / ".join(x for x in [t.get("agencyName"), t.get("branchName")] if x), country="Saudi Arabia",
        published=parse_date(t.get("submitionDate")), deadline=parse_date(t.get("lastOfferPresentationDate")),
        description=" | ".join(x for x in [t.get("tenderActivityName"), t.get("tenderTypeName")] if x),
        notice_type="tender", language="ar",
        extra={"tenderId": t.get("tenderId"), "activity": t.get("tenderActivityName")},
    )


def fetch(ctx: RunContext) -> PortalResult:
    res = PortalResult(portal=PORTAL.key)
    since = ctx.since.isoformat()
    days = (ctx.today - ctx.since).days
    pid = 2 if days <= 2 else 3 if days <= 7 else 4 if days <= 30 else 1
    hdr = {"X-Requested-With": "XMLHttpRequest", "Referer": PORTAL.url}
    seen = {}
    t0 = time.time()
    state = {"stop": False}

    def run(extra, max_pages, budget=None):
        """Return True if this query was read to its end."""
        for page in range(1, max_pages + 1):
            if state["stop"] or time.time() - t0 > (budget or BUDGET_S):
                return False
            if res.queries:
                time.sleep(PACE_S)
            try:
                r = get(API, params=dict(PageSize=24, PageNumber=page, PublishDateId=pid, sort="SubmitionDate",
                                         sortDirection="DESC", **extra), headers=hdr, timeout=ctx.timeout, retries=1)
            except Exception as e:  # noqa: BLE001
                res.errors.append(f"{extra} p{page}: {type(e).__name__} (site refused; stopping)")
                state["stop"] = True
                return False
            res.queries += 1
            if r.status_code != 200:
                res.errors.append(f"{extra} p{page}: HTTP {r.status_code} (stopping; rate limit is respected)")
                state["stop"] = True
                return False
            data = r.json().get("data") or []
            res.rows_seen += len(data)
            old = False
            for t in data:
                c = _cand(t)
                if c.published and c.published < since:
                    old = True
                    continue
                seen.setdefault(c.ref or c.url, c)
            if len(data) < 24 or old:
                return True
        return False

    try:
        if not run({}, 400) and not state["stop"]:
            res.notes.append(f"full crawl hit {BUDGET_S}s budget after {len(seen)} tenders; adding keyword legs")
            for term in TERMS:
                if state["stop"] or time.time() - t0 > BUDGET_S + KW_BUDGET_S:
                    res.notes.append("keyword legs truncated by time budget")
                    break
                run({"MultipleSearch": term, "IsSearch": "true"}, 1, budget=BUDGET_S + KW_BUDGET_S)
    except Exception as e:  # noqa: BLE001
        res.errors.append(f"{type(e).__name__}: {e}")
    res.candidates = list(seen.values())
    return res
