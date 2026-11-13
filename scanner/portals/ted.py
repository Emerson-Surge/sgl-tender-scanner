"""TED (EU) via the official Search API v3. Keyless for published notices
(tested 13 Nov 2026 from this environment). Two query legs: CPV codes, and a
multilingual full-text leg so notices with the wrong CPV still surface."""
from ..core import Candidate, PortalInfo, PortalResult, RunContext, post, parse_date

PORTAL = PortalInfo(key="ted", name="TED (EU)", region="Europe", method="Official Search API v3 (keyless)",
                    min_rows=1, url="https://ted.europa.eu/en/search")

API = "https://api.ted.europa.eu/v3/notices/search"
CPVS = ["71351710", "71353000", "71351210", "71351913", "71351100", "71352300", "71355000",
        "38260000", "71351200", "71352000", "71354000", "71354100"]
TEXT_TERMS = ["aeromagnetic", "airborne geophysical", "aerogeophysical", "heliborne", "gamma spectrometry",
              "aéromagnétique", "géophysique aéroportée", "aeroportés", "héliportés", "aerogeofísico",
              "aeromagnetik", "Aerogeophysik", "aerogeofysisk", "lentogeofysiikka", "geofizyczne lotnicze",
              "αερομαγνητική", "γεωφυσική", "electromagnetic survey", "airborne gravity", "magnetometry"]
FIELDS = ["notice-title", "publication-date", "deadline-receipt-tender-date-lot", "buyer-name",
          "buyer-country", "notice-type", "description-proc", "classification-cpv"]


def _pick(v):
    """TED multilingual fields: {lang: [text]} or [text] or str."""
    if isinstance(v, dict):
        for lang in ("eng", "fra", "deu", "spa", "por"):
            if lang in v:
                x = v[lang]
                return x[0] if isinstance(x, list) else x
        x = next(iter(v.values()), "")
        return x[0] if isinstance(x, list) else x
    if isinstance(v, list):
        return v[0] if v else ""
    return v or ""


def _run(q, ctx, res):
    page = 1
    while page <= 5:
        r = post(API, json={"query": q, "fields": FIELDS, "limit": 100, "page": page,
                            "paginationMode": "PAGE_NUMBER"}, timeout=ctx.timeout)
        res.queries += 1
        if r.status_code != 200:
            res.errors.append(f"HTTP {r.status_code}: {r.text[:200]}")
            return
        data = r.json()
        notices = data.get("notices", [])
        for n in notices:
            pub = n.get("publication-number", "")
            res.rows_seen += 1
            yield Candidate(
                portal="ted", ref=pub, title=_pick(n.get("notice-title")),
                url=f"https://ted.europa.eu/en/notice/-/detail/{pub}",
                buyer=_pick(n.get("buyer-name")), country=_pick(n.get("buyer-country")),
                published=parse_date(n.get("publication-date")),
                deadline=parse_date(_pick(n.get("deadline-receipt-tender-date-lot"))),
                description=_pick(n.get("description-proc"))[:1500],
                notice_type=("award" if str(_pick(n.get("notice-type"))).startswith(("can", "veat"))
                             else _pick(n.get("notice-type"))),
                extra={"cpv": n.get("classification-cpv")},
            )
        if len(notices) < 100:
            return
        page += 1


def fetch(ctx: RunContext) -> PortalResult:
    res = PortalResult(portal=PORTAL.key)
    since = ctx.since.strftime("%Y%m%d")
    seen = {}
    try:
        q1 = f"classification-cpv IN ({' '.join(CPVS)}) AND publication-date>={since}"
        for c in _run(q1, ctx, res):
            seen[c.ref] = c
        terms = " OR ".join(f'FT~"{t}"' for t in TEXT_TERMS)
        q2 = f"({terms}) AND publication-date>={since}"
        for c in _run(q2, ctx, res):
            seen.setdefault(c.ref, c)
    except Exception as e:  # noqa: BLE001
        res.errors.append(f"{type(e).__name__}: {e}")
    res.candidates = list(seen.values())
    return res
