"""Mercado Público (ChileCompra), two legs:

  * official API (api.mercadopublico.cl/servicios/v1/publico/licitaciones.json),
    one call per day in ctx.since..today, when a free ticket is in
    MERCADOPUBLICO_TICKET (register at api.mercadopublico.cl). Without it this
    leg is skipped with a note (an invalid ticket answers {"Codigo":203}).
  * the public search page www.mercadopublico.cl/BuscarLicitacion (no login),
    plain headless render, using its own "¿Qué deseas buscar?" box with
    geophysics keywords; first result page per keyword (title, description,
    dates, buyer). Tested 13 Nov 2026.
Rows are kept when published on/after ctx.since. url = the public
DetailsAcquisition page for the tender ID.
"""
import datetime as dt
import json
import os
import re
import subprocess
import time

from ..core import ROOT, Candidate, PortalInfo, PortalResult, RunContext, get, parse_date

PORTAL = PortalInfo(key="mercadopublico", name="Mercado Público (Chile)", region="Americas",
                    method="Official API (ticket, optional) + public search page keyword render", min_rows=1,
                    url="https://www.mercadopublico.cl/BuscarLicitacion", uses_browser=True)

API = "https://api.mercadopublico.cl/servicios/v1/publico/licitaciones.json"
SEARCH = "https://www.mercadopublico.cl/BuscarLicitacion"
DETAIL = "https://www.mercadopublico.cl/Procurement/Modules/RFB/DetailsAcquisition.aspx?idlicitacion={}"
KEYWORDS = ["geofisico", "geofisica", "aeromagnetico", "magnetometria", "gravimetria", "aerogeofisico",
            "espectrometria gamma", "radiometria", "electromagnetico", "levantamiento aereo", "lidar",
            "aerotransportado"]

JS = r"""
const { chromium } = require('playwright');
(async () => {
  const cfg = JSON.parse(process.argv[1]);
  const b = await chromium.launch(); const p = await b.newPage();
  const out = {hits: {}, errors: []};
  const grab = () => p.$$eval('.lic-bloq-wrap', bs => bs.map(b => ({
      id: ((b.querySelector('.id-licitacion span') || {}).innerText || '').trim(),
      estado: ((b.querySelector('.estado-texto') || {}).innerText || '').trim(),
      title: ((b.querySelector('h2') || {}).innerText || '').trim(),
      text: b.innerText.slice(0, 2000)})));
  try {
    await p.goto(cfg.url, {waitUntil: 'domcontentloaded', timeout: 60000});
    await p.waitForSelector('.lic-bloq-wrap', {timeout: 60000});
    for (const kw of cfg.keywords) {
      try {
        const before = await p.$eval('.lic-bloq-wrap .id-licitacion span', e => e.innerText).catch(() => '');
        await p.fill('#textoBusqueda', kw);
        await p.click('#btnBuscar');
        await p.waitForFunction(f => { const e = document.querySelector('.lic-bloq-wrap .id-licitacion span');
            return (e && e.innerText !== f) || !e; }, before, {timeout: 20000}).catch(() => {});
        await p.waitForTimeout(1500);
        const count = await p.evaluate(() => { const m = document.body.innerText
            .match(/encontra\w*\s*(?:más de)?\s*([\d.]+)\s*resultado/i); return m ? m[1] : ''; });
        out.hits[kw] = {count, rows: await grab()};
      } catch (e) { out.errors.push(kw + ': ' + String(e.message || e).slice(0, 200)); }
    }
  } catch (e) { out.errors.push(String(e.message || e).slice(0, 300)); }
  await b.close();
  process.stdout.write(JSON.stringify(out));
})().catch(e => { console.error(e); process.exit(1); });
"""


def _after(label, text):
    m = re.search(label + r"\s*\n+\s*(\d{2}/\d{2}/\d{4})", text)
    return parse_date(m[1]) if m else ""


def _api(ctx, res, ticket, seen):
    d = ctx.since
    while d <= ctx.today:
        try:
            r = get(API, params={"fecha": d.strftime("%d%m%Y"), "ticket": ticket}, timeout=ctx.timeout)
            res.queries += 1
            data = r.json() if r.status_code == 200 else {}
            if r.status_code != 200 or "Listado" not in data:
                res.errors.append(f"API {d}: HTTP {r.status_code} {str(data or r.text)[:150]}")
                if data.get("Codigo") == 203:  # invalid ticket: stop
                    return
            for x in data.get("Listado") or []:
                res.rows_seen += 1
                code = x.get("CodigoExterno", "")
                seen.setdefault(code, Candidate(
                    portal=PORTAL.key, ref=code, title=x.get("Nombre", ""), url=DETAIL.format(code),
                    country="Chile", published=d.isoformat(), deadline=parse_date(x.get("FechaCierre")),
                    notice_type="tender", language="es", extra={"estado": x.get("CodigoEstado", "")}))
        except Exception as e:  # noqa: BLE001
            res.errors.append(f"API {d}: {type(e).__name__}: {e}")
        d += dt.timedelta(days=1)
        time.sleep(0.5)  # the API rejects simultaneous requests per ticket


def fetch(ctx: RunContext) -> PortalResult:
    res = PortalResult(portal=PORTAL.key)
    seen = {}
    ticket = os.environ.get("MERCADOPUBLICO_TICKET", "").strip()
    if ticket:
        _api(ctx, res, ticket, seen)
    else:
        res.notes.append("MERCADOPUBLICO_TICKET not set: API leg skipped (free ticket at api.mercadopublico.cl); "
                         "public keyword search only")
    try:
        p = subprocess.run(["node", "-e", JS, json.dumps({"url": SEARCH, "keywords": KEYWORDS})],
                           cwd=str(ROOT), capture_output=True, text=True, timeout=170)
        res.queries += len(KEYWORDS)
        if p.returncode != 0:
            res.errors.append(f"search render failed: {p.stderr[-300:]}")
        else:
            data = json.loads(p.stdout)
            res.errors += [f"search: {e}" for e in data.get("errors", [])]
            since = ctx.since.isoformat()
            for kw, h in (data.get("hits") or {}).items():
                rows = h.get("rows") or []
                cnt = int((h.get("count") or "0").replace(".", "") or 0)
                if cnt > len(rows):
                    res.notes.append(f"'{kw}': {cnt} results, first {len(rows)} read")
                for r in rows:
                    res.rows_seen += 1
                    code = r.get("id", "")
                    text = r.get("text", "")
                    pub = _after("Fecha de publicación", text)
                    if pub and pub < since:
                        continue
                    lines = [x.strip() for x in text.splitlines() if x.strip()]
                    title = r.get("title", "")
                    desc = ""
                    if title in lines:
                        i = lines.index(title)
                        desc = lines[i + 1] if i + 1 < len(lines) and not lines[i + 1].startswith("Monto") else ""
                    m = re.search(r"Fecha de cierre\s*\n+\s*[^\n]*\n+\s*([^\n]+)", text)
                    c = seen.get(code)
                    if c and not c.description:
                        c.description = desc
                        continue
                    if c:
                        continue
                    seen[code] = Candidate(
                        portal=PORTAL.key, ref=code, title=title, url=DETAIL.format(code),
                        buyer=m[1].strip() if m else "", country="Chile", published=pub,
                        deadline=_after("Fecha de cierre", text), description=desc[:1500],
                        notice_type="tender", language="es",
                        extra={"estado": r.get("estado", ""), "keyword": kw})
    except Exception as e:  # noqa: BLE001
        res.errors.append(f"search: {type(e).__name__}: {e}")
    res.candidates = list(seen.values())
    return res
