"""Brazil PNCP (Portal Nacional de Contratações Públicas) via the official
keyless Consultation API v1 (pncp.gov.br/api/consulta; tested 13 Nov 2026).

The API has no keyword search; the CNPJ filter takes ~100 s per call and
multi-day windows on busy modalities take 7-13 s per page, while single-day
windows answer in ~1.5 s. So /contratacoes/publicacao is read as:
  * low-volume modalities (Concorrência presencial, Diálogo competitivo,
    Concurso, Manifestação de interesse, Pré-qualificação): whole window;
  * Concorrência eletrônica (~250/day) then Pregão eletrônico (~1,100/day):
    one window per day, newest first, until the BUDGET runs out.
Sequential with a pause (parallel or back-to-back paging gets HTTP 429).
Pages take 1.5-9 s, so in ~2 min a run reads roughly 15-40 pages: the
low-volume modalities and the newest days of Concorrência eletrônica, while
Pregão eletrônico is mostly not reached. Days left unscanned are listed in
res.notes. PARTIAL COVERAGE by design of the API; see PNCP keyword search
via other sources (dou, alertalicitacao) for recall.
"""
import datetime as dt
import time

from ..core import Candidate, PortalInfo, PortalResult, RunContext, get, parse_date

PORTAL = PortalInfo(key="pncp", name="PNCP (Brazil)", region="Americas",
                    method="Official Consultation API v1 (keyless)", min_rows=200,
                    url="https://pncp.gov.br/app/editais")

API = "https://pncp.gov.br/api/consulta/v1/contratacoes/publicacao"
MODS = {5: "Concorrência - Presencial", 2: "Diálogo Competitivo", 3: "Concurso",
        10: "Manifestação de Interesse", 11: "Pré-qualificação", 4: "Concorrência - Eletrônica",
        6: "Pregão - Eletrônico"}
SMALL = [5, 2, 3, 10, 11]       # a few pages per month: whole window in one query
DAILY = [4, 6]                  # high volume: one query per day, newest first
PAGE_CAP = 60
SIZE = 50
BUDGET = float(__import__("os").environ.get("PNCP_BUDGET_S", "420"))
PAUSE = 1.5     # seconds between calls; back-to-back paging trips HTTP 429 within ~10 calls


class RateLimited(Exception):
    pass


def _page(params, page, timeout):
    r = get(API, params={**params, "pagina": page, "tamanhoPagina": SIZE}, timeout=timeout, retries=0)
    if r.status_code == 429:
        raise RateLimited("HTTP 429")
    if r.status_code == 204:
        return {"data": [], "totalPaginas": 0}
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:150]}")
    return r.json()


def _cand(x):
    org = x.get("orgaoEntidade") or {}
    uni = x.get("unidadeOrgao") or {}
    cnpj, ano, seq = org.get("cnpj", ""), x.get("anoCompra", ""), x.get("sequencialCompra", "")
    ref = x.get("numeroControlePNCP") or f"{cnpj}-{ano}-{seq}"
    obj = (x.get("objetoCompra") or "").strip()
    return Candidate(
        portal=PORTAL.key, ref=ref, title=obj[:300],
        url=f"https://pncp.gov.br/app/editais/{cnpj}/{ano}/{seq}",
        buyer=org.get("razaoSocial", ""), country="Brazil",
        published=parse_date(x.get("dataPublicacaoPncp")),
        deadline=parse_date(x.get("dataEncerramentoProposta")),
        description=" | ".join(s for s in (obj, (x.get("informacaoComplementar") or "").strip()[:1000]) if s),
        value=str(x.get("valorTotalEstimado") or ""),
        notice_type="tender", language="pt",
        extra={"modalidade": x.get("modalidadeNome", ""), "uf": uni.get("ufSigla", ""),
               "municipio": uni.get("municipioNome", ""), "situacao": x.get("situacaoCompraNome", ""),
               "processo": x.get("processo", ""), "link_origem": x.get("linkSistemaOrigem") or ""},
    )


def fetch(ctx: RunContext) -> PortalResult:
    res = PortalResult(portal=PORTAL.key)
    t0 = time.time()
    seen = {}
    stop = []  # set once the API rate-limits twice in a row: stop politely

    def window(mod, d1, d2):
        """Read one modality for one date window; returns (pages_read, total_pages)."""
        params = {"dataInicial": d1.strftime("%Y%m%d"), "dataFinal": d2.strftime("%Y%m%d"),
                  "codigoModalidadeContratacao": mod}
        page, total = 1, 1
        while page <= min(total, PAGE_CAP) and time.time() - t0 < BUDGET and not stop:
            try:
                try:
                    d = _page(params, page, ctx.timeout)
                except RateLimited:
                    time.sleep(30)
                    d = _page(params, page, ctx.timeout)
            except Exception as e:  # noqa: BLE001
                if isinstance(e, RateLimited):
                    stop.append(1)
                res.errors.append(f"{MODS[mod]} {d1}..{d2} p{page}: {type(e).__name__}: {str(e)[:150]}")
                return page - 1, total
            res.queries += 1
            time.sleep(PAUSE)
            total = int(d.get("totalPaginas") or 0)
            for x in d.get("data") or []:
                res.rows_seen += 1
                try:
                    c = _cand(x)
                    seen.setdefault(c.ref, c)
                except Exception as e:  # noqa: BLE001
                    res.errors.append(f"row: {type(e).__name__}: {e}")
            page += 1
        return page - 1, total

    try:
        for mod in SMALL:
            got, total = window(mod, ctx.since, ctx.today)
            if got < total:
                res.notes.append(f"{MODS[mod]}: read {got}/{total} pages; rest not scanned")
        days = [ctx.today - dt.timedelta(days=i) for i in range((ctx.today - ctx.since).days + 1)]
        days = [d for d in days if d.weekday() < 6]  # PNCP publishes little on Sundays
        for mod in DAILY:
            got_all = tot_all = 0
            skipped = []
            for d in days:  # newest first
                if time.time() - t0 >= BUDGET or stop:
                    skipped.append(d)
                    continue
                got, total = window(mod, d, d)
                got_all += got
                tot_all += total
                if got < total:
                    skipped.append(d)
            if skipped:
                res.notes.append(f"{MODS[mod]}: time budget/rate limit; days not (fully) scanned: "
                                 f"{min(skipped)}..{max(skipped)} ({len(skipped)} days)")
    except Exception as e:  # noqa: BLE001
        res.errors.append(f"{type(e).__name__}: {e}")
    res.candidates = list(seen.values())
    return res
