"""Pertamina (Indonesia) public procurement announcements, headless render.

https://www.pertamina.com/en/tender now 404s; the public procurement pages are
/en/pengadaan-umum (General Procurement) and /en/pengadaan-di-daerah
(Regional Procurement), rendered client-side (tested 13 Nov 2026). Each shows
the ~6 newest announcement articles: title, category, <time datetime>, link to
/news/<slug>. Low volume by nature; actual bidding is in GEP SMART (vendor
login), which is not touched. ref = article slug.
"""
import html as _html
import re

from ..core import Candidate, PortalInfo, PortalResult, RunContext, browser, parse_date

PORTAL = PortalInfo(key="pertamina", name="Pertamina procurement announcements", region="Asia-Pacific",
                    method="Public announcement pages, headless render", min_rows=4,
                    url="https://www.pertamina.com/en/pengadaan-umum", uses_browser=True)

B = "https://www.pertamina.com"
PAGES = ["/en/pengadaan-umum", "/en/pengadaan-di-daerah"]
ART = re.compile(r"<article.*?</article>", re.S)


def _t(s):
    return re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def fetch(ctx: RunContext) -> PortalResult:
    res = PortalResult(portal=PORTAL.key)
    since = ctx.since.isoformat()
    seen = {}
    try:
        urls = [B + p for p in PAGES]
        for u, pg in zip(urls, browser(urls, wait_ms=3000, html=True)):
            res.queries += 1
            if pg.get("error") or (pg.get("status") or 0) >= 400 or "/error/" in (pg.get("final_url") or ""):
                res.errors.append(f"{u}: {pg.get('error') or pg.get('status')} {pg.get('final_url', '')}")
                continue
            for a in ART.findall(pg.get("html", "")):
                m = re.search(r'<h2[^>]*>\s*(?:<!--!-->)*\s*<a[^>]*href="((?:/[a-z]{2})?/news/[^"]+)"[^>]*>(.*?)</a>', a, re.S)
                if not m:
                    continue
                res.rows_seen += 1
                slug = m[1].rsplit("/", 1)[-1]
                if slug in seen:
                    continue
                cat = re.search(r'uppercase font-semibold">(.*?)</div>', a, re.S)
                tm = re.search(r'<time datetime="([^"]+)"', a)
                seen[slug] = Candidate(
                    portal=PORTAL.key, ref=slug, title=_t(m[2]), url=B + m[1], buyer="PT Pertamina (Persero) group",
                    country="Indonesia", published=parse_date(tm[1]) if tm else "",
                    notice_type=_t(cat[1]) if cat else "", language="id",
                    extra={"page": u.rsplit("/", 1)[-1]},
                )
        if res.queries and not seen and not res.errors:
            res.errors.append("no announcement articles parsed (layout change?)")
    except Exception as e:  # noqa: BLE001
        res.errors.append(f"{type(e).__name__}: {e}")
    res.candidates = [c for c in seen.values() if not c.published or c.published >= since]
    return res
