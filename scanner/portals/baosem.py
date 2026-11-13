"""Algeria BAOSEM (Bulletin des Appels d'Offres du Secteur de l'Energie et des
Mines: Sonatrach, Sonelgaz, mining). Public, no subscription, via the site's
own search form: GET https://www.baosem.com/appel-offre/all
  ?date_debut=dd/mm/yyyy&date_fin=dd/mm/yyyy&text_placard=<full text>&p1=N
Public fields: bulletin no./date, Baosem ref, title (FR/EN/AR), notice nature,
national/international, sector. Advertiser, tender number and deadline are
"Reservé aux abonnés" (subscribers only), so buyer/deadline stay empty and the
url is the public search filtered to that bulletin number.

Leg 1: every notice in the date window (paged, ~40/page incl. two tables).
Leg 2: full-text keyword searches (all dates; rows before since dropped
locally, since text+date queries are very slow server-side). Full-text search
is itself slow (up to ~18 s) for uncached terms, so both legs share a budget.
"""
import html as _html
import re
import time
from urllib.parse import urlencode

from ..core import Candidate, PortalInfo, PortalResult, RunContext, get, parse_date

PORTAL = PortalInfo(key="baosem", name="BAOSEM (Algeria energy & mines bulletin)", region="Africa/MENA",
                    method="Public search form HTML (subscriber fields hidden)", min_rows=50,
                    url="https://www.baosem.com/appel-offre/last")

SEARCH = "https://www.baosem.com/appel-offre/all"
BUDGET_S = 100
TERMS = ["géophysique", "geophysical", "aéroporté", "aéromagnétique", "magnétométrie", "gravimétrie",
         "spectrométrie", "جيوفيزيائي"]


def _t(s):
    return re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def _parse(page):
    out = []
    for r in page.split('<tr class="row_appels">')[1:]:
        r = r.split('<div class="modal', 1)[0]
        g = lambda p: (lambda m: _t(m[1]) if m else "")(re.search(p, r, re.S))  # noqa: E731
        bolds = [_t(b) for b in re.findall(r'<b class="black-text">(.*?)(?:</b>|</li>)', r, re.S)]
        out.append(dict(no=g(r"N\W{1,3}\s*Baosem:\s*<strong[^>]*>(.*?)</strong>"), date=g(r"Du: <strong>(.*?)</strong>"),
                        ref=g(r"R.{1,8}f\s*Baosem:\s*<strong>(.*?)</strong>"),
                        title=bolds[0] if bolds else "",
                        nature=bolds[1] if len(bolds) > 1 else "", scope=bolds[2] if len(bolds) > 2 else "",
                        sector=g(r'<p class="blockquote-nk">\s*<b>(?!<span)(.*?)</b>')))
    return out


def fetch(ctx: RunContext) -> PortalResult:
    res = PortalResult(portal=PORTAL.key)
    base = {"date_debut": ctx.since.strftime("%d/%m/%Y"), "date_fin": ctx.today.strftime("%d/%m/%Y")}
    since = ctx.since.isoformat()
    seen = {}
    t0 = time.time()

    def run(params, max_pages, dated=True):
        for p in range(1, max_pages + 1):
            if time.time() - t0 > BUDGET_S:
                res.notes.append(f"time budget hit ({params.get('text_placard', 'all')} p{p})")
                return
            q = dict(base if dated else {}, **params, p1=p, p2=p)
            r = get(SEARCH, params=q, timeout=ctx.timeout)
            res.queries += 1
            if r.status_code != 200:
                res.errors.append(f"{params} p{p}: HTTP {r.status_code}")
                return
            rows = _parse(r.text)
            res.rows_seen += len(rows)
            for d in rows:
                pub = parse_date(d["date"])
                if pub and pub < since:
                    continue
                key = d["ref"] or f"{d['no']}|{d['title']}"
                if key in seen:
                    continue
                seen[key] = Candidate(
                    portal="baosem", ref=d["ref"], title=d["title"],
                    url=f"{SEARCH}?{urlencode({'baosem': d['no']})}" if d["no"] else PORTAL.url,
                    country="Algeria", published=pub,
                    description=" | ".join(x for x in [d["nature"], d["scope"], d["sector"]] if x),
                    notice_type=d["nature"],
                    extra={"bulletin_no": d["no"], "note": "advertiser/deadline reserved to subscribers"})
            last = max([int(x) for x in re.findall(r"[?&](?:amp;)?p[12]=(\d+)", r.text)] or [1])
            if not rows or p >= last:
                return

    try:
        run({}, 400)
        for term in TERMS:
            run({"text_placard": term}, 2, dated=False)  # text+date search is much slower; filter dates locally
    except Exception as e:  # noqa: BLE001
        res.errors.append(f"{type(e).__name__}: {e}")
    res.candidates = list(seen.values())
    return res
