"""Write report.html (self-contained), report.md (chat/email summary) and candidates.xlsx."""
from __future__ import annotations

import html
from pathlib import Path

MANUAL_CHECKS = [
    ("AusTender (Australia)", "https://www.tenders.gov.au/", "CloudFront blocks automated access from this network; search 'geophysical', agency Geoscience Australia"),
    ("GeM (India)", "https://bidplus.gem.gov.in/all-bids", "connection reset for automated requests; search GSI / AMD bids"),
    ("Etimad (Saudi Arabia)", "https://tenders.etimad.sa/", "check SGS / MIM / Ma'aden if no adapter ran"),
]

SECTIONS = [
    ("new", "New: likely airborne", "Airborne signal, not seen before, not in the tracker. Verify each before it goes in the tracker."),
    ("review", "New: geophysics, no airborne signal (skim)", "Ground, lab, marine or equipment notices that hit geophysics terms. Usually out of scope; skim titles."),
    ("deadline_changed", "Deadline changes", "Notices already seen whose deadline moved."),
    ("possible_duplicate", "Possible re-tenders / duplicates", "Same title as an earlier notice under a different reference. Often a re-float."),
    ("awards", "Award notices (for the weekly award re-check)", "Matched award / adjudication records."),
    ("in_tracker", "Already in the tracker", "Matched, but the reference or URL is already in the tracker workbook."),
    ("drone_only", "Excluded: drone/UAV-only", "Scope rule excludes these; listed so nothing disappears silently."),
]

CSS = """
:root{--bg:#f7f7f5;--card:#fff;--ink:#1d2433;--mute:#5d6576;--line:#e3e4e8;--ok:#1f7a4d;--warn:#a66300;--fail:#b3261e;--acc:#1f3864}
@media (prefers-color-scheme:dark){:root{--bg:#14161b;--card:#1c1f26;--ink:#e7e9ee;--mute:#9aa1ae;--line:#2c313b;--ok:#5cc98f;--warn:#f0b35a;--fail:#ff8a80;--acc:#8fb0ff}}
body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 16px 64px}
h1{font-size:22px;margin:0 0 4px}h2{font-size:17px;margin:32px 0 6px;color:var(--acc)}
.sum{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin:12px 0}
.mute{color:var(--mute)}table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden}
th,td{text-align:left;padding:7px 9px;border-bottom:1px solid var(--line);vertical-align:top}th{font-size:12px;color:var(--mute);font-weight:600}
.OK{color:var(--ok);font-weight:600}.WARN{color:var(--warn);font-weight:600}.FAIL{color:var(--fail);font-weight:600}
.wrap{overflow-x:auto}a{color:var(--acc)}.tag{font-size:11px;border:1px solid var(--line);border-radius:4px;padding:0 4px;color:var(--mute)}
details{margin-top:6px}
"""


def _e(s):
    return html.escape(str(s or ""))


def _row(d):
    m = d.get("match") or {}
    mirrors = "".join(f' <a href="{_e(u)}">mirror</a>' for u in d.get("mirrors", []))
    note = d.get("status_note") or ""
    return (f"<tr><td><a href=\"{_e(d['url'])}\">{_e(d['title'][:220])}</a>{mirrors}"
            f"<div class=mute>{_e(d.get('buyer'))} {_e(note)}</div></td>"
            f"<td>{_e(d.get('country'))}</td><td>{_e(d.get('portal_name'))}<div class=mute>{_e(d.get('ref'))}</div></td>"
            f"<td>{_e(d.get('published'))}</td><td><b>{_e(d.get('deadline') or 'unverified')}</b></td>"
            f"<td><span class=tag>{_e(m.get('tier'))}</span> {_e(', '.join(m.get('terms', [])[:4]))}</td></tr>")


