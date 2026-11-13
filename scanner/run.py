"""Weekly sweep runner.

    python3 -m scanner.run                 # normal weekly run
    python3 -m scanner.run --portals ted,wb
    python3 -m scanner.run --since-days 30 # override window
    python3 -m scanner.run --dry-run       # don't update state

Window: per portal, from its last successful run minus 2 days of overlap
(default 14 days on first run, capped at 60), so a failed Monday is swept
again next time instead of being lost.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as dt
import importlib
import json
import pkgutil
import time
import traceback
from pathlib import Path

from . import portals as portals_pkg
from .core import ROOT, PortalResult, RunContext
from .matcher import match
from .state import State

DEFAULT_DAYS = 14
MAX_DAYS = 60
OVERLAP = 2


def discover():
    mods = {}
    for m in pkgutil.iter_modules(portals_pkg.__path__):
        if m.name.startswith("_"):
            continue
        mod = importlib.import_module(f"{portals_pkg.__name__}.{m.name}")
        if hasattr(mod, "PORTAL") and hasattr(mod, "fetch"):
            mods[mod.PORTAL.key] = mod
    return mods


def run_portal(mod, ctx):
    t0 = time.time()
    try:
        res = mod.fetch(ctx)
    except Exception as e:  # adapter bug: never kill the whole run
        res = PortalResult(portal=mod.PORTAL.key, errors=[f"adapter crashed: {e!r}",
                                                          traceback.format_exc()[-600:]])
    res.seconds = round(time.time() - t0, 1)
    if res.rows_seen < mod.PORTAL.min_rows and not res.errors:
        res.errors.append(f"only {res.rows_seen} rows (expected >= {mod.PORTAL.min_rows}): "
                          "page layout may have changed or portal is empty")
    return res


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--portals", default="")
    ap.add_argument("--skip", default="")
    ap.add_argument("--since-days", type=int, default=0)
    ap.add_argument("--today", default="")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--out", default="")
    a = ap.parse_args(argv)

    today = dt.date.fromisoformat(a.today) if a.today else dt.date.today()
    state = State()
    mods = discover()
    if a.portals:
        mods = {k: v for k, v in mods.items() if k in a.portals.split(",")}
    for k in filter(None, a.skip.split(",")):
        mods.pop(k, None)

    def window(key):
        if a.since_days:
            return today - dt.timedelta(days=a.since_days)
        last = state.last_success(key)
        since = (last - dt.timedelta(days=OVERLAP)) if last else today - dt.timedelta(days=DEFAULT_DAYS)
        return max(since, today - dt.timedelta(days=MAX_DAYS))

    results = {}
    print(f"SGL sweep {today}: {len(mods)} portals", flush=True)
    with cf.ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = {}
        for key, mod in mods.items():
            ctx = RunContext(since=window(key), today=today)
            futs[ex.submit(run_portal, mod, ctx)] = (key, ctx)
        for f in cf.as_completed(futs):
            key, ctx = futs[f]
            res = f.result()
            res.notes.insert(0, f"window from {ctx.since}")
            results[key] = res
            print(f"  {res.status:4} {key:16} rows={res.rows_seen:<5} q={res.queries:<3} {res.seconds:>5}s "
                  f"{'; '.join(e.splitlines()[0][:90] for e in res.errors[:2])}", flush=True)

    buckets = {k: [] for k in ("new", "review", "deadline_changed", "possible_duplicate", "awards",
                               "drone_only", "in_tracker", "seen", "closed", "old")}
    cross = {}
    for key, res in results.items():
        since = window(key)
        for c in res.candidates:
            m = match(c.title, c.description)
            if not m:
                continue
            c.match = m
            d = c.to_dict()
            d["portal_name"] = mods[key].PORTAL.name
            if c.deadline and c.deadline < today.isoformat():
                buckets["closed"].append(d); continue
            if c.published and c.published < (since - dt.timedelta(days=1)).isoformat() and not c.deadline:
                buckets["old"].append(d); continue
            if "award" in (c.notice_type or "").lower() or "adjudic" in (c.notice_type or "").lower():
                buckets["awards"].append(d); continue
            if m["drone_only"]:
                buckets["drone_only"].append(d); continue
            status, note = state.classify(c)
            d["status_note"] = note
            # cross-portal mirror merge within this run (same normalised title + deadline)
            from .state import title_key
            ck = (title_key(c.title), c.deadline)
            if status in ("new", "possible_duplicate") and ck in cross and len(ck[0]) > 20:
                cross[ck].setdefault("mirrors", []).append(c.url); continue
            if status in ("new", "possible_duplicate"):
                cross[ck] = d
            if status == "new" and not (m["airborne"] and not m["negative_hints"]):
                status = "review"
            buckets[status].append(d)
            if not a.dry_run:
                state.remember(c, today)

    for b in buckets.values():
        b.sort(key=lambda d: (-d["match"]["score"], d.get("deadline") or "9999"))

    n_ok = sum(r.status == "OK" for r in results.values())
    n_warn = sum(r.status == "WARN" for r in results.values())
    n_fail = sum(r.status == "FAIL" for r in results.values())
    summary = (f"SGL sweep {today}: portals {n_ok} OK / {n_warn} warn / {n_fail} failed of {len(results)}; "
               f"rows read {sum(r.rows_seen for r in results.values())}; "
               f"NEW likely-airborne {len(buckets['new'])}, geophysics-review {len(buckets['review'])}, deadline changes {len(buckets['deadline_changed'])}, "
               f"possible re-tenders {len(buckets['possible_duplicate'])}, awards {len(buckets['awards'])}, "
               f"already tracked {len(buckets['in_tracker'])}, drone-only excluded {len(buckets['drone_only'])}")
    record = {
        "date": today.isoformat(), "ran_at_utc": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "summary": summary,
        "portals": {k: {"name": mods[k].PORTAL.name, "region": mods[k].PORTAL.region,
                        "method": mods[k].PORTAL.method, "url": mods[k].PORTAL.url,
                        "status": r.status, "rows_seen": r.rows_seen, "min_rows": mods[k].PORTAL.min_rows,
                        "queries": r.queries, "matched": sum(1 for c in r.candidates if c.match),
                        "errors": [e[:400] for e in r.errors], "notes": r.notes, "seconds": r.seconds}
                    for k, r in sorted(results.items())},
        "buckets": buckets,
    }
    out = Path(a.out) if a.out else ROOT / "runs" / today.isoformat()
    out.mkdir(parents=True, exist_ok=True)
    (out / "sweep.json").write_text(json.dumps(record, ensure_ascii=False, indent=1, default=str))
    from .report import write_reports
    write_reports(record, out)
    if not a.dry_run:
        slim = {k: v for k, v in record.items() if k != "buckets"}
        slim["counts"] = {k: len(v) for k, v in buckets.items()}
        state.save(slim)
    print(summary)
    print(f"Report: {out / 'report.html'}")
    return record


if __name__ == "__main__":
    main()
