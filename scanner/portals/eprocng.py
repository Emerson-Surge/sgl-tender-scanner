"""Nigeria oil & gas: NipeX (Nigerian Petroleum Exchange, the NNPC / upstream
operator tendering platform) public "Current Opportunities" page:
https://nipexmain.nipex-ng.com/newsite/current-opportunities.php
Plain HTML cards (operator, product codes, title, advert PDF, deadline), no
login. Usually only a handful of open adverts. The upload timestamp in the PDF
filename (YYYYMMDD_...) is used as the publication date.

Not covered (see report): BPP publicprocurement.gov.ng (host unreachable from
here), nocopo.bpp.gov.ng (TLS error), bpp.gov.ng/advertisement (BPP's own
adverts only), NGSA (no tenders section), nnpcgroup.com (no tender list;
NNPC tenders go through NipeX).
"""
import html as _html
import re
from urllib.parse import urljoin

from ..core import Candidate, PortalInfo, PortalResult, RunContext, get, parse_date

PORTAL = PortalInfo(key="eprocng", name="Nigeria NipeX current opportunities (NNPC/upstream)", region="Africa",
                    method="Public HTML cards", min_rows=1,
                    url="https://nipexmain.nipex-ng.com/newsite/current-opportunities.php")

ORD = re.compile(r"(\d+)(st|nd|rd|th)")


def _t(s):
    return re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def fetch(ctx: RunContext) -> PortalResult:
    res = PortalResult(portal=PORTAL.key)
    try:
        r = get(PORTAL.url, timeout=ctx.timeout)
        res.queries += 1
        if r.status_code != 200:
            res.errors.append(f"HTTP {r.status_code}")
            return res
        cards = re.split(r'<div class="opp-card(?:\s[^"]*)?">', r.text)[1:]
        cards = [c for c in cards if 'class="opp-title"' in c]
        if '<div class="opp-grid' not in r.text:
            res.errors.append("opportunity grid not found (layout change?)")
        for c in cards:
            res.rows_seen += 1
            op = re.search(r'opp-operator-badge">.*?(?:<span>([^<]+)</span>|alt="([^"]+)")', c, re.S)
            codes = re.search(r'opp-product-code">\s*<a[^>]*>([^<]*)</a>', c)
            ti = re.search(r'<h3 class="opp-title"><a href="([^"]+)"[^>]*>(.*?)</a>', c, re.S)
            dl = re.search(r"Deadline:\s*<strong>([^<]+)</strong>", c)
            href = urljoin(PORTAL.url, _html.unescape(ti[1])) if ti else PORTAL.url
            fn = href.rsplit("/", 1)[-1]
            pub = parse_date(fn[:8]) if re.match(r"\d{8}_", fn) else ""
            if pub and pub < ctx.since.isoformat():
                continue
            buyer = (op[1] or op[2]).strip() if op else ""
            res.candidates.append(Candidate(
                portal="eprocng", ref=fn.rsplit(".", 1)[0][:120], title=_t(ti[2]) if ti else "", url=href,
                buyer=buyer, country="Nigeria", published=pub,
                deadline=parse_date(ORD.sub(r"\1", dl[1])) if dl else "",
                description=f"NipeX product codes: {codes[1].strip()}" if codes else "",
                notice_type="tender", language="en", extra={"product_codes": codes[1].strip() if codes else ""}))
    except Exception as e:  # noqa: BLE001
        res.errors.append(f"{type(e).__name__}: {e}")
    return res
