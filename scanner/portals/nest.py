"""Tanzania NeST (National e-Procurement System) published tenders.
The public page https://nest.go.tz/tenders/published-tenders (Angular, no
login) loads its list from the public GraphQL query getPublishedEntityViewData
at https://nest.go.tz/gateway/nest-app/graphql. We send the same query the page
sends (pageSize up to 200) and return every currently published tender
(~240), dropping only those invited before ctx.since. NeST has no stable
per-tender public URL (details open in-app), so url is the list page and ref
is the tender number. GST (Geological Survey of Tanzania) is a target buyer.
"""
from ..core import Candidate, PortalInfo, PortalResult, RunContext, parse_date, post

PORTAL = PortalInfo(key="nest", name="Tanzania NeST published tenders", region="Africa",
                    method="Public page's GraphQL list query", min_rows=30,
                    url="https://nest.go.tz/tenders/published-tenders")

API = "https://nest.go.tz/gateway/nest-app/graphql"
Q = """query getPublishedEntityViewData($input: DataRequestInputInput, $withMetaData: Boolean) {
  items: getPublishedEntityViewData(input: $input, withMetaData: $withMetaData) {
    totalPages totalRecords currentPage hasNext
    rows: data { descriptionOfTheProcurement entityId entityNumber entityStatus entitySubCategoryName
      entityType entityUuid financialYearCode id invitationDate lotCount procurementCategoryName
      procuringEntityName submissionOrOpeningDate referenceNumber }
  }
}"""
PAGE = 200


def fetch(ctx: RunContext) -> PortalResult:
    res = PortalResult(portal=PORTAL.key)
    since = ctx.since.isoformat()
    seen = {}
    try:
        page = 1
        while page <= 20:
            v = {"input": {"page": page, "pageSize": PAGE,
                           "fields": [{"fieldName": "invitationDate", "isSortable": True, "orderDirection": "DESC"}],
                           "mustHaveFilters": [{"fieldName": "entityStatus", "operation": "IN",
                                                "inValues": ["PUBLISHED"]}]}}
            r = post(API, json={"operationName": "getPublishedEntityViewData", "variables": v, "query": Q},
                     headers={"Origin": "https://nest.go.tz", "Referer": PORTAL.url}, timeout=ctx.timeout)
            res.queries += 1
            if r.status_code != 200:
                res.errors.append(f"page {page}: HTTP {r.status_code}")
                break
            body = r.json()
            if body.get("errors"):
                res.errors.append(f"GraphQL: {str(body['errors'])[:200]}")
            it = ((body.get("data") or {}).get("items")) or {}
            rows = it.get("rows") or []
            res.rows_seen += len(rows)
            for t in rows:
                pub = parse_date(t.get("invitationDate"))
                if pub and pub < since:
                    continue
                ref = t.get("entityNumber") or t.get("referenceNumber") or t.get("entityUuid") or ""
                seen.setdefault(t.get("entityUuid") or ref, Candidate(
                    portal="nest", ref=ref, title=(t.get("descriptionOfTheProcurement") or "").strip(),
                    url=PORTAL.url, buyer=t.get("procuringEntityName") or "", country="Tanzania",
                    published=pub, deadline=parse_date(t.get("submissionOrOpeningDate")),
                    description=" | ".join(x for x in [t.get("procurementCategoryName"), t.get("entitySubCategoryName"),
                                                       t.get("entityType")] if x),
                    notice_type="tender", language="en",
                    extra={"uuid": t.get("entityUuid"), "lots": t.get("lotCount")}))
            if not it.get("hasNext") or not rows:
                break
            page += 1
    except Exception as e:  # noqa: BLE001
        res.errors.append(f"{type(e).__name__}: {e}")
    res.candidates = list(seen.values())
    return res
