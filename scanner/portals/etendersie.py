"""Ireland eTenders (etenders.gov.ie, European Dynamics ePPS). The public
"latest contract notices" quick search needs no login:
  /epps/quickSearchAction.do?searchType=cftFTS&latest=true&T01_ps=100&d-3680175-p=N
HTML table, newest first; T01_ps=100 gives 100 rows/page (default 10). We page
until rows are older than ctx.since. Description = the info-icon tooltip."""
import html
import re

from ..core import Candidate, PortalInfo, PortalResult, RunContext, get, parse_date

PORTAL = PortalInfo(key="etendersie", name="eTenders (Ireland)", region="Europe",
                    method="Public notice listing (HTML, 100/page)", min_rows=60,
                    url="https://www.etenders.gov.ie/epps/quickSearchAction.do?searchType=cftFTS&latest=true")

BASE = "https://www.etenders.gov.ie"
LIST = BASE + "/epps/quickSearchAction.do?searchType=cftFTS&latest=true&T01_ps=100&d-3680175-p={page}"
ROW = re.compile(r"<tr[^>]*>\s*<td>\d+</td>(.*?)</tr>", re.S)
CELL = re.compile(r"<td[^>]*>(.*?)</td>", re.S)


def _txt(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def fetch(ctx: RunContext) -> PortalResult:
    res = PortalResult(portal=PORTAL.key)
    seen = {}
    since = ctx.since.isoformat()
    try:
        for page in range(1, 31):
            r = get(LIST.format(page=page), timeout=ctx.timeout)
            res.queries += 1
            if r.status_code != 200:
                res.errors.append(f"page {page} HTTP {r.status_code}")
                break
            rows = ROW.findall(r.text)
            if not rows:
                if page == 1:
                    res.errors.append("no table rows found (layout change?)")
                break
            older = 0
            for row in rows:
                cells = CELL.findall(row)
                if len(cells) < 8:
                    continue
                res.rows_seen += 1
                m = re.search(r'resourceId=(\d+)">(.*?)</a>', cells[0], re.S)
                rid = m[1] if m else _txt(cells[1])
                title = _txt(m[2]) if m else _txt(cells[0])
                tip = re.search(r"title='(.*?)'\s*/>", cells[3], re.S) or re.search(r'title="(.*?)"', cells[3], re.S)
                pub = parse_date(_txt(cells[4]))
                if pub and pub < since:
                    older += 1
                    continue
                seen[rid] = Candidate(
                    portal=PORTAL.key, ref=rid, title=title,
                    url=f"{BASE}/epps/cft/prepareViewCfTWS.do?resourceId={rid}",
                    buyer=_txt(cells[2]), country="IE", published=pub, deadline=parse_date(_txt(cells[5])),
                    description=html.unescape(tip[1])[:2000] if tip else "",
                    value=_txt(cells[10]) if len(cells) > 10 else "",
                    notice_type=f"{_txt(cells[6])} / {_txt(cells[7])}", language="en",
                )
            if older:
                break
    except Exception as e:  # noqa: BLE001
        res.errors.append(f"{type(e).__name__}: {e}")
    res.candidates = list(seen.values())
    return res
