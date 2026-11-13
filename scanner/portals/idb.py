"""Inter-American Development Bank procurement notices via the official CKAN
datastore at data.iadb.org (resource 856aabfd-2c6a-48fb-a8b8-19f3ff443618;
keyless; tested 13 Nov 2026).

One datastore_search_sql query for every notice published on/after
ctx.since (~60/week, all types: SPECIFIC, EOI, GENERAL, RFI, AWARD).
AWARD notices get notice_type="award". url = the notice document on
idbdocs (public), falling back to the project page.
"""
from ..core import Candidate, PortalInfo, PortalResult, RunContext, get, parse_date

PORTAL = PortalInfo(key="idb", name="IDB procurement notices", region="Global/Donor",
                    method="Official CKAN datastore SQL API (keyless)", min_rows=5,
                    url="https://www.iadb.org/en/how-we-can-work-together/procurement/procurement-projects/project-procurement")

API = "https://data.iadb.org/api/3/action/datastore_search_sql"
RES = "856aabfd-2c6a-48fb-a8b8-19f3ff443618"
COLS = ("noticeid, type, countryname, projectnumber, proyecturl, loannumber, noticetitle, documenturl, "
        "projectname, publicationdate, deadline, sectorenglnm, procurement_id, process_id, category_nm, "
        "prcrmnt_mthd_engl_nm, process_nm, process_desc")
TYPES = {"AWARD": "award", "SPECIFIC": "tender", "EOI": "eoi", "GENERAL": "prior-info",
         "REQUEST FOR INFORMATION": "rfi"}


def _c(s):
    return (s or "").replace("_x000D_", " ").strip()


def fetch(ctx: RunContext) -> PortalResult:
    res = PortalResult(portal=PORTAL.key)
    try:
        offset = 0
        while offset < 20000:
            sql = (f'SELECT {COLS} FROM "{RES}" WHERE publicationdate >= \'{ctx.since.isoformat()}\' '
                   f'ORDER BY publicationdate DESC LIMIT 1000 OFFSET {offset}')
            r = get(API, params={"sql": sql}, timeout=max(ctx.timeout, 60))
            res.queries += 1
            if r.status_code != 200:
                res.errors.append(f"HTTP {r.status_code}: {r.text[:200]}")
                break
            recs = r.json().get("result", {}).get("records", [])
            for x in recs:
                res.rows_seen += 1
                typ = _c(x.get("type")).upper()
                pid = _c(x.get("procurement_id")) or _c(x.get("process_id"))
                ref = _c(x.get("noticeid"))
                ref = f"{_c(x.get('projectnumber'))}/{ref}" if ref else pid
                desc = " | ".join(s for s in (_c(x.get("process_nm")), _c(x.get("process_desc"))[:1200],
                                              _c(x.get("projectname"))) if s)
                res.candidates.append(Candidate(
                    portal=PORTAL.key, ref=ref, title=_c(x.get("noticetitle")) or _c(x.get("process_nm")),
                    url=_c(x.get("documenturl")) or _c(x.get("proyecturl")),
                    buyer=_c(x.get("projectname")), country=_c(x.get("countryname")).title(),
                    published=parse_date(x.get("publicationdate")), deadline=parse_date(x.get("deadline")),
                    description=desc, notice_type=TYPES.get(typ, typ.lower()),
                    extra={"project": _c(x.get("projectnumber")), "loan": _c(x.get("loannumber")),
                           "sector": _c(x.get("sectorenglnm")), "method": _c(x.get("prcrmnt_mthd_engl_nm")),
                           "category": _c(x.get("category_nm")), "project_url": _c(x.get("proyecturl")),
                           "procurement_id": pid},
                ))
            if len(recs) < 1000:
                break
            offset += 1000
    except Exception as e:  # noqa: BLE001
        res.errors.append(f"{type(e).__name__}: {e}")
    return res
