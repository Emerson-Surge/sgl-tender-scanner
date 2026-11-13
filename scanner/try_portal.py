"""Test one adapter:  python3 -m scanner.try_portal <key> [days]
Prints status, row count, errors, and every row the matcher accepts."""
import datetime as dt, importlib, sys, time
from .core import RunContext
from .matcher import match
key = sys.argv[1]; days = int(sys.argv[2]) if len(sys.argv) > 2 else 30
mod = importlib.import_module(f"scanner.portals.{key}")
today = dt.date.today()
t = time.time()
r = mod.fetch(RunContext(since=today - dt.timedelta(days=days), today=today))
print(f"{mod.PORTAL.name}: status={r.status} rows={r.rows_seen} (min {mod.PORTAL.min_rows}) queries={r.queries} {time.time()-t:.0f}s")
for e in r.errors: print("  ERROR:", e[:300])
for n in r.notes: print("  note:", n[:300])
print("  sample rows:")
for c in r.candidates[:3]: print("   ", c.ref, c.published, c.deadline, c.country, "|", c.title[:100], "|", c.url[:100])
hits = [(c, match(c.title, c.description)) for c in r.candidates]
hits = [(c, m) for c, m in hits if m]
print(f"  matched {len(hits)}:")
for c, m in hits: print("   ", m["tier"], c.ref, c.published, c.deadline, "|", c.title[:110], "|", m["terms"][:4], "|", c.url[:110])
