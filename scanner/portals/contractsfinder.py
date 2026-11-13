"""UK Contracts Finder (below-threshold notices, e.g. BGS/UKRI) via the public
OCDS search API (keyless). Unlike FTS, the `stages=tender` filter here works
(checked 13 Nov 2026), so we page tender releases only via links.next."""
import time

from ..core import PortalInfo, PortalResult, RunContext
from .fts import paced_get, release_to_candidate

PORTAL = PortalInfo(key="contractsfinder", name="UK Contracts Finder", region="Europe",
                    method="Official OCDS search API (keyless), stages=tender", min_rows=50,
                    url="https://www.contractsfinder.service.gov.uk/Search")

API = "https://www.contractsfinder.service.gov.uk/Published/Notices/OCDS/Search"
BUDGET_S = 150


def fetch(ctx: RunContext) -> PortalResult:
    res = PortalResult(portal=PORTAL.key)
    t0 = time.time()
    seen = {}
    url = f"{API}?publishedFrom={ctx.since.isoformat()}T00:00:00&stages=tender&limit=100"
    try:
        while url:
            if time.time() - t0 > BUDGET_S:
                res.errors.append(f"time budget hit after {res.queries} pages")
                break
            r = paced_get(url, ctx, res, pause=1.0)
            res.queries += 1
            if r.status_code != 200:
                res.errors.append(f"HTTP {r.status_code}: {r.text[:200]}")
                break
            d = r.json()
            for x in d.get("releases") or []:
                res.rows_seen += 1
                ocid = x.get("ocid", "")
                # ocid = ocds-b5fd17-<notice uuid>
                nid = ocid.replace("ocds-b5fd17-", "")
                c = release_to_candidate(x, PORTAL.key, f"https://www.contractsfinder.service.gov.uk/Notice/{nid}")
                c.ref = nid or c.ref
                if ocid not in seen or c.published > seen[ocid].published:
                    seen[ocid] = c
            url = (d.get("links") or {}).get("next")
    except Exception as e:  # noqa: BLE001
        res.errors.append(f"{type(e).__name__}: {e}")
    res.candidates = list(seen.values())
    return res
