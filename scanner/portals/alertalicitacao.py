"""Alerta Licitação (Brazilian aggregator of municipal/state/PNCP tenders).

The website's free "Busca PNCP" form returns no results to a plain request
or plain headless render (results are not rendered; the site runs reCAPTCHA
v3) and the full search needs a login, so the website is manual-only.

The site documents an official API (alertalicitacao.com.br/!api):
GET /api/v1/licitacoesAbertas?palavra_chave=...&pagina=N&licitacoesPorPagina=100
with a 32-character token in the "Token" header. A token needs an account
(first 100 rows/day free, then R$0.01 per row and per request). If
ALERTALICITACAO_TOKEN is set the adapter runs one keyword query per term
(open tenders only; the API has no publication date, so ctx.since cannot be
applied server-side); otherwise it makes no calls.
"""
import os

from ..core import Candidate, PortalInfo, PortalResult, RunContext, get, parse_date

PORTAL = PortalInfo(key="alertalicitacao", name="Alerta Licitação (Brazil)", region="Americas",
                    method="Official API v1 (token in ALERTALICITACAO_TOKEN); website manual-only",
                    min_rows=1, url="https://alertalicitacao.com.br/")

API = "https://alertalicitacao.com.br/api/v1/licitacoesAbertas/"
KEYWORDS = ["aerolevantamento", "aerogeofísico", "magnetometria", "gamaespectrometria", "geofísica",
            "levantamento geofísico", "gravimetria", "perfilamento a laser"]
MAX_PAGES = 2


def fetch(ctx: RunContext) -> PortalResult:
    res = PortalResult(portal=PORTAL.key)
    token = os.environ.get("ALERTALICITACAO_TOKEN", "").strip()
    if not token:
        res.errors.append("ALERTALICITACAO_TOKEN not set (token needs an Alerta Licitação account); "
                          "website search is manual-only: results not served to plain/headless requests")
        return res
    seen = {}
    for kw in KEYWORDS:
        for page in range(1, MAX_PAGES + 1):
            try:
                r = get(API, params={"palavra_chave": kw, "pagina": page, "licitacoesPorPagina": 100},
                        headers={"Token": token}, timeout=ctx.timeout)
                res.queries += 1
                if r.status_code != 200:
                    res.errors.append(f"{kw}: HTTP {r.status_code}")
                    break
                d = r.json()
                if d.get("totalErros"):
                    res.errors.append(f"{kw}: {d.get('erros')}"[:300])
                    break
                for x in d.get("licitacoes") or []:
                    res.rows_seen += 1
                    lid = x.get("id_licitacao", "")
                    seen.setdefault(lid, Candidate(
                        portal=PORTAL.key, ref=lid, title=x.get("titulo", "") + " - " + (x.get("objeto") or "")[:250],
                        url=x.get("link") or f"https://alertalicitacao.com.br/!licitacao/{lid}",
                        buyer=x.get("orgao", ""), country="Brazil",
                        deadline=parse_date(x.get("abertura_datetime") or x.get("abertura")),
                        description=x.get("objeto", ""), notice_type="tender", language="pt",
                        extra={"uf": x.get("uf", ""), "municipio": x.get("municipio", ""),
                               "tipo": x.get("tipo", ""), "link_externo": x.get("linkExterno", ""),
                               "keyword": kw}))
                if page >= int(d.get("paginas") or 1):
                    break
            except Exception as e:  # noqa: BLE001
                res.errors.append(f"{kw}: {type(e).__name__}: {e}")
                break
    res.candidates = list(seen.values())
    return res
