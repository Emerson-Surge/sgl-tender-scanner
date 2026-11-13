"""South Africa National Treasury eTenders. The public "open tenders" table on
https://www.etenders.gov.za/Home/opportunities?id=1 is a server-side DataTable
fed by GET /Home/PaginatedTenderOpportunities?status=1 (JSON, no login).
Sorted by publication date desc; we page until rows predate ctx.since.
The portal has no per-tender public page, so url points to the open-tenders
list (search by tender number there); support-document file names are in extra.
Council for Geoscience (CGS) is the key buyer for SGL.
"""
from ..core import Candidate, PortalInfo, PortalResult, RunContext, get, parse_date

PORTAL = PortalInfo(key="etenderza", name="eTenders South Africa", region="Africa",
                    method="Public DataTable JSON (PaginatedTenderOpportunities)", min_rows=100,
                    url="https://www.etenders.gov.za/Home/opportunities?id=1")

BASE = "https://www.etenders.gov.za"
PAGE = 500


def fetch(ctx: RunContext) -> PortalResult:
    res = PortalResult(portal=PORTAL.key)
    since = ctx.since.isoformat()
    out = {}
    try:
        start = 0
        for _ in range(20):
            r = get(f"{BASE}/Home/PaginatedTenderOpportunities",
                    params={"draw": 1, "start": start, "length": PAGE, "status": 1,
                            "order[0][column]": 2, "order[0][dir]": "desc", "search[value]": ""},
                    headers={"X-Requested-With": "XMLHttpRequest"}, timeout=max(ctx.timeout, 90))
            res.queries += 1
            if r.status_code != 200:
                res.errors.append(f"HTTP {r.status_code}: {r.text[:200]}")
                break
            data = r.json().get("data") or []
            old = False
            for t in data:
                res.rows_seen += 1
                pub = parse_date(t.get("date_Published"))
                if pub and pub < since:
                    old = True
                    continue
                docs = [d.get("fileName", "") for d in (t.get("supportDocument") or [])]
                ref = t.get("tender_No") or str(t.get("id", ""))
                desc = " | ".join(x for x in [t.get("category"), t.get("type"), t.get("province"),
                                              (t.get("conditions") or "")[:800]] if x)
                c = Candidate(
                    portal="etenderza", ref=ref.strip(), title=(t.get("description") or "").strip(),
                    url=f"{BASE}/Home/opportunities?id=1",
                    buyer=t.get("department") or t.get("organ_of_State") or "", country="South Africa",
                    published=pub, deadline=parse_date(t.get("closing_Date")), description=desc,
                    notice_type="tender", language="en",
                    extra={"etenders_id": t.get("id"), "category": t.get("category"), "documents": docs[:5]},
                )
                out.setdefault(f"{c.ref}|{t.get('id')}", c)
            if old or len(data) < PAGE:
                break
            start += PAGE
    except Exception as e:  # noqa: BLE001
        res.errors.append(f"{type(e).__name__}: {e}")
    res.candidates = list(out.values())
    return res
