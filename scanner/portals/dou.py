"""Diário Oficial da União, Seção 3 (contracts and tenders) via the public
reader page in.gov.br/leiturajornal (tested 13 Nov 2026). Each day's page
embeds a JSON "jsonArray" with every article of the section (title, type,
issuing body hierarchy and the first ~400 characters of the text).

One plain GET per weekday in ctx.since..today (3 in parallel) (~2,000-3,000 articles/day).
Homologation/award/contract-extract articles get notice_type="award".
"""
import datetime as dt
import html as _html
import json
import re
from concurrent.futures import ThreadPoolExecutor

from ..core import Candidate, PortalInfo, PortalResult, RunContext, get, parse_date

PORTAL = PortalInfo(key="dou", name="Diário Oficial da União - Seção 3 (Brazil)", region="Americas",
                    method="Public reader page, embedded jsonArray (one GET per weekday)", min_rows=1000,
                    url="https://www.in.gov.br/leiturajornal?secao=do3")

READER = "https://www.in.gov.br/leiturajornal?data={d}&secao=do3"
ARTICLE = "https://www.in.gov.br/web/dou/-/{slug}"
PARAMS = re.compile(r'<script id="(?:[^"]*_)?params" type="application/json">\s*(\{.*?\})\s*</script>', re.S)
AWARD = re.compile(r"homologa|adjudica|resultado|extrato|ratifica", re.I)


def _day(d, ctx, res):
    r = get(READER.format(d=d.strftime("%d-%m-%Y")), timeout=ctx.timeout)
    res.queries += 1
    if r.status_code != 200:
        res.errors.append(f"{d}: HTTP {r.status_code}")
        return []
    page = r.content.decode("utf-8", errors="replace")
    arts = []
    for m in PARAMS.finditer(page):
        try:
            arts += json.loads(m.group(1)).get("jsonArray") or []
        except ValueError as e:
            res.errors.append(f"{d}: bad jsonArray: {e}")
    return arts


def fetch(ctx: RunContext) -> PortalResult:
    res = PortalResult(portal=PORTAL.key)
    seen = {}
    days = [ctx.since + dt.timedelta(days=i) for i in range((ctx.today - ctx.since).days + 1)]
    days = [d for d in days if d.weekday() < 5]

    def safe_day(d):
        try:
            return _day(d, ctx, res)
        except Exception as e:  # noqa: BLE001
            res.errors.append(f"{d}: {type(e).__name__}: {e}")
            return []

    with ThreadPoolExecutor(3) as pool:  # pages are 2-3 MB and can take ~8 s each
        for d, arts in zip(days, pool.map(safe_day, days)):
            res.rows_seen += len(arts)
            for a in arts:
                try:
                    slug = a.get("urlTitle") or ""
                    art_type = a.get("artType") or ""
                    title = _html.unescape(a.get("title") or art_type)
                    content = _html.unescape(re.sub(r"<[^>]+>", " ", a.get("content") or "")).strip()
                    hier = a.get("hierarchyList") or []
                    seen.setdefault(slug or f"{d}:{a.get('pubOrder')}", Candidate(
                        portal=PORTAL.key, ref=slug, title=f"{title} - {hier[-1]}" if hier else title,
                        url=ARTICLE.format(slug=slug) if slug else READER.format(d=d.strftime("%d-%m-%Y")),
                        buyer=a.get("hierarchyStr", ""), country="Brazil",
                        published=parse_date(a.get("pubDate")) or d.isoformat(),
                        description=content[:1500],
                        notice_type="award" if AWARD.search(art_type) else "tender",
                        language="pt",
                        extra={"art_type": art_type, "edition": a.get("editionNumber", ""),
                               "page": a.get("numberPage", "")},
                    ))
                except Exception as e:  # noqa: BLE001
                    res.errors.append(f"{d} article: {type(e).__name__}: {e}")
    res.candidates = list(seen.values())
    return res
