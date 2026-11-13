"""Petronect (Petrobras purchasing portal): public list of opportunities open
for proposals, read with a plain headless Chromium render (tested 13 Nov 2026).

The list page (HTTP 200, no login) builds its table client-side, 10 rows per
page (~30 pages), with object titles cut at ~37 characters. The adapter:
  1. pages through the whole public list with the page's own "Próximo" button;
  2. runs the page's own "BUSCAR POR" keyword box (which also searches item
     descriptions and long texts) for geophysics stems, and for every hit
     opens the row's public "info" pop-up to read the item lines, which go into
     the description so the matcher sees e.g. "LIC AERO GRAVMAG NA BACIA DE
     PELOTAS" behind the truncated title.
Only documented UI actions on the public page; no internal endpoints called
directly. Rows are kept when their quotation period started on/after
ctx.since; keyword hits are always kept while open (they are few).
There is no per-notice public URL, so url = list page + "#<number>".
"""
import json
import subprocess

from ..core import ROOT, Candidate, PortalInfo, PortalResult, RunContext, parse_date

LIST = ("https://www.petronect.com.br/irj/go/km/docs/pccshrcontent/Site%20Content%20(Legacy)/"
        "Portal2018/pt/lista_licitacoes_publicadas_ft.html")
PORTAL = PortalInfo(key="petronect", name="Petronect (Petrobras)", region="Americas",
                    method="Public list page, headless render + on-page keyword search", min_rows=100,
                    url=LIST, uses_browser=True)

KEYWORDS = ["geof", "magnet", "gravim", "gravmag", "aerolev", "aerogeo", "aeromag", "gamaesp",
            "radiom", "eletromag", "lidar", "perfilamento a laser", "aerofotogra"]

JS = r"""
const { chromium } = require('playwright');
(async () => {
  const cfg = JSON.parse(process.argv[1]);
  const b = await chromium.launch(); const p = await b.newPage();
  const out = {rows: [], hits: {}, errors: []};
  const grab = () => p.$$eval('#result tr', trs => trs.map(tr => Array.from(tr.querySelectorAll('td'))
      .map(td => td.innerText.trim())).filter(c => c.length >= 7));
  const allPages = async () => {
    let rows = [], guard = 0;
    while (guard++ < 200) {
      rows.push(...await grab());
      const dis = await p.$eval('#next', e => e.classList.contains('disabled') || e.offsetParent === null).catch(() => true);
      if (dis) break;
      const first = await p.$eval('#result tr td', e => e.innerText).catch(() => '');
      await p.click('#next');
      await p.waitForFunction(f => { const e = document.querySelector('#result tr td'); return e && e.innerText !== f; },
                              first, {timeout: 5000}).catch(() => {});
    }
    return rows;
  };
  try {
    await p.goto(cfg.url, {waitUntil: 'domcontentloaded', timeout: 60000});
    await p.waitForSelector('#result tr td', {timeout: 60000});
    out.pages = await p.textContent('#IndFim');
    out.rows = await allPages();
    for (const kw of cfg.keywords) {
      try {
        await p.fill('#filterNewLayoutKeyWord', kw);
        await p.click('#resultTableHeaderKeySubmitBtn', {timeout: 10000});
        await p.waitForTimeout(1200);
        const rows = await allPages();
        const items = {};
        for (const r of rows.slice(0, 15)) {
          const a = await p.$(`#result a.modal-info[data-opport-num="${r[0]}"]`);
          if (!a) continue;
          await a.click(); await p.waitForTimeout(700);
          items[r[0]] = await p.evaluate(() => { const m = document.querySelector('.modal.in, .modal.show');
                                                 return m ? m.innerText.slice(0, 3000) : ''; });
          await p.evaluate(() => { if (window.jQuery) jQuery('.modal').modal('hide'); });
          await p.waitForTimeout(500);
        }
        out.hits[kw] = {rows, items};
        await p.click('#resultTableHeaderKeyResetBtn', {timeout: 10000}).catch(() => {});
        await p.waitForTimeout(800);
      } catch (e) {
        out.errors.push(kw + ': ' + String(e.message || e).slice(0, 200));
        await p.evaluate(() => { if (window.jQuery) jQuery('.modal').modal('hide'); }).catch(() => {});
      }
    }
  } catch (e) { out.errors.push(String(e.message || e).slice(0, 300)); }
  await b.close();
  process.stdout.write(JSON.stringify(out));
})().catch(e => { console.error(e); process.exit(1); });
"""


def _items(txt):
    """Item lines from the info pop-up ('8001.AA<TAB>LIC AERO GRAVMAG ...<TAB>Quantidade...')."""
    out = []
    for line in (txt or "").splitlines():
        parts = [x.strip() for x in line.split("\t") if x.strip()]
        if len(parts) >= 2 and parts[0].replace(".", "").isalnum() and parts[0][:1].isdigit():
            out.append(parts[1])
    return out


def fetch(ctx: RunContext) -> PortalResult:
    res = PortalResult(portal=PORTAL.key)
    try:
        p = subprocess.run(["node", "-e", JS, json.dumps({"url": LIST, "keywords": KEYWORDS})],
                           cwd=str(ROOT), capture_output=True, text=True, timeout=170)
        res.queries = 1 + len(KEYWORDS)
        if p.returncode != 0:
            res.errors.append(f"render failed: {p.stderr[-300:]}")
            return res
        data = json.loads(p.stdout)
    except Exception as e:  # noqa: BLE001
        res.errors.append(f"{type(e).__name__}: {e}")
        return res
    res.errors += [f"render: {e}" for e in data.get("errors", [])]
    rows = data.get("rows") or []
    res.rows_seen = len(rows)
    if rows and data.get("pages") and len(rows) < (int(data["pages"]) - 1) * 10:
        res.errors.append(f"paging incomplete: {len(rows)} rows for {data['pages']} pages")

    hit_kw, hit_txt = {}, {}
    for kw, h in (data.get("hits") or {}).items():
        for r in h.get("rows") or []:
            hit_kw.setdefault(r[0], []).append(kw)
        for num, txt in (h.get("items") or {}).items():
            hit_txt[num] = txt
    by_num = {r[0]: r for r in rows}
    for kw, h in (data.get("hits") or {}).items():  # a hit missing from the paged list still counts
        for r in h.get("rows") or []:
            by_num.setdefault(r[0], r)

    since = ctx.since.isoformat()
    out = []
    for num, r in by_num.items():
        try:
            num, obj, sub, company, scope, start, end = r[:7]
            pub, dl = parse_date(start), parse_date(end)
            if num not in hit_kw and pub and pub < since:
                continue
            items = _items(hit_txt.get(num, ""))
            desc = "; ".join(items)
            out.append(Candidate(
                portal=PORTAL.key, ref=num, title=obj, url=f"{LIST}#{num}", buyer=company,
                country="Brazil", published=pub, deadline=dl, description=desc,
                notice_type="tender", language="pt",
                extra={"sub_status": sub, "scope": scope, "keyword_hits": hit_kw.get(num, [])},
            ))
        except Exception as e:  # noqa: BLE001
            res.errors.append(f"row {r[:1]}: {type(e).__name__}: {e}")
    res.candidates = out
    return res
