"""Pakistan PPRA e-PMS public "Active Tenders" (linked from ppra.gov.pk):
https://epms.ppra.gov.pk/public/tenders/active-tenders?page=N
Server-rendered HTML, 50 rows/page, newest advertised first, no login.
We page until a page is empty or entirely older than ctx.since.
"""
import html as _html
import re

from ..core import Candidate, PortalInfo, PortalResult, RunContext, get, parse_date

PORTAL = PortalInfo(key="ppra", name="Pakistan PPRA e-PMS active tenders", region="Asia/Middle East",
                    method="Public HTML list (paged)", min_rows=50,
                    url="https://epms.ppra.gov.pk/public/tenders/active-tenders")

BASE = "https://epms.ppra.gov.pk"
MAX_PAGES = 80


def _t(s):
    return re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def _dl(row, label):
    m = re.search(r'cb-rt-dl">' + re.escape(label) + r'</span>\s*<span class="cb-rt-dv">(.*?)</span>\s*</div>', row, re.S)
    return _t(m[1]) if m else ""


def _parse(page):
    out = []
    for row in page.split('<tr class="cb-rt-main')[1:]:
        no = re.search(r'class="cb-rt-name[^"]*">([^<]+)</strong>', row)
        det = re.search(r'data-label="Tender Details">\s*<span>\s*<strong>(.*?)</strong>', row, re.S)
        adv = re.search(r'data-label="Advertised">([^<]+)<', row)
        clo = re.search(r'data-label="Closing">\s*<strong[^>]*>([^<]+)<', row)
        badges = re.findall(r'<small class="[^"]*badge[^"]*">([^<]+)</small>', row)
        org = re.search(r'Organization</span>\s*<span class="cb-rt-dv">(.*?)</small>', row, re.S)
        out.append(dict(no=_t(no[1]) if no else "", title=_t(det[1]) if det else "",
                        adv=adv[1].strip() if adv else "", closing=clo[1].strip() if clo else "",
                        badges=[_t(b) for b in badges], org=_t(org[1]) if org else "",
                        ttype=_dl(row, "Tender Type"), cat=_dl(row, "Procurement Category")))
    return out


def fetch(ctx: RunContext) -> PortalResult:
    res = PortalResult(portal=PORTAL.key)
    since = ctx.since.isoformat()
    seen = {}
    try:
        for p in range(1, MAX_PAGES + 1):
            r = get(f"{BASE}/public/tenders/active-tenders", params={"page": p}, timeout=ctx.timeout)
            res.queries += 1
            if r.status_code != 200:
                res.errors.append(f"page {p}: HTTP {r.status_code}")
                break
            rows = _parse(r.text)
            res.rows_seen += len(rows)
            if not rows:
                if p == 1:
                    res.errors.append("no rows on page 1 (layout change?)")
                break
            fresh = 0
            for d in rows:
                pub = parse_date(d["adv"])
                if pub and pub < since:
                    continue
                fresh += 1
                seen.setdefault(d["no"] or d["title"], Candidate(
                    portal="ppra", ref=d["no"], title=d["title"],
                    url=f"{BASE}/public/tenders/tender-details/{d['no']}" if d["no"] else PORTAL.url,
                    buyer=d["org"], country="Pakistan", published=pub, deadline=parse_date(d["closing"]),
                    description=" | ".join(x for x in [d["ttype"], d["cat"], *d["badges"]] if x),
                    notice_type="tender", language="en"))
            if fresh == 0:
                break
    except Exception as e:  # noqa: BLE001
        res.errors.append(f"{type(e).__name__}: {e}")
    res.candidates = list(seen.values())
    return res
