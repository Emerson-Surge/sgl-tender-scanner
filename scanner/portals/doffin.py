"""Norway Doffin. The documented public API (api.doffin.no/public/v2) needs a
subscription key (401). The doffin.no website itself is a plain SPA that
calls a keyless JSON search endpoint (api.doffin.no/webclient/api/v2/
search-api/search, referenced in the site's JS bundle; no WAF/captcha), which
we use read-only.

The endpoint returns at most 1,000 accessible hits per query, so the window is
split into 7-day chunks (~400-500 notices/week), page size 500. A keyword leg
(geofysisk etc.) runs too, in case chunking ever overflows."""
import datetime as dt

from ..core import Candidate, PortalInfo, PortalResult, RunContext, parse_date, post

PORTAL = PortalInfo(key="doffin", name="Doffin (Norway)", region="Europe",
                    method="Website's keyless JSON search API, 7-day chunks", min_rows=150,
                    url="https://www.doffin.no/search")

API = "https://api.doffin.no/webclient/api/v2/search-api/search"
KEYWORDS = ["geofysisk", "geofysikk", "flymåling", "helikoptermåling", "aeromagnetisk",
            "elektromagnetisk", "magnetometri", "gammaspektrometri", "airborne", "geophysical"]


def _query(search, frm, to, ctx, res, seen):
    page = 1
    while page <= 4:
        body = {"numHitsPerPage": 500, "page": page, "searchString": search,
                "sortBy": "PUBLICATION_DATE_DESC",
                "facets": {"publicationDate": {"from": frm, "to": to}}}
        r = post(API, json=body, timeout=ctx.timeout)
        res.queries += 1
        if r.status_code != 200:
            res.errors.append(f"'{search}' {frm} HTTP {r.status_code}: {r.text[:150]}")
            return
        d = r.json()
        hits = d.get("hits") or []
        if d.get("numHitsTotal", 0) > d.get("numHitsAccessible", 0) and page == 1:
            res.notes.append(f"'{search}' {frm}..{to}: {d['numHitsTotal']} hits, only {d['numHitsAccessible']} accessible")
        for h in hits:
            hid = h.get("id", "")
            if hid not in seen:
                res.rows_seen += 1
            ev = h.get("estimatedValue") or {}
            seen[hid] = Candidate(
                portal=PORTAL.key, ref=hid, title=h.get("heading") or "",
                url=f"https://www.doffin.no/notices/{hid}",
                buyer=", ".join(b.get("name", "") for b in h.get("buyer") or []), country="NO",
                published=parse_date(h.get("publicationDate") or h.get("issueDate")),
                deadline=parse_date(h.get("deadline")), description=(h.get("description") or "")[:2000],
                value=f"{ev.get('amount')} {ev.get('currencyCode')}" if ev.get("amount") else "",
                notice_type=h.get("type") or "", language="no",
                extra={"status": h.get("status"), "place": h.get("placeOfPerformance")},
            )
        if len(hits) < 500 or page * 500 >= d.get("numHitsAccessible", 0):
            return
        page += 1


def fetch(ctx: RunContext) -> PortalResult:
    res = PortalResult(portal=PORTAL.key)
    seen = {}
    start = ctx.since
    while start <= ctx.today:
        end = min(start + dt.timedelta(days=6), ctx.today)
        try:
            _query("", start.isoformat(), end.isoformat(), ctx, res, seen)
        except Exception as e:  # noqa: BLE001
            res.errors.append(f"chunk {start}: {type(e).__name__}: {e}")
        start = end + dt.timedelta(days=1)
    for kw in KEYWORDS:
        try:
            _query(kw, ctx.since.isoformat(), None, ctx, res, seen)
        except Exception as e:  # noqa: BLE001
            res.errors.append(f"'{kw}': {type(e).__name__}: {e}")
    res.candidates = list(seen.values())
    return res