def write_reports(rec: dict, out: Path):
    b = rec["buckets"]
    p = rec["portals"]
    parts = [f"<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
             f"<title>SGL Tender Sweep</title><style>{CSS}</style></head><body><main>",
             f"<h1>SGL tender sweep, {rec['date']}</h1><div class=sum>{_e(rec['summary'])}</div>"]
    for key, title, blurb in SECTIONS:
        rows = b.get(key, [])
        if key in ("in_tracker", "drone_only", "review") and rows:
            parts.append(f"<h2>{title} ({len(rows)})</h2><details><summary class=mute>{blurb}</summary><div class=wrap><table>")
        else:
            parts.append(f"<h2>{title} ({len(rows)})</h2><p class=mute>{blurb}</p><div class=wrap><table>")
        parts.append("<tr><th>Notice</th><th>Country</th><th>Portal / ref</th><th>Published</th><th>Deadline</th><th>Why matched</th></tr>")
        parts += [_row(d) for d in rows] or ["<tr><td colspan=6 class=mute>None this run.</td></tr>"]
        parts.append("</table></div>" + ("</details>" if key in ("in_tracker", "drone_only", "review") and rows else ""))

    parts.append("<h2>Portal health</h2><p class=mute>A WARN or FAIL means that portal was not fully read this run. "
                 "Silence from a FAIL portal is not a quiet week.</p><div class=wrap><table>"
                 "<tr><th>Portal</th><th>Region</th><th>Status</th><th>Rows</th><th>Matched</th><th>Method</th><th>Problems</th></tr>")
    order = {"FAIL": 0, "WARN": 1, "OK": 2}
    for k, v in sorted(p.items(), key=lambda kv: (order[kv[1]["status"]], kv[1]["region"], kv[0])):
        parts.append(f"<tr><td><a href=\"{_e(v['url'])}\">{_e(v['name'])}</a></td><td>{_e(v['region'])}</td>"
                     f"<td class={v['status']}>{v['status']}</td><td>{v['rows_seen']}</td><td>{v['matched']}</td>"
                     f"<td class=mute>{_e(v['method'])}</td><td class=mute>{_e('; '.join(e.splitlines()[0] for e in v['errors'])[:300])}</td></tr>")
    parts.append("</table></div><h2>Manual checks this week</h2><p class=mute>Portals that block automated access. "
                 "Open them by hand.</p><div class=wrap><table><tr><th>Portal</th><th>What to check</th></tr>")
    for name, url, what in MANUAL_CHECKS:
        parts.append(f"<tr><td><a href=\"{_e(url)}\">{_e(name)}</a></td><td>{_e(what)}</td></tr>")
    parts.append(f"</table></div><p class=mute>Closed (deadline passed) matches dropped: {len(b.get('closed', []))}. "
                 f"Older than window with no deadline: {len(b.get('old', []))}. Generated {rec['ran_at_utc']} UTC.</p></main></body></html>")
    (out / "report.html").write_text("".join(parts))

    # markdown summary (chat / email body)
    md = [f"**{rec['summary']}**", ""]
    for key, title, _ in [x for x in SECTIONS if x[0] in ("new", "deadline_changed", "possible_duplicate", "awards")]:
        rows = b.get(key, [])
        if not rows:
            continue
        md.append(f"### {title} ({len(rows)})")
        for d in rows:
            md.append(f"- {d['title'][:160]} | {d.get('country') or '?'} | {d.get('portal_name')} {d.get('ref')} | "
                      f"deadline {d.get('deadline') or 'unverified'} | {d['url']}")
        md.append("")
    bad = [f"{v['name']} ({v['status']}: {v['errors'][0].splitlines()[0][:100] if v['errors'] else ''})"
           for v in p.values() if v["status"] != "OK"]
    if bad:
        md.append("### Portals not fully read")
        md += [f"- {x}" for x in bad]
    (out / "report.md").write_text("\n".join(md))

    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Candidates"
        hdr = ["Bucket", "Title", "Country", "Buyer", "Portal", "Ref", "Published", "Deadline", "Tier", "Terms", "Note", "URL"]
        ws.append(hdr)
        for key, _, _ in SECTIONS:
            for d in b.get(key, []):
                m = d.get("match") or {}
                ws.append([key, d["title"][:500], d.get("country"), d.get("buyer"), d.get("portal_name"), d.get("ref"),
                           d.get("published"), d.get("deadline") or "unverified", m.get("tier"),
                           ", ".join(m.get("terms", [])), d.get("status_note", ""), d["url"]])
        hs = wb.create_sheet("Portal health")
        hs.append(["Portal", "Region", "Status", "Rows", "Matched", "Method", "Problems"])
        for k, v in sorted(p.items()):
            hs.append([v["name"], v["region"], v["status"], v["rows_seen"], v["matched"], v["method"], "; ".join(v["errors"])[:500]])
        for s in (ws, hs):
            for c in s[1]:
                c.font = Font(bold=True, color="FFFFFFFF")
                c.fill = PatternFill("solid", fgColor="FF1F3864")
            s.freeze_panes = "A2"
            s.auto_filter.ref = s.dimensions
        wb.save(out / "candidates.xlsx")
    except Exception as e:  # noqa: BLE001
        (out / "xlsx_error.txt").write_text(repr(e))
