"""CanadaBuys (Government of Canada) via the official keyless open-data CSVs
(canadabuys.canada.ca/opendata; tested 13 Nov 2026).

Two files: today's new notices and all currently open notices. Both are
bilingual; English and French title/description are both handed to the
matcher. Rows are kept when published or amended on/after ctx.since.
Notices from MERX/provincial systems carry their own noticeURL; otherwise the
CanadaBuys notice page is built from the reference number.
"""
import csv
import html as _html
import io

from ..core import Candidate, PortalInfo, PortalResult, RunContext, get, parse_date

PORTAL = PortalInfo(key="canadabuys", name="CanadaBuys (Canada)", region="Americas",
                    method="Official open-data CSVs (keyless)", min_rows=100,
                    url="https://canadabuys.canada.ca/en/tender-opportunities")

BASE = "https://canadabuys.canada.ca/opendata/pub/"
FILES = ["newTenderNotice-nouvelAvisAppelOffres.csv", "openTenderNotice-ouvertAvisAppelOffres.csv"]


def _clean(s):
    return _html.unescape((s or "").replace("\r", " ").strip())


def _list(s):
    return "; ".join(x.strip() for x in (s or "").split("*") if x.strip())


def fetch(ctx: RunContext) -> PortalResult:
    res = PortalResult(portal=PORTAL.key)
    since = ctx.since.isoformat()
    seen = {}
    for f in FILES:
        try:
            r = get(BASE + f, timeout=max(ctx.timeout, 90))
            res.queries += 1
            if r.status_code != 200:
                res.errors.append(f"{f}: HTTP {r.status_code}")
                continue
            rows = list(csv.DictReader(io.StringIO(r.content.decode("utf-8-sig", errors="replace"))))
        except Exception as e:  # noqa: BLE001
            res.errors.append(f"{f}: {type(e).__name__}: {e}")
            continue
        res.rows_seen += len(rows)
        for row in rows:
            try:
                ref = (row.get("referenceNumber-numeroReference") or "").strip()
                pub = parse_date(row.get("publicationDate-datePublication"))
                amd = parse_date(row.get("amendmentDate-dateModification"))
                if max(pub, amd) < since:
                    continue
                t_en = _clean(row.get("title-titre-eng"))
                t_fr = _clean(row.get("title-titre-fra"))
                title = t_en if not t_fr or t_fr == t_en else f"{t_en} / {t_fr}"
                d_en = _clean(row.get("tenderDescription-descriptionAppelOffres-eng"))
                d_fr = _clean(row.get("tenderDescription-descriptionAppelOffres-fra"))
                desc = " | ".join(x for x in (d_en[:1500], d_fr[:1000],
                                              _list(row.get("unspscDescription-eng")),
                                              _list(row.get("gsinDescription-nibsDescription-eng"))) if x)
                url = (row.get("noticeURL-URLavis-eng") or "").strip() or \
                    f"https://canadabuys.canada.ca/en/tender-opportunities/tender-notice/{ref}"
                key = ref or url
                seen[key] = Candidate(
                    portal=PORTAL.key, ref=ref, title=title or row.get("solicitationNumber-numeroSollicitation", ""),
                    url=url, buyer=_clean(row.get("contractingEntityName-nomEntitContractante-eng")),
                    country="Canada", published=pub,
                    deadline=parse_date(row.get("tenderClosingDate-appelOffresDateCloture")),
                    description=desc,
                    notice_type="tender",
                    language="en/fr",
                    extra={"solicitation": row.get("solicitationNumber-numeroSollicitation", ""),
                           "amendment": row.get("amendmentNumber-numeroModification", ""),
                           "method": row.get("procurementMethod-methodeApprovisionnement-eng", ""),
                           "unspsc": _list(row.get("unspsc")),
                           "regions": _list(row.get("regionsOfDelivery-regionsLivraison-eng"))},
                )
            except Exception as e:  # noqa: BLE001
                res.errors.append(f"row: {type(e).__name__}: {e}")
    res.candidates = list(seen.values())
    return res
