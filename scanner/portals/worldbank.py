"""World Bank procurement notices via the keyless Search API v2
(search.worldbank.org/api/v2/procnotices; tested 13 Nov 2026).

Two legs:
  * multilingual keyword queries (qterm), sorted newest first, paged until the
    notice date drops below ctx.since;
  * a standing project watch (WATCH dict): every notice of any type on those
    projects in the window, title-prefixed "[WATCH <id>]" so it surfaces
    regardless of keywords.
Contract Award notices are kept with notice_type="award".
"""
import datetime as dt
import html as _html
import re

from ..core import Candidate, PortalInfo, PortalResult, RunContext, get, parse_date

PORTAL = PortalInfo(key="worldbank", name="World Bank procurement notices", region="Global/Donor",
                    method="Search API v2 procnotices (keyless)", min_rows=1,
                    url="https://projects.worldbank.org/en/projects-operations/procurement")

API = "https://search.worldbank.org/api/v2/procnotices"
TERMS = [
    "airborne", "aeromagnetic", "geophysical", "geophysics", "geological mapping", "magnetic survey",
    "gravity survey", "radiometric", "gamma spectrometry", "electromagnetic", "LiDAR", "heliborne",
    "geological survey", "mineral exploration",
    "géophysique", "géophysiques", "aéroporté", "levés géophysiques", "cartographie géologique",
    "aéromagnétique", "spectrométrie",
    "geofísico", "geofísica", "aerogeofísico", "levantamiento geofísico", "cartografía geológica",
    "levantamento geofísico", "aerolevantamento",
]
WATCH = {
    "P506438": "DRC Inga 3 (Kongo Central airborne geophysics)",
    "P510607": "Peru Strategic Minerals Sector (INGEMMET aerial survey)",
}
FL = ("id,notice_type,noticedate,bid_description,bid_reference_no,project_id,project_name,"
      "project_ctry_name,submission_deadline_date,contact_organization,notice_lang_name,notice_text,"
      "procurement_method_name")
ROWS = 100


def _date(s):
    try:
        return dt.datetime.strptime(s, "%d-%b-%Y").date()
    except Exception:  # noqa: BLE001
        p = parse_date(s)
        return dt.date.fromisoformat(p) if p else None


def _strip(h):
    t = re.sub(r"<[^>]+>", " ", h or "")
    return re.sub(r"\s+", " ", _html.unescape(t)).strip()


def _cand(n):
    nt = n.get("notice_type", "")
    nd = _date(n.get("noticedate", ""))
    title = n.get("bid_description") or n.get("project_name") or ""
    desc = _strip(n.get("notice_text", ""))[:1500]
    return Candidate(
        portal="worldbank", ref=n.get("id", ""), title=title.strip(),
        url=f"https://projects.worldbank.org/en/projects-operations/procurement-detail/{n.get('id', '')}",
        buyer=n.get("contact_organization", ""), country=n.get("project_ctry_name", ""),
        published=nd.isoformat() if nd else "", deadline=parse_date(n.get("submission_deadline_date")),
        description=desc, notice_type="award" if "award" in nt.lower() else nt,
        language=n.get("notice_lang_name", ""),
        extra={"project_id": n.get("project_id", ""), "project_name": n.get("project_name", ""),
               "bid_reference_no": n.get("bid_reference_no", ""), "wb_notice_type": nt},
    )


def _query(params, ctx, res, max_pages=5):
    """Yield notices newest-first while noticedate >= since."""
    os_ = 0
    for _ in range(max_pages):
        p = dict(params, format="json", rows=ROWS, os=os_, srt="submission_date", order="desc", fl=FL)
        r = get(API, params=p, timeout=ctx.timeout)
        res.queries += 1
        if r.status_code != 200:
            res.errors.append(f"{params}: HTTP {r.status_code}")
            return
        data = r.json()
        notices = data.get("procnotices") or []
        if isinstance(notices, dict):
            notices = list(notices.values())
        old = False
        for n in notices:
            res.rows_seen += 1
            d = _date(n.get("noticedate", ""))
            if d and d < ctx.since:
                old = True
                continue
            yield n
        if old or len(notices) < ROWS:
            return
        os_ += ROWS


def fetch(ctx: RunContext) -> PortalResult:
    res = PortalResult(portal=PORTAL.key)
    seen = {}
    for t in TERMS:
        try:
            for n in _query({"qterm": t}, ctx, res):
                c = _cand(n)
                if c.ref:
                    seen.setdefault(c.ref, c)
        except Exception as e:  # noqa: BLE001
            res.errors.append(f"qterm={t}: {type(e).__name__}: {e}")
    for pid, label in WATCH.items():
        try:
            k = 0
            for n in _query({"project_id": pid}, ctx, res):
                c = _cand(n)
                c.title = f"[WATCH {pid}] {c.title}"
                c.description = f"airborne geophysical survey watch ({label}). {c.description}"
                c.extra["watch"] = pid
                seen[c.ref] = c  # watch version wins
                k += 1
            res.notes.append(f"watch {pid}: {k} notice(s) in window")
        except Exception as e:  # noqa: BLE001
            res.errors.append(f"watch {pid}: {type(e).__name__}: {e}")
    res.candidates = list(seen.values())
    return res
