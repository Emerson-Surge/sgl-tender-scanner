"""Denmark udbud.dk. The public search page (udbud.dk/soeg) posts to a keyless
JSON endpoint /soegning/public/soegeresultat (no login, no WAF).
Leg 1: page ALL active notices of every form type (~2,400) at 100/page. The
form-type filter is left empty on purpose: the Miljøstyrelsen airborne
geophysics notice (30 Oct 2026) is a voluntary ex-ante transparency /
direct-award pre-announcement ("dir-awa-pre"), which the site's default
"current tenders" types exclude.
Leg 2: free-text (`fritekstQuery`) search for geophysics terms without the
status filter, keeping hits published since ctx.since.

ctx.since is deliberately not applied: the set is "currently open", which is
what matters for bidding, and a notice published before the window but still
open (e.g. the Miljøstyrelsen airborne tender closing 29 Nov 2026) must not be
missed. The runner's state handles repeats."""
from ..core import Candidate, PortalInfo, PortalResult, RunContext, parse_date, post

PORTAL = PortalInfo(key="udbud", name="udbud.dk (Denmark)", region="Europe",
                    method="Website's keyless JSON search endpoint, all active notices", min_rows=300,
                    url="https://udbud.dk/soeg")

API = "https://udbud.dk/soegning/public/soegeresultat"
KEYWORDS = ["geofysisk", "geofysik", "luftbåren", "luftbårne", "flybåren", "aeromagnetisk", "SkyTEM",
            "elektromagnetisk", "gammaspektrometri", "magnetometri", "geophysical", "airborne"]
PAGE = 100


def _run(ctx, res, seen, text=None):
    page = 1
    while page <= 40:
        body = {"pagineringDto": {"aktuelSide": page, "maksElementer": PAGE,
                                  "sorteringFelt": "PUBLIKATION_DATO", "retning": "Desc"},
                "filterDto": {"formularType": [], "opgaveType": [], "procedureType": [],
                              "smvVenligType": []}}
        if text:
            body["fritekstQuery"] = text
        else:
            body["udbudStatusFilter"] = "AKTIV"
        r = post(API, json=body, timeout=ctx.timeout)
        res.queries += 1
        if r.status_code != 200:
            res.errors.append(f"{text or 'active'} p{page} HTTP {r.status_code}: {r.text[:200]}")
            return
        d = r.json()
        rows = d.get("resultatElementDtoList") or []
        old = 0
        for x in rows:
            da = x.get("dataDa") or {}
            if text and parse_date(da.get("publiceringsdato")) < ctx.since.isoformat():
                old += 1
                continue
            if x.get("noticeId") not in seen:
                res.rows_seen += 1
            en = x.get("dataEn") or {}
            nid, ver, pub = x.get("noticeId", ""), x.get("noticeVersion", ""), x.get("noticePublicationNumber", "")
            fr = da.get("tidsfrister") or []
            desc = da.get("beskrivelse") or ""
            if en.get("beskrivelse") and en.get("beskrivelse") != desc:
                desc += " | " + en["beskrivelse"]
            seen[nid] = Candidate(
                portal=PORTAL.key, ref=pub or nid, title=da.get("titel") or en.get("titel") or "",
                url=f"https://udbud.dk/detaljevisning?noticeId={nid}&noticeVersion={ver}&noticePublicationNumber={pub}",
                buyer=da.get("ordregiver") or "", country="DK",
                published=parse_date(da.get("publiceringsdato")),
                deadline=parse_date(min(fr)) if fr else "",
                description=f"{desc} [CPV {da.get('cpvKode')} {da.get('cpvTitel')}]"[:2000],
                value=f"{da.get('anslaaetVaerdi')} {da.get('anslaaetVaerdiValuta')}" if da.get("anslaaetVaerdi") else "",
                notice_type=da.get("formulartype") or "", language="da",
                extra={"cpv": [da.get("cpvKode")], "subtype": da.get("bkSubType"), "noticeId": nid},
            )
        total = d.get("totaltAntalResultater", 0)
        if len(rows) < PAGE or page * PAGE >= total or old:
            return
        page += 1


def fetch(ctx: RunContext) -> PortalResult:
    res = PortalResult(portal=PORTAL.key)
    seen = {}
    for text in [None] + KEYWORDS:
        try:
            _run(ctx, res, seen, text)
        except Exception as e:  # noqa: BLE001
            res.errors.append(f"{text or 'active'}: {type(e).__name__}: {e}")
    res.candidates = list(seen.values())
    return res
