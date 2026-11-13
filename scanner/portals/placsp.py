"""Spain Plataforma de Contratación del Sector Público (PLACSP), official ATOM
syndication feed 643 "licitacionesPerfilesContratanteCompleto3" (keyless),
newest-first, paginated via rel="next".

Volume problem (measured 13 Nov 2026): ~4,000 entry updates/day (every status
change: PUB, EV, ADJ, RES...), 500 entries per ~14 MB uncompressed page,
~15 s per page. A full week is ~55 pages / ~13 min, so the adapter works to a
time budget (default 150 s, ~4-5k entries, about one working day), newest
first. Set PLACSP_BUDGET_S (e.g. 900) for a full weekly sweep. There is no
server-side keyword/CPV filter on the feed. TED still covers above-threshold
Spanish notices."""
import os
import re
import time
import xml.etree.ElementTree as ET

from ..core import Candidate, PortalInfo, PortalResult, RunContext, get, parse_date

PORTAL = PortalInfo(key="placsp", name="PLACSP (Spain)", region="Europe",
                    method="Official ATOM syndication feed 643 (time-budgeted, newest first)",
                    min_rows=500, url="https://contrataciondelestado.es/wps/portal/plataforma")

FEED = "https://contrataciondelestado.es/sindicacion/sindicacion_643/licitacionesPerfilesContratanteCompleto3.atom"
NS = {"a": "http://www.w3.org/2005/Atom",
      "cbc": "urn:dgpe:names:draft:codice:schema:xsd:CommonBasicComponents-2",
      "cac": "urn:dgpe:names:draft:codice:schema:xsd:CommonAggregateComponents-2",
      "cpe": "urn:dgpe:names:draft:codice-place-ext:schema:xsd:CommonAggregateComponents-2",
      "cbe": "urn:dgpe:names:draft:codice-place-ext:schema:xsd:CommonBasicComponents-2"}
STATUS = {"PRE": "anuncio previo", "PUB": "en plazo", "EV": "pendiente de adjudicación", "ADJ": "adjudicada",
          "RES": "resuelta", "ANUL": "anulada"}


def _t(el, path):
    x = el.find(path, NS)
    return (x.text or "").strip() if x is not None and x.text else ""


def fetch(ctx: RunContext) -> PortalResult:
    res = PortalResult(portal=PORTAL.key)
    budget = float(os.environ.get("PLACSP_BUDGET_S", "600"))
    t0 = time.time()
    seen = {}
    url = FEED
    since = ctx.since.isoformat()
    reached_since = False
    try:
        while url and not reached_since:
            if time.time() - t0 > budget:
                res.notes.append(f"time budget {budget:.0f}s reached after {res.queries} pages; "
                                 f"oldest entry read {min((c.extra['updated'] for c in seen.values()), default='?')}")
                break
            r = get(url, timeout=max(ctx.timeout, 90))
            res.queries += 1
            if r.status_code != 200:
                res.errors.append(f"HTTP {r.status_code} on {url[-60:]}")
                break
            root = ET.fromstring(r.content)
            nxt = None
            for l in root.findall("a:link", NS):
                if l.get("rel") == "next":
                    nxt = l.get("href")
            for e in root.findall("a:entry", NS):
                res.rows_seen += 1
                updated = _t(e, "a:updated")
                if updated[:10] < since:
                    reached_since = True
                    continue
                eid = _t(e, "a:id").rsplit("/", 1)[-1]
                link = e.find("a:link", NS)
                cfs = e.find("cpe:ContractFolderStatus", NS)
                folder = status = buyer = deadline = cpv = budget_amt = pname = ""
                if cfs is not None:
                    folder = _t(cfs, "cbc:ContractFolderID")
                    status = _t(cfs, "cbe:ContractFolderStatusCode")
                    buyer = _t(cfs, "cpe:LocatedContractingParty/cac:Party/cac:PartyName/cbc:Name")
                    pp = cfs.find("cac:ProcurementProject", NS)
                    if pp is not None:
                        pname = _t(pp, "cbc:Name")
                        budget_amt = _t(pp, "cac:BudgetAmount/cbc:TotalAmount")
                        cpv = ",".join(x.text for x in pp.findall(
                            "cac:RequiredCommodityClassification/cbc:ItemClassificationCode", NS) if x.text)
                    deadline = _t(cfs, "cac:TenderingProcess/cac:TenderSubmissionDeadlinePeriod/cbc:EndDate")
                title = _t(e, "a:title") or pname
                if eid in seen:  # older update of the same folder; keep newest
                    continue
                seen[eid] = Candidate(
                    portal=PORTAL.key, ref=folder or eid, title=title,
                    url=link.get("href") if link is not None else f"https://contrataciondelestado.es/sindicacion/licitacionesPerfilContratante/{eid}",
                    buyer=buyer, country="ES", published=parse_date(updated), deadline=parse_date(deadline),
                    description=f"{_t(e, 'a:summary')} | CPV {cpv}"[:2000],
                    value=f"{budget_amt} EUR" if budget_amt else "",
                    notice_type=STATUS.get(status, status), language="es",
                    extra={"cpv": cpv.split(",") if cpv else [], "updated": updated, "placsp_id": eid},
                )
            url = nxt
    except Exception as e:  # noqa: BLE001
        res.errors.append(f"{type(e).__name__}: {e}")
    res.candidates = list(seen.values())
    return res
