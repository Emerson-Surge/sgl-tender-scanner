"""ComprasMX (Mexico federal procurement, successor of CompraNet): public site
comprasmx.buengobierno.gob.mx/sitiopublico, "Anuncios vigentes" table, read
with a plain headless Chromium render (no login; tested 13 Nov 2026).

The page is an Angular app showing 100 rows per page (~900 open notices);
the adapter clicks the page's own "next" button through all pages. Columns:
procedure number, character, name, agency acronym, status, clarification
meeting date, proposal opening date (-> deadline), procedure type. The list
has no publication date and the app has no per-notice URL, so published is
empty (all open notices are returned every run; the runner's state dedupes)
and url is the public site.
"""
import json
import subprocess

from ..core import ROOT, Candidate, PortalInfo, PortalResult, RunContext, parse_date

SITE = "https://comprasmx.buengobierno.gob.mx/sitiopublico/#/"
PORTAL = PortalInfo(key="comprasmx", name="ComprasMX (Mexico)", region="Americas",
                    method="Public site 'Anuncios vigentes', headless render + paging", min_rows=200,
                    url=SITE, uses_browser=True)

JS = r"""
const { chromium } = require('playwright');
(async () => {
  const url = process.argv[1];
  const b = await chromium.launch(); const p = await b.newPage();
  const out = {rows: [], errors: [], total: ''};
  const grab = () => p.$$eval('table tbody tr', trs => trs.map(tr => Array.from(tr.querySelectorAll('td'))
      .map(td => td.innerText.trim())).filter(c => c.length >= 8));
  try {
    await p.goto(url, {waitUntil: 'domcontentloaded', timeout: 60000});
    await p.waitForFunction(() => /Total:\s*[1-9]/.test(document.body.innerText), null, {timeout: 90000});
    await p.waitForTimeout(1000);
    out.total = await p.evaluate(() => { const m = document.body.innerText.match(/Total:\s*([\d,.]+)/); return m ? m[1] : ''; });
    for (let i = 0; i < 60; i++) {
      out.rows.push(...await grab());
      const next = await p.$('.p-paginator-next');
      if (!next) break;
      const dis = await next.evaluate(e => e.classList.contains('p-disabled') || e.disabled);
      if (dis) break;
      const first = await p.$eval('table tbody tr td:nth-child(2)', e => e.innerText).catch(() => '');
      await next.click();
      await p.waitForFunction(f => { const e = document.querySelector('table tbody tr td:nth-child(2)');
                                     return e && e.innerText !== f; }, first, {timeout: 20000})
             .catch(() => out.errors.push('page ' + (i + 2) + ' did not change'));
    }
  } catch (e) { out.errors.push(String(e.message || e).slice(0, 300)); }
  await b.close();
  process.stdout.write(JSON.stringify(out));
})().catch(e => { console.error(e); process.exit(1); });
"""


def fetch(ctx: RunContext) -> PortalResult:
    res = PortalResult(portal=PORTAL.key)
    try:
        p = subprocess.run(["node", "-e", JS, SITE], cwd=str(ROOT), capture_output=True, text=True, timeout=170)
        res.queries = 1
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
    total = int((data.get("total") or "0").replace(",", "").replace(".", "") or 0)
    if total and len(rows) < total * 0.9:
        res.notes.append(f"read {len(rows)} of {total} open notices")
    seen = {}
    for r in rows:
        try:
            _, num, char, name, agency, status, junta, apertura, ptype = (r + [""] * 9)[:9]
            if num in seen:
                continue
            seen[num] = Candidate(
                portal=PORTAL.key, ref=num, title=name, url=SITE, buyer=agency, country="Mexico",
                deadline=parse_date(apertura), notice_type="tender", language="es",
                description=f"{ptype}; {char}",
                extra={"status": status, "junta_aclaraciones": junta, "apertura": apertura,
                       "procedure_type": ptype, "character": char},
            )
        except Exception as e:  # noqa: BLE001
            res.errors.append(f"row: {type(e).__name__}: {e}")
    res.candidates = list(seen.values())
    return res
