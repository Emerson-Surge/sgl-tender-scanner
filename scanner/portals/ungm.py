"""UNGM (UN Global Marketplace) public notices. The public page
https://www.ungm.org/Public/Notice loads its result table from
POST /Public/Notice/Search (JSON body, anti-forgery token taken from the same
public page; no account). Page size is fixed at 15 server-side.

UNGM rate-limits (HTTP 429 after ~30 rapid requests), so a full crawl of a
week (~60+ pages) does not fit the time budget politely. We run server-side
keyword searches on Title and Description (published since ctx.since, open and
closed), paced at ~1.5 s per request, and return every row they return.
"""
import html as _html
import re
import time

from ..core import Candidate, PortalInfo, PortalResult, RunContext, get, parse_date, post

PORTAL = PortalInfo(key="ungm", name="UNGM (UN Global Marketplace)", region="Global/Donor",
                    method="Public notice search (page's JSON POST)", min_rows=10,
                    url="https://www.ungm.org/Public/Notice")

BASE = "https://www.ungm.org"
BUDGET_S = 100
PACE_S = 1.5
# Title search needs >= 5 chars. Substring search, so stems catch variants.
TERMS = ["airborne", "aeromagn", "geophys", "geofis", "géophys", "geolog", "géolog", "magnet",
         "gravi", "radiometr", "gamma", "electromagn", "lidar", "heliborne", "aerial survey",
         "aéroport", "spectrom", "levantamento"]

ROW_RE = re.compile(r'data-noticeid="(\d+)" class="tableRow')


def _txt(s):
    return re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def _parse(page_html):
    out = []
    parts = ROW_RE.split(page_html)
    # parts: [pre, id1, body1, id2, body2, ...]
    for i in range(1, len(parts) - 1, 2):
        nid, body = parts[i], parts[i + 1]
        title = re.search(r'ungm-title--small">(.*?)</span>', body, re.S)
        cells = re.findall(r'<div role="cell" class="tableCell([^"]*)"[^>]*>(.*?)</div>', body, re.S)
        plain = [(cls.strip(), _txt(c)) for cls, c in cells]
        dl = next((t for cls, t in plain if "deadline" in cls), "")
        agency = next((t for cls, t in plain if "resultAgency" in cls), "")
        ref = next((t for cls, t in plain if cls == "resultInfo1"), "")
        bare = [t for cls, t in plain if cls == ""]
        # bare cells in order: published, notice type, country
        pub = bare[0] if len(bare) > 0 else ""
        ntype = bare[1] if len(bare) > 1 else ""
        country = bare[2] if len(bare) > 2 else ""
        out.append(dict(id=nid, title=_txt(title[1]) if title else "", deadline=dl, published=pub,
                        agency=agency, ntype=ntype, ref=ref, country=country))
    return out


def _cand(d):
    return Candidate(
        portal="ungm", ref=d["id"], title=d["title"], url=f"{BASE}/Public/Notice/{d['id']}",
        buyer=d["agency"], country=d["country"], published=parse_date(d["published"]),
        deadline=parse_date(d["deadline"]), notice_type=d["ntype"],
        extra={"agency_ref": d["ref"]},
    )


def fetch(ctx: RunContext) -> PortalResult:
    res = PortalResult(portal=PORTAL.key)
    seen = {}
    t0 = time.time()
    try:
        r = get(f"{BASE}/Public/Notice", timeout=ctx.timeout)
        res.queries += 1
        if r.status_code != 200:
            res.errors.append(f"notice page HTTP {r.status_code}")
            return res
        m = re.search(r'name="__RequestVerificationToken"[^>]*value="([^"]+)"', r.text)
        hdr = {"X-Requested-With": "XMLHttpRequest", "Referer": f"{BASE}/Public/Notice"}
        if m:
            hdr["RequestVerificationToken"] = m[1]
        since_s = ctx.since.strftime("%d-%b-%Y")
        base = dict(PageIndex=0, PageSize=15, Title="", Description="", Reference="", PublishedFrom=since_s,
                    PublishedTo="", DeadlineFrom="", DeadlineTo="", Countries=[], Agencies=[], UNSPSCs=[],
                    NoticeTypes=[], SortField="DatePublished", SortAscending=False, isPicker=False,
                    IsSustainable=False, IsActive=False, NoticeDisplayType=None,
                    NoticeSearchTotalLabelId="noticeSearchTotal", TypeOfCompetitions=[])

        def run(extra, max_pages):
            for page in range(max_pages):
                if time.time() - t0 > BUDGET_S:
                    res.notes.append(f"time budget hit before {extra} p{page}")
                    return
                time.sleep(PACE_S)
                x = post(f"{BASE}/Public/Notice/Search", json=dict(base, PageIndex=page, **extra),
                         headers=hdr, timeout=ctx.timeout)
                res.queries += 1
                if x.status_code != 200:
                    res.errors.append(f"search {extra} p{page}: HTTP {x.status_code}")
                    return
                rows = _parse(x.text)
                res.rows_seen += len(rows)
                for d in rows:
                    c = _cand(d)
                    seen.setdefault(c.ref, c)
                if len(rows) < 15:
                    return

        for term in TERMS:
            for fld in ("Title", "Description"):
                run({fld: term}, 6)
    except Exception as e:  # noqa: BLE001
        res.errors.append(f"{type(e).__name__}: {e}")
    res.candidates = list(seen.values())
    return res
