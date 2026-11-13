"""France BOAMP via the official Opendatasoft Explore API v2.1 served from
www.boamp.fr (keyless). The boamp-datadila.opendatasoft.com host resets the
connection from this environment; www.boamp.fr/api/explore/... is the same
dataset and answers normally (13 Nov 2026).

Two legs:
  1. exports/json of every notice published since ctx.since (title-level; one
     call, ~2.5k rows/week, ~11k/30 days, ~8 s).
  2. full-text search() for geophysics keywords, pulling the eForms `donnees`
     so matched notices get a real description (lot descriptions etc.).
"""
import json

from ..core import Candidate, PortalInfo, PortalResult, RunContext, get, parse_date

PORTAL = PortalInfo(key="boamp", name="BOAMP (France)", region="Europe",
                    method="Official Opendatasoft API on boamp.fr (export + full-text search)",
                    min_rows=500, url="https://www.boamp.fr/pages/recherche/")

BASE = "https://www.boamp.fr/api/explore/v2.1/catalog/datasets/boamp"
SELECT = ("idweb,objet,dateparution,datelimitereponse,nomacheteur,nature_libelle,descripteur_libelle,"
          "type_marche,url_avis,famille_libelle,code_departement")
KEYWORDS = ["géophysique", "géophysiques", "aéroporté", "aéroportée", "héliporté", "héliportée",
            "magnétisme", "magnétométrie", "aéromagnétique", "spectrométrie", "radiométrie",
            "gravimétrie", "électromagnétique", "levés", "levé aérien", "lidar"]


def _texts(node, out, depth=0):
    """Collect cbc:Description / cbc:Name texts from eForms JSON."""
    if depth > 40 or len(out) > 60:
        return
    if isinstance(node, dict):
        for k, v in node.items():
            if k in ("cbc:Description", "cbc:Note") :
                vals = v if isinstance(v, list) else [v]
                for x in vals:
                    t = x.get("#text") if isinstance(x, dict) else x
                    if isinstance(t, str) and t not in out:
                        out.append(t)
            else:
                _texts(v, out, depth + 1)
    elif isinstance(node, list):
        for v in node:
            _texts(v, out, depth + 1)


def _cand(x, desc=""):
    idweb = x.get("idweb", "")
    descr = x.get("descripteur_libelle") or []
    return Candidate(
        portal=PORTAL.key, ref=idweb, title=x.get("objet") or "",
        url=x.get("url_avis") or f"https://www.boamp.fr/pages/avis/?q=idweb:{idweb}",
        buyer=x.get("nomacheteur") or "", country="FR",
        published=parse_date(x.get("dateparution")), deadline=parse_date(x.get("datelimitereponse")),
        description=(desc or "; ".join(descr))[:2000], notice_type=x.get("nature_libelle") or "",
        language="fr", extra={"descripteurs": descr, "famille": x.get("famille_libelle"),
                              "dept": x.get("code_departement")},
    )


def fetch(ctx: RunContext) -> PortalResult:
    res = PortalResult(portal=PORTAL.key)
    seen = {}
    since = ctx.since.isoformat()
    try:
        r = get(f"{BASE}/exports/json", params={"where": f"dateparution>=date'{since}'", "select": SELECT},
                timeout=max(ctx.timeout, 120))
        res.queries += 1
        if r.status_code == 200:
            for x in r.json():
                res.rows_seen += 1
                seen[x.get("idweb")] = _cand(x)
        else:
            res.errors.append(f"export HTTP {r.status_code}: {r.text[:200]}")
    except Exception as e:  # noqa: BLE001
        res.errors.append(f"export {type(e).__name__}: {e}")

    for kw in KEYWORDS:
        try:
            off = 0
            while off < 500:
                r = get(f"{BASE}/records", params={
                    "where": f"dateparution>=date'{since}' AND search(\"{kw}\")",
                    "select": SELECT + ",donnees", "limit": 100, "offset": off}, timeout=ctx.timeout)
                res.queries += 1
                if r.status_code != 200:
                    res.errors.append(f"search '{kw}' HTTP {r.status_code}: {r.text[:150]}")
                    break
                rows = r.json().get("results") or []
                for x in rows:
                    texts = []
                    try:
                        _texts(json.loads(x.get("donnees") or "{}"), texts)
                    except ValueError:
                        pass
                    c = _cand(x, " | ".join(texts))
                    if c.ref not in seen:
                        res.rows_seen += 1
                    seen[c.ref] = c
                if len(rows) < 100:
                    break
                off += 100
        except Exception as e:  # noqa: BLE001
            res.errors.append(f"search '{kw}' {type(e).__name__}: {e}")
    res.candidates = list(seen.values())
    return res
