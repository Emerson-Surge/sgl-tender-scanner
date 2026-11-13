// Headless page renderer for JS-only portals. Reads JSON from stdin:
// {urls, wait_ms, wait_for, timeout_ms, html}; writes a JSON array to stdout.
const { chromium } = require('playwright');

(async () => {
  let input = '';
  for await (const chunk of process.stdin) input += chunk;
  const cfg = JSON.parse(input);
  const browser = await chromium.launch();
  const ctx = await browser.newContext({
    userAgent: 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36',
    locale: 'en-US',
  });
  const out = [];
  for (const url of cfg.urls) {
    const page = await ctx.newPage();
    const rec = { url };
    try {
      const resp = await page.goto(url, { timeout: cfg.timeout_ms || 60000, waitUntil: 'domcontentloaded' });
      rec.status = resp ? resp.status() : null;
      try { await page.waitForLoadState('networkidle', { timeout: 20000 }); } catch (e) {}
      if (cfg.wait_for) {
        try { await page.waitForSelector(cfg.wait_for, { timeout: 25000 }); } catch (e) { rec.wait_for_missed = true; }
      }
      await page.waitForTimeout(cfg.wait_ms || 3000);
      rec.final_url = page.url();
      rec.text = await page.evaluate(() => document.body ? document.body.innerText : '');
      if (cfg.html) rec.html = await page.content();
      rec.links = await page.evaluate(() => Array.from(document.querySelectorAll('a[href]')).slice(0, 3000)
        .map(a => ({ href: a.href, text: (a.innerText || '').trim().slice(0, 400) })));
    } catch (e) {
      rec.error = String(e.message || e).slice(0, 300);
    }
    out.push(rec);
    await page.close();
  }
  await browser.close();
  process.stdout.write(JSON.stringify(out));
})().catch(e => { console.error(e); process.exit(1); });
