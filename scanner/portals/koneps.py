"""Korea KONEPS (나라장터) bid notices via the official data.go.kr Open API
(조달청 입찰공고정보서비스, BidPublicInfoService, PPS search operations).

Needs a free data.go.kr service key in env KONEPS_API_KEY (either the
"Decoding" key or the URL-encoded "Encoding" key). Without it, fetch returns
errors=["KONEPS_API_KEY not set"] and makes no calls. Endpoint path checked
13 Nov 2026 (an unregistered key gets SERVICE_KEY_IS_NOT_REGISTERED_ERROR;
the older BidPublicInfoService04 path is retired). Not run end-to-end here for
lack of a key: confirm field names on first keyed run.

Keyword search on the notice name (bidNtceNm) over service (용역) and goods
(물품) notices published since ctx.since, in <=30-day windows.
"""
import datetime as dt
import os
from urllib.parse import urlencode

from ..core import Candidate, PortalInfo, PortalResult, RunContext, get, parse_date

PORTAL = PortalInfo(key="koneps", name="KONEPS (Korea, data.go.kr)", region="Asia-Pacific",
                    method="Official data.go.kr Open API (key in KONEPS_API_KEY)", min_rows=1,
                    url="https://www.g2b.go.kr/")

API = "https://apis.data.go.kr/1230000/ad/BidPublicInfoService/"
OPS = {"service": "getBidPblancListInfoServcPPSSrch", "goods": "getBidPblancListInfoThngPPSSrch"}
KEYWORDS = ["물리탐사", "지구물리", "항공자력", "자력탐사", "항공물리", "중력탐사", "방사능탐사", "감마선",
            "전자탐사", "항공탐사", "항공측량", "라이다", "LiDAR", "자력계", "광물자원", "광물탐사", "헬기"]
ROWS = 100


def _url(op, key, params):
    q = urlencode(params)
    # an "Encoding" key is already percent-encoded: append it verbatim
    k = key if "%" in key else urlencode({"serviceKey": key})[len("serviceKey="):]
    return f"{API}{op}?serviceKey={k}&{q}"


def _items(data):
    body = (data.get("response") or {}).get("body") or {}
    items = body.get("items") or []
    if isinstance(items, dict):
        items = items.get("item") or []
    if isinstance(items, dict):
        items = [items]
    return items, int(body.get("totalCount") or 0)


def fetch(ctx: RunContext) -> PortalResult:
    res = PortalResult(portal=PORTAL.key)
    key = os.environ.get("KONEPS_API_KEY", "").strip()
    if not key:
        res.errors.append("KONEPS_API_KEY not set")
        return res
    seen = {}
    windows, start = [], ctx.since
    while start <= ctx.today:
        end = min(start + dt.timedelta(days=29), ctx.today)
        windows.append((start, end))
        start = end + dt.timedelta(days=1)
    for kind, op in OPS.items():
        for kw in KEYWORDS:
            for a, b in windows:
                page = 1
                while page <= 5:
                    params = {"numOfRows": ROWS, "pageNo": page, "type": "json", "inqryDiv": 1,
                              "inqryBgnDt": a.strftime("%Y%m%d") + "0000", "inqryEndDt": b.strftime("%Y%m%d") + "2359",
                              "bidNtceNm": kw}
                    try:
                        r = get(_url(op, key, params), timeout=ctx.timeout)
                        res.queries += 1
                        if r.status_code != 200:
                            res.errors.append(f"{kind} '{kw}': HTTP {r.status_code}: {r.text[:200]}")
                            break
                        try:
                            data = r.json()
                        except ValueError:
                            res.errors.append(f"{kind} '{kw}': non-JSON reply: {r.text[:200]}")
                            break
                        header = (data.get("response") or {}).get("header") or {}
                        if header.get("resultCode") not in (None, "00"):
                            res.errors.append(f"{kind} '{kw}': {header.get('resultCode')} {header.get('resultMsg')}")
                            break
                        items, total = _items(data)
                    except Exception as e:  # noqa: BLE001
                        res.errors.append(f"{kind} '{kw}': {type(e).__name__}: {e}")
                        break
                    for it in items:
                        res.rows_seen += 1
                        no, ordn = it.get("bidNtceNo", ""), it.get("bidNtceOrd", "")
                        ref = f"{no}-{ordn}" if ordn else no
                        if ref in seen:
                            continue
                        price = it.get("presmptPrce") or it.get("asignBdgtAmt") or ""
                        seen[ref] = Candidate(
                            portal=PORTAL.key, ref=ref, title=it.get("bidNtceNm", ""),
                            url=it.get("bidNtceDtlUrl") or it.get("bidNtceUrl") or PORTAL.url,
                            buyer=it.get("dminsttNm") or it.get("ntceInsttNm", ""), country="Korea",
                            published=parse_date(it.get("bidNtceDt") or it.get("rgstDt")),
                            deadline=parse_date(it.get("bidClseDt")), value=f"{price} KRW" if price else "",
                            notice_type=f"{kind}: {it.get('ntceKindNm', '')}".strip(": "), language="ko",
                            extra={"keyword": kw, "contract_method": it.get("cntrctCnclsMthdNm", "")},
                        )
                    if page * ROWS >= total or not items:
                        break
                    page += 1
    res.candidates = list(seen.values())
    return res
