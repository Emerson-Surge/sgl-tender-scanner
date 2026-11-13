"""ControlBid: public mirror of open Petronect (Petrobras/Transpetro)
opportunities, plain HTML (controlbid.com.br/licitacoes/; robots.txt allows
/licitacoes; tested 13 Nov 2026).

The listing gives number, object (long ones cut with "…"), buyer and closing
date. Detail pages (/licitacoes/<number>) add the full object, start date,
location and item lines; they are fetched for numbers not yet in the local
cache (ctx.cache_dir/controlbid_details.json), truncated titles first, at most
DETAIL_CAP per run, 4 at a time. Start dates never change, so after the first
run only new notices cost a request. The "Encerradas recentemente" block
(closed notices) is skipped.
"""
import html as _html
import json
import re
from concurrent.futures import ThreadPoolExecutor

from ..core import Candidate, PortalInfo, PortalResult, RunContext, get, parse_date

PORTAL = PortalInfo(key="controlbid", name="ControlBid (Petronect mirror)", region="Americas",
                    method="Public HTML listing + detail pages", min_rows=100,
                    url="https://controlbid.com.br/licitacoes/")

BASE = "https://controlbid.com.br"
DETAIL_CAP = 400
ROW = re.compile(r'<li><a href="/licitacoes/(\d+)"><span class="mono">\d+</span>'
                 r'<span class="objeto">(.*?)</span><span class="meta">(.*?)</span></a></li>', re.S)


def _txt(s):
    return re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def _detail(num, timeout):
    r = get(f"{BASE}/licitacoes/{num}", timeout=timeout, retries=1)
    if r.status_code != 200:
        return {"error": f"HTTP {r.status_code}"}
    t = r.content.decode("utf-8", errors="replace")
    d = {}
    for m in re.finditer(r'<script type="application/ld\+json">(.*?)</script>', t, re.S):
        try:
            for g in json.loads(m.group(1)).get("@graph", []):
                for a in g.get("about") or []:
                    if a.get("description"):
                        d["title"] = a["description"]
        except Exception:  # noqa: BLE001
            pass
    body = _txt(t)
    m = re.search(r"In[íi]cio (\d{2}/\d{2}/\d{4})", body)
    d["start"] = parse_date(m[1]) if m else ""
    m = re.search(r"Encerramento (\d{2}/\d{2}/\d{4})", body)
    d["end"] = parse_date(m[1]) if m else ""
    m = re.search(r"Local (.*?) Itens e especifica", body)
    d["local"] = m[1].strip()[:200] if m else ""
    m = re.search(r"Itens e especifica[çc][ãa]o t[ée]cnica (.*?) Especifica[çc][ãa]o copiada", body)
    d["items"] = m[1].strip()[:2000] if m else ""
    return d


def fetch(ctx: RunContext) -> PortalResult:
    res = PortalResult(portal=PORTAL.key)
    try:
        r = get(f"{BASE}/licitacoes/", timeout=ctx.timeout)
        res.queries += 1
        if r.status_code != 200:
            res.errors.append(f"listing HTTP {r.status_code}")
            return res
        page = r.content.decode("utf-8", errors="replace")
    except Exception as e:  # noqa: BLE001
        res.errors.append(f"listing: {type(e).__name__}: {e}")
        return res
    cut = page.find("Encerradas recentemente")
    open_part = page[:cut] if cut > 0 else page
    rows = {}
    for num, obj, meta in ROW.findall(open_part):
        rows.setdefault(num, (_txt(obj), _txt(meta)))
    res.rows_seen = len(rows)
    if not rows:
        res.errors.append("no rows parsed (layout change?)")
        return res

    cache_file = ctx.cache_dir / "controlbid_details.json"
    try:
        cache = json.loads(cache_file.read_text()) if cache_file.exists() else {}
    except Exception:  # noqa: BLE001
        cache = {}
    todo = [n for n in rows if n not in cache]
    todo.sort(key=lambda n: not rows[n][0].endswith("…"))
    if len(todo) > DETAIL_CAP:
        res.notes.append(f"{len(todo) - DETAIL_CAP} detail pages deferred to next run")
        todo = todo[:DETAIL_CAP]
    if todo:
        with ThreadPoolExecutor(4) as pool:
            for n, d in zip(todo, pool.map(lambda n: _safe(n, ctx.timeout), todo)):
                res.queries += 1
                if "error" in d:
                    res.errors.append(f"detail {n}: {d['error']}")
                else:
                    cache[n] = d
        try:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            # keep only notices still listed, so the file stays small
            cache_file.write_text(json.dumps({n: v for n, v in cache.items() if n in rows}))
        except Exception as e:  # noqa: BLE001
            res.notes.append(f"cache not saved: {e}")

    since = ctx.since.isoformat()
    for num, (obj, meta) in rows.items():
        d = cache.get(num, {})
        pub = d.get("start", "")
        if pub and pub < since:
            continue
        buyer = meta.split("·")[0].strip()
        m = re.search(r"encerra (\d{2}/\d{2}/\d{4})", meta)
        res.candidates.append(Candidate(
            portal=PORTAL.key, ref=num, title=d.get("title") or obj, url=f"{BASE}/licitacoes/{num}",
            buyer=buyer, country="Brazil", published=pub,
            deadline=d.get("end") or (parse_date(m[1]) if m else ""),
            description=d.get("items", ""), notice_type="tender", language="pt",
            extra={"local": d.get("local", ""), "source": "Petronect"},
        ))
    return res


def _safe(n, timeout):
    try:
        return _detail(n, timeout)
    except Exception as e:  # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}"}
