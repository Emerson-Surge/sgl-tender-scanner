"""Poland e-Zamówienia (BZP board). The public board at
ezamowienia.gov.pl/mo-client-board/bzp/list calls a keyless JSON endpoint
/mo-board/api/v1/Board/Search (no login, no WAF). It ignores PageSize (always
10/page) and the window holds ~700 notices/day, so we search server-side:
OrderObject (subject substring, case-insensitive), CpvCode, and the PIG-PIB
buyer name. The official /mo-board/api/v1/notice bulk endpoint also works but
embeds full HTML bodies (~32 kB/notice, ~16 MB per 500), too heavy weekly."""
import time

from ..core import Candidate, PortalInfo, PortalResult, RunContext, get, parse_date

PORTAL = PortalInfo(key="ezamowienia", name="e-Zamówienia BZP (Poland)", region="Europe",
                    method="Board's keyless JSON search (subject/CPV/buyer queries)", min_rows=3,
                    url="https://ezamowienia.gov.pl/mo-client-board/bzp/list")

API = "https://ezamowienia.gov.pl/mo-board/api/v1/Board/Search"
SUBJECT_TERMS = ["geofizy", "aerogeofiz", "magnetometr", "magnetyczn", "grawimetr", "elektromagnetyczn",
                 "spektrometr", "radiometr", "gamma", "lotnicz zdję", "zdjęć lotniczych", "skaning laserow",
                 "LiDAR", "aeromagnet", "kartografi geologiczn", "badań geologicznych"]
CPVS = ["71351710-3", "71353000-7", "71351210-8", "71351100-4", "71355000-1", "71351200-5",
        "71352000-0", "71354000-4", "71354100-5", "71351000-3", "38260000-9"]
BUYERS = ["Państwowy Instytut Geologiczny"]
BUDGET_S = 100
MAX_PAGES = 15


def fetch(ctx: RunContext) -> PortalResult:
    res = PortalResult(portal=PORTAL.key)
    seen = {}
    t0 = time.time()
    queries = ([{"OrderObject": t} for t in SUBJECT_TERMS] + [{"CpvCode": c} for c in CPVS]
               + [{"OrganizationName": b} for b in BUYERS])
    for q in queries:
        page = 1
        while page <= MAX_PAGES:
            if time.time() - t0 > BUDGET_S:
                res.errors.append(f"time budget hit at {q}")
                res.candidates = list(seen.values())
                return res
            try:
                r = get(API, params={"publicationDateFrom": f"{ctx.since.isoformat()}T00:00:00Z",
                                     "SortingColumnName": "PublicationDate", "SortingDirection": "DESC",
                                     "PageNumber": page, "PageSize": 10, **q}, timeout=ctx.timeout)
                res.queries += 1
                if r.status_code != 200:
                    res.errors.append(f"{q} HTTP {r.status_code}: {r.text[:150]}")
                    break
                rows = r.json() or []
            except Exception as e:  # noqa: BLE001
                res.errors.append(f"{q}: {type(e).__name__}: {e}")
                break
            for x in rows:
                key = x.get("objectId") or x.get("noticeNumber")
                if key in seen:
                    continue
                res.rows_seen += 1
                seen[key] = Candidate(
                    portal=PORTAL.key, ref=x.get("noticeNumber") or key, title=(x.get("orderObject") or "").strip(),
                    url=f"https://ezamowienia.gov.pl/mo-client-board/bzp/notice-details/id/{x.get('objectId')}",
                    buyer=x.get("organizationName") or "", country=x.get("organizationCountry") or "PL",
                    published=parse_date(x.get("publicationDate")), deadline=parse_date(x.get("submittingOffersDate")),
                    description=f"CPV {x.get('cpvCode') or ''}; {x.get('orderType') or ''}"[:2000],
                    notice_type=x.get("noticeType") or x.get("noticeTypeTed") or "", language="pl",
                    extra={"cpv": x.get("cpvCode"), "tenderId": x.get("tenderId"), "bzp": x.get("bzpNumber")},
                )
            if len(rows) < 10:
                break
            page += 1
    res.candidates = list(seen.values())
    return res
