"""Iceland. Two public static listings of OPEN tenders (no API, no login):
  * utbodsvefur.is - the national "Útboðsvefur" (Fjársýslan/Ríkiskaup,
    municipalities, Landsvirkjun, Isavia...), one HTML table of every open
    tender (~75 on 13 Nov 2026): number, title, short description, buyer,
    type, deadline.
  * utbod.is (HogunNET site) "Útboð í gangi" list; it was empty ("Ekkert á
    skrá...") on 13 Nov 2026 but is parsed in case it gets entries.
Both list open tenders only, without a publication date, so ctx.since is not
applied (state handles repeats)."""
import html
import re

from ..core import Candidate, PortalInfo, PortalResult, RunContext, get, parse_date

PORTAL = PortalInfo(key="utbod", name="Útboðsvefur / Útboð.is (Iceland)", region="Europe",
                    method="Public open-tender listings (static HTML)", min_rows=20,
                    url="https://utbodsvefur.is/")

ROW = re.compile(r'<tr>\s*<td class="td-number">(.*?)</td>(.*?)</tr>', re.S)


def _txt(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def _utbodsvefur(ctx, res, out):
    r = get("https://utbodsvefur.is/", timeout=ctx.timeout)
    res.queries += 1
    if r.status_code != 200:
        res.errors.append(f"utbodsvefur HTTP {r.status_code}")
        return
    r.encoding = "utf-8"
    rows = ROW.findall(r.text)
    if not rows:
        res.errors.append("utbodsvefur: no table rows (layout change?)")
    for num, rest in rows:
        desc_cell = rest
        m = re.search(r'<a href="([^"]+)" title="([^"]*)"', desc_cell)
        spans = re.findall(r'<span class="hide-lt-lg">(.*?)</span>', desc_cell, re.S)
        tds = re.findall(r"<td>(.*?)</td>", rest, re.S)
        res.rows_seen += 1
        ref = _txt(num)
        url = m[1] if m else "https://utbodsvefur.is/"
        out[url] = Candidate(
            portal=PORTAL.key, ref=ref or url.rstrip("/").rsplit("/", 1)[-1],
            title=html.unescape(m[2]) if m else _txt(spans[0] if spans else ""),
            url=url, buyer=_txt(tds[0]) if tds else "", country="IS",
            deadline=parse_date(_txt(tds[2])) if len(tds) > 2 else "",
            description=_txt(spans[1]) if len(spans) > 1 else "",
            notice_type=_txt(tds[1]) if len(tds) > 1 else "", language="is",
        )


def _utbod_is(ctx, res, out):
    r = get("https://utbod.is/default.aspx?pageId=1", timeout=ctx.timeout)
    res.queries += 1
    if r.status_code != 200:
        res.errors.append(f"utbod.is HTTP {r.status_code}")
        return
    s = r.text
    i = s.find("Útboð í gangi")
    block = s[i:s.find("</div>", s.find("<div>", i) + 5) + 6] if i >= 0 else ""
    if "Ekkert á skrá" in s[i:i + 2000]:
        res.notes.append("utbod.is: no open tenders listed")
        return
    for href, text in re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', block, re.S):
        t = _txt(text)
        if not t:
            continue
        res.rows_seen += 1
        url = href if href.startswith("http") else "https://utbod.is/" + href.lstrip("/")
        out[url] = Candidate(portal=PORTAL.key, ref=url.rsplit("=", 1)[-1], title=t, url=url,
                             country="IS", language="is", buyer="", notice_type="open tender")


def fetch(ctx: RunContext) -> PortalResult:
    res = PortalResult(portal=PORTAL.key)
    out = {}
    for fn in (_utbodsvefur, _utbod_is):
        try:
            fn(ctx, res, out)
        except Exception as e:  # noqa: BLE001
            res.errors.append(f"{fn.__name__}: {type(e).__name__}: {e}")
    res.candidates = list(out.values())
    return res
