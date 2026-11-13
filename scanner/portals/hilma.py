"""Finland Hilma (hankintailmoitukset.fi). The documented API (api.hankintailmoitukset.fi)
needs a subscription key; the public website's search page calls a keyless
Azure Cognitive Search proxy at www.hankintailmoitukset.fi/search/eformnotices
(OData params: search, $filter, $top, $skip, $orderby, $count). We page every
notice published since ctx.since (~550/week). Plans (isPlan) are included."""
from ..core import Candidate, PortalInfo, PortalResult, RunContext, get, parse_date

PORTAL = PortalInfo(key="hilma", name="Hilma (Finland)", region="Europe",
                    method="Website's keyless search proxy (Azure Search OData), full window",
                    min_rows=150, url="https://www.hankintailmoitukset.fi/fi/search")

API = "https://www.hankintailmoitukset.fi/search/eformnotices"
WEB = "https://www.hankintailmoitukset.fi/fi"
PAGE = 500


def _first(x, *keys):
    for k in keys:
        if x.get(k):
            return x[k]
    return ""


def _url(x):
    if x.get("planId") and x.get("isPlan"):
        return f"{WEB}/public/plan/{x['planId']}"
    if x.get("procedureId"):
        return f"{WEB}/public/procedure/{x['procedureId']}/enotice/{x['noticeId']}"
    if x.get("oldProcurementProjectId"):
        return f"{WEB}/public/procurement/{x['oldProcurementProjectId']}/notice/{x['noticeId']}/overview"
    return f"{WEB}/search?q={x.get('noticeNumber', '')}"


def fetch(ctx: RunContext) -> PortalResult:
    res = PortalResult(portal=PORTAL.key)
    seen = {}
    skip = 0
    try:
        while skip < 20000:
            r = get(API, params={"search": "*", "queryType": "full", "$top": PAGE, "$skip": skip,
                                 "$orderby": "datePublished desc", "$count": "true",
                                 "$filter": f"datePublished ge {ctx.since.isoformat()}T00:00:00Z"},
                    timeout=ctx.timeout)
            res.queries += 1
            if r.status_code != 200:
                res.errors.append(f"HTTP {r.status_code}: {r.text[:200]}")
                break
            d = r.json()
            rows = d.get("value") or []
            for x in rows:
                res.rows_seen += 1
                nid = x.get("noticeNumber") or str(x.get("noticeId", ""))
                desc = _first(x, "descriptionFi", "descriptionEn", "descriptionSv", "descriptionOther")
                seen[nid] = Candidate(
                    portal=PORTAL.key, ref=nid,
                    title=_first(x, "titleFi", "titleEn", "titleSv", "titleOther"),
                    url=_url(x),
                    buyer=_first(x, "organisationNameFi", "organisationNameEn", "organisationNameSv",
                                 "organisationNameOther"),
                    country="FI", published=parse_date(x.get("datePublished")),
                    deadline=parse_date(x.get("deadline") or x.get("expirationDate")),
                    description=(desc or "")[:2000],
                    value=f"{x.get('estimatedValue')} {x.get('currency') or 'EUR'}" if x.get("estimatedValue") else "",
                    notice_type=x.get("mainType") or "", language="fi",
                    extra={"cpv": (x.get("cpvCodes") or "").split(","), "ted": x.get("tedPublicationId")},
                )
            total = d.get("@odata.count", 0)
            skip += PAGE
            if len(rows) < PAGE or skip >= total:
                break
    except Exception as e:  # noqa: BLE001
        res.errors.append(f"{type(e).__name__}: {e}")
    res.candidates = list(seen.values())
    return res
