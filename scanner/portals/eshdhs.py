"""Greece KIMDIS / ESHDHS open data (keyless):
POST https://cerpp.eprocurement.gov.gr/khmdhs-opendata/notice?page=N
body {title | cpvItems, dateFrom, dateTo}; 50 rows/page; 404 = no results.

~5,600 notices/week, so we search server-side: title substring stems (case-
insensitive) and CPV codes. cpvItems needs the real check digit (a wrong one
returns 404); the digits below were discovered against the live data on
13 Nov 2026. URL = the public notice PDF (GET /notice/attachment/<ref>)."""
from ..core import Candidate, PortalInfo, PortalResult, RunContext, parse_date, post

PORTAL = PortalInfo(key="eshdhs", name="Greece KIMDIS (ESHDHS)", region="Europe",
                    method="Official open-data API (keyless), title + CPV search", min_rows=1,
                    url="https://cerpp.eprocurement.gov.gr/upgkimdis/unprotected/home.xhtml")

API = "https://cerpp.eprocurement.gov.gr/khmdhs-opendata/notice"
TITLE_TERMS = ["γεωφυσικ", "μαγνητομετρ", "αερομαγνητ", "ηλεκτρομαγνητ", "αερογεωφυσ", "ραδιομετρ",
               "φασματομετρ", "βαρυτομετρ", "βαρυμετρ", "LiDAR", "αεροφωτογραμμετρ", "γεωλογικ χαρτογράφ"]
CPVS = ["71351710-3", "71353000-7", "71351210-8", "71351100-4", "71355000-1", "71351200-5",
        "71352000-0", "71354000-4", "71354100-5", "71351500-8"]


def _run(body, ctx, res, seen):
    page = 0
    while page < 10:
        r = post(f"{API}?page={page}", json=body, headers={"Content-Type": "application/json"},
                 timeout=ctx.timeout)
        res.queries += 1
        if r.status_code == 404:
            return
        if r.status_code != 200:
            res.errors.append(f"{list(body)[0]} HTTP {r.status_code}: {r.text[:150]}")
            return
        d = r.json()
        for x in d.get("content") or []:
            res.rows_seen += 1
            ref = x.get("referenceNumber", "")
            if ref in seen:
                continue
            objs = x.get("objectDetails") or []
            cpvs = [c.get("key") for o in objs for c in (o.get("cpvs") or [])]
            desc = " | ".join(f"{o.get('shortDescription') or ''} [{', '.join((c.get('value') or '') for c in (o.get('cpvs') or []))}]" for o in objs[:20])
            seen[ref] = Candidate(
                portal=PORTAL.key, ref=ref, title=(x.get("title") or "").strip(),
                url=f"{API}/attachment/{ref}",
                buyer=(x.get("organization") or {}).get("value", ""), country="GR",
                published=parse_date(x.get("publishedDate") or x.get("submissionDate") or x.get("signedDate")),
                deadline=parse_date(x.get("finalSubmissionDate")), description=desc[:2000],
                value=f"{x.get('totalCostWithoutVAT')} EUR" if x.get("totalCostWithoutVAT") else "",
                notice_type=(x.get("noticeType") or {}).get("value", ""), language="el",
                extra={"cpv": cpvs, "cancelled": x.get("cancelled")},
            )
        if d.get("last", True):
            return
        page += 1


def fetch(ctx: RunContext) -> PortalResult:
    res = PortalResult(portal=PORTAL.key)
    seen = {}
    win = {"dateFrom": ctx.since.isoformat(), "dateTo": ctx.today.isoformat()}
    bodies = [{"title": t, **win} for t in TITLE_TERMS] + [{"cpvItems": CPVS, **win}]
    for b in bodies:
        try:
            _run(b, ctx, res, seen)
        except Exception as e:  # noqa: BLE001
            res.errors.append(f"{b.get('title') or 'cpv'}: {type(e).__name__}: {e}")
    res.candidates = list(seen.values())
    return res
