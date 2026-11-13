"""Zambia ZPPA e-GP (ePPS platform). The full "Current Tenders" search
(/epps/prepareCurrentOpportunities.do) requires solving a CAPTCHA, so it is
NOT automated. What is public without a captcha:
  * the home page "Latest Tenders" block (10 newest notices, with date);
PARTIAL COVERAGE: only the 10 newest tenders at run time. Check the full list
by hand weekly (link in PORTAL.url). /epps/common/viewOpenedTenders.do is also
public but lists tenders already at bid opening, so it is not used.
"""
import html as _html
import re

from ..core import Candidate, PortalInfo, PortalResult, RunContext, get, parse_date

PORTAL = PortalInfo(key="zppa", name="Zambia ZPPA e-GP (latest tenders only)", region="Africa",
                    method="Public home page 'Latest Tenders' block (full list is captcha-gated)",
                    min_rows=5, url="https://eprocure.zppa.org.zm/epps/prepareCurrentOpportunities.do?currentType=cft")

BASE = "https://eprocure.zppa.org.zm"
ITEM = re.compile(r'<a href="(/epps/cft/prepareViewCfTWS\.do\?resourceId=(\d+))">\s*<span class="eventDate">\s*'
                  r'<span class="eDD">(\d+)</span>\s*<span class="eDM"\s*>(\w+)</span>\s*<span class="eDY">(\d+)</span>'
                  r'\s*</span>(.*?)</a>', re.S)


def fetch(ctx: RunContext) -> PortalResult:
    res = PortalResult(portal=PORTAL.key)
    try:
        r = get(BASE + "/epps/home.do", timeout=ctx.timeout)
        res.queries += 1
        if r.status_code != 200:
            res.errors.append(f"HTTP {r.status_code}")
            return res
        block = r.text.split("LatestTenders", 1)
        items = ITEM.findall(block[1] if len(block) > 1 else r.text)
        if not items:
            res.errors.append("Latest Tenders block not found (layout change?)")
        for href, rid, dd, mon, yy, title in items:
            res.rows_seen += 1
            pub = parse_date(f"{dd} {mon} 20{yy}")
            if pub and pub < ctx.since.isoformat():
                continue
            res.candidates.append(Candidate(
                portal="zppa", ref=rid, title=re.sub(r"\s+", " ", _html.unescape(title)).strip(),
                url=BASE + _html.unescape(href), country="Zambia", published=pub,
                notice_type="tender", language="en"))
        res.notes.append("partial coverage: home page shows only the 10 newest tenders; full list is captcha-gated")
    except Exception as e:  # noqa: BLE001
        res.errors.append(f"{type(e).__name__}: {e}")
    return res
