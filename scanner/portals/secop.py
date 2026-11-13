"""Colombia SECOP II processes via the official open-data Socrata API
(datos.gov.co dataset p6dx-8zbt "SECOP II - Procesos de Contratación";
keyless; tested 13 Nov 2026).

Server-side $where on keyword stems in the process name or description
(upper-cased; stems chosen to survive missing accents), limited to records
published, last published or awarded on/after ctx.since. Awarded records are
kept with notice_type="award".
"""
from ..core import Candidate, PortalInfo, PortalResult, RunContext, get, parse_date

PORTAL = PortalInfo(key="secop", name="SECOP II (Colombia)", region="Americas",
                    method="datos.gov.co Socrata SODA API (official open data, keyless)", min_rows=1,
                    url="https://community.secop.gov.co/Public/Tendering/ContractNoticeManagement/Index")

API = "https://www.datos.gov.co/resource/p6dx-8zbt.json"
STEMS = ["GEOF", "MAGNET", "AEROMAGN", "GRAVIM", "RADIOMET", "ELECTROMAGN", "ELECTRO MAGN",
         "AEROGEOF", "AEROTRANSPORTAD", "LIDAR", "GAMMA", "ESPECTROMETR", "AEROFOTOGRAM"]
PAGE = 1000


def _where(since):
    kw = " OR ".join(f"upper({f}) like '%{s}%'" for s in STEMS
                     for f in ("nombre_del_procedimiento", "descripci_n_del_procedimiento"))
    d = f"'{since}T00:00:00'"
    return (f"({kw}) AND (fecha_de_publicacion_del >= {d} OR fecha_de_ultima_publicaci >= {d} "
            f"OR fecha_adjudicacion >= {d})")


def fetch(ctx: RunContext) -> PortalResult:
    res = PortalResult(portal=PORTAL.key)
    seen = {}
    try:
        where = _where(ctx.since.isoformat())
        offset = 0
        while offset < 10 * PAGE:
            r = get(API, params={"$where": where, "$limit": PAGE, "$offset": offset,
                                 "$order": "fecha_de_publicacion_del DESC"}, timeout=max(ctx.timeout, 60))
            res.queries += 1
            if r.status_code != 200:
                res.errors.append(f"HTTP {r.status_code}: {r.text[:200]}")
                break
            rows = r.json()
            for x in rows:
                res.rows_seen += 1
                ref = x.get("id_del_proceso") or x.get("referencia_del_proceso") or ""
                url = (x.get("urlproceso") or {}).get("url", "") if isinstance(x.get("urlproceso"), dict) \
                    else str(x.get("urlproceso") or "")
                awarded = (x.get("adjudicado") or "").lower() == "si" or bool(x.get("fecha_adjudicacion"))
                desc = (x.get("descripci_n_del_procedimiento") or "").strip()
                name = (x.get("nombre_del_procedimiento") or "").strip()
                if len(name) < 60 and desc and desc[:40] not in name:  # names are often a person or a PO no.
                    name = f"{name}: {desc[:250]}" if name else desc[:300]
                seen[ref or url] = Candidate(
                    portal=PORTAL.key, ref=ref, title=name[:320],
                    url=url or PORTAL.url, buyer=x.get("entidad", ""), country="Colombia",
                    published=parse_date(x.get("fecha_de_publicacion_del") or x.get("fecha_de_ultima_publicaci")),
                    deadline=parse_date(x.get("fecha_de_recepcion_de")),
                    description=desc[:1500], value=str(x.get("precio_base") or ""),
                    notice_type="award" if awarded else "tender", language="es",
                    extra={"reference": x.get("referencia_del_proceso", ""),
                           "modalidad": x.get("modalidad_de_contratacion", ""),
                           "estado": x.get("estado_del_procedimiento", ""),
                           "fase": x.get("fase", ""),
                           "proveedor": x.get("nombre_del_proveedor", ""),
                           "valor_adjudicado": x.get("valor_total_adjudicacion", ""),
                           "fecha_adjudicacion": parse_date(x.get("fecha_adjudicacion")),
                           "departamento": x.get("departamento_entidad", "")},
                )
            if len(rows) < PAGE:
                break
            offset += PAGE
    except Exception as e:  # noqa: BLE001
        res.errors.append(f"{type(e).__name__}: {e}")
    res.candidates = list(seen.values())
    return res
