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

    write_xlsx(rec, out)


COUNTRY = {"GR": "Greece", "FR": "France", "NL": "Netherlands", "DEU": "Germany", "DE": "Germany", "SWE": "Sweden",
           "FIN": "Finland", "FI": "Finland", "BEL": "Belgium", "PL": "Poland", "DK": "Denmark", "ESP": "Spain",
           "FRA": "France", "GRC": "Greece", "POL": "Poland", "NLD": "Netherlands", "DNK": "Denmark", "NOR": "Norway",
           "IRL": "Ireland", "ITA": "Italy", "PRT": "Portugal", "AUT": "Austria", "CZE": "Czechia", "ROU": "Romania",
           "GBR": "United Kingdom", "UK": "United Kingdom", "CHE": "Switzerland", "BGR": "Bulgaria", "EST": "Estonia",
           "LTU": "Lithuania", "LVA": "Latvia", "HUN": "Hungary", "SVK": "Slovakia", "SVN": "Slovenia", "HRV": "Croatia"}
WHY = {"strong": "Geophysical survey wording",
       "combo": "Airborne wording plus geophysics wording",
       "licence": "Data licence plus geophysics wording"}
STATUS_EN = {
    "new": "New - likely airborne",
    "review": "New - geophysics but not airborne (skim)",
    "deadline_changed": "Deadline changed",
    "possible_duplicate": "Possible re-tender or copy",
    "awards": "Award (contract already given)",
    "in_tracker": "Already in tracker",
    "drone_only": "Excluded - drone only",
}

NAME_EN = {"burkina": "Burkina Faso daily public procurement bulletin (DGCMEF)",
           "dou": "Brazil Federal Official Gazette, Section 3 (DOU)",
           "mercadopublico": "Chile public procurement portal (Mercado Publico)",
           "comprasmx": "Mexico federal procurement portal (ComprasMX)",
           "alertalicitacao": "Alerta Licitacao (Brazil tender aggregator)",
           "eshdhs": "Greece central procurement register (KIMDIS)",
           "baosem": "BAOSEM (Algeria energy and mining tender bulletin)",
           "boamp": "BOAMP (France official tender bulletin)",
           "ezamowienia": "e-Zamowienia (Poland public procurement board)",
           "udbud": "udbud.dk (Denmark public tenders)",
           "hilma": "Hilma (Finland public tenders)",
           "doffin": "Doffin (Norway public tenders)",
           "tenderned": "TenderNed (Netherlands public tenders)",
           "placsp": "Spain public sector procurement platform (PLACSP)",
           "utbod": "Utbod (Iceland public tenders)",
           "nen": "NEN (Czech national e-procurement)",
           "secop": "SECOP II (Colombia public procurement)",
           "pncp": "PNCP (Brazil national procurement portal)"}


def _method_en(m):
    m = (m or "").lower()
    if "pdf" in m:
        return "Published PDF bulletins"
    if "csv" in m or "open-data" in m or "open data" in m:
        return "Official open-data file"
    if "headless" in m or "render" in m:
        return "Public website, read with a browser"
    if "api" in m or "json" in m or "graphql" in m or "ocds" in m or "atom" in m or "socrata" in m or "ckan" in m:
        return "Official or public data feed"
    return "Public website listing"


def _problem_en(errors):
    import re
    out = []
    for e in errors:
        e1 = e.splitlines()[0]
        if "not set" in e1:
            out.append("Needs a free API key or account token that has not been added yet")
        elif m := re.search(r"only (\d+) rows \(expected >= (\d+)\)", e1):
            out.append(f"Only {m[1]} notices came back (normally at least {m[2]}). The site may have changed "
                       "or had a quiet week; check by hand")
        elif "HTTP 202" in e1:
            out.append("The site answered with a holding page instead of results (likely bot protection); "
                       "check it by hand")
        elif "HTTP 5" in e1 or "Timeout" in e1 or "timed out" in e1:
            out.append("The site was down or too slow on some days, so those days were not read")
        elif "budget" in e1:
            out.append("Ran out of time; the oldest days in the window were not read")
        elif "HTTP 429" in e1 or "rate limit" in e1:
            out.append("The site limited how many requests it would answer; part of the week was not read")
        elif "HTTP 40" in e1:
            out.append("The site refused the request; check it by hand")
        elif "crashed" in e1:
            out.append("Scanner error on this portal (needs a fix)")
        else:
            out.append(e1[:160])
    seen, res = set(), []
    for x in out:
        if x not in seen:
            seen.add(x); res.append(x)
    return ". ".join(res)


def _date(iso):
    import datetime as dt
    try:
        return dt.date.fromisoformat(iso).strftime("%d %b %Y")
    except Exception:  # noqa: BLE001
        return iso or ""


def write_xlsx(rec: dict, out: Path):
    """Review workbook, curated like a tracker.

    Leads tab: only what deserves attention this week -
      1. new tenders that QUALIFY or need a CHECK (or are airborne and not yet verified),
      2. open tracker items and anything in the tracker closing within 45 days, with this week's update,
      3. airborne-geophysics award intel.
    Filtered out tab: every other match with the reason it was dropped (audit only).
    Portal health tab: one row per portal in plain English.

    English titles/verdicts come from runs/<date>/translations.json and tracker notes from
    runs/<date>/tracker_updates.json; the weekly session writes both."""
    import datetime as dt
    import json
    import math
    import openpyxl
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from .state import TRACKER_REFS

    def load(name):
        f = out / name
        return json.loads(f.read_text()) if f.exists() else {}

    tr, upd = load("translations.json"), load("tracker_updates.json")
    tracker = json.loads(TRACKER_REFS.read_text()).get("rows", []) if TRACKER_REFS.exists() else []
    b, p = rec["buckets"], rec["portals"]
    today = dt.date.fromisoformat(rec["date"])

    leads_new, intel, filtered = [], [], []
    for key in ["new", "deadline_changed", "possible_duplicate", "awards", "review", "in_tracker", "drone_only"]:
        for d in b.get(key, []):
            t = tr.get(f"{d['portal']}:{d['ref']}", {})
            v = (t.get("verdict") or "").strip()
            vu = v.upper()
            row = {"d": d, "t": t, "key": key, "verdict": v or "Not yet verified"}
            if vu.startswith(("QUALIFIES", "CHECK")):
                leads_new.append(row)
            elif vu.startswith("AWARD"):
                intel.append(row)
            elif not v and key in ("new", "deadline_changed") and (d.get("match") or {}).get("airborne"):
                leads_new.append(row)
            elif not v and key == "awards" and (d.get("match") or {}).get("airborne"):
                intel.append(row)
            else:
                filtered.append(row)

    def soon(r):
        if r.get("status") == "Open":
            return True
        if r.get("deadline"):
            try:
                return 0 <= (dt.date.fromisoformat(r["deadline"]) - today).days <= 45
            except ValueError:
                return False
        return False
    tracked = [r for r in tracker if soon(r) or any(r["opportunity"].startswith(k[:40]) for k in upd)]

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Leads"
    W = [("Section", 20), ("Opportunity", 56), ("Country", 16), ("Buyer", 28), ("Deadline", 14),
         ("Verdict / this week's update", 58), ("Found on", 20), ("Link", 13)]
    ws.append([c for c, _ in W])
    SEC = {"new": "FFC6EFCE", "tracked": "FFDDEBF7", "intel": "FFFFF2CC", "none": "FFF2F2F2"}

    def add(sheet, values, fill, url=None, link_col=None):
        sheet.append(values)
        r = sheet.max_row
        for c in sheet[r]:
            c.fill = PatternFill("solid", fgColor=fill)
        if url and link_col:
            c = sheet.cell(r, link_col)
            c.value, c.hyperlink = "Open notice", url
            c.font = Font(name="Calibri", size=11, color="FF1F4E9A", underline="single")

    def country(d):
        return COUNTRY.get((d.get("country") or "").upper(), d.get("country") or "")

    if leads_new:
        for x in leads_new:
            d, t = x["d"], x["t"]
            add(ws, ["New tender", t.get("title_en") or d["title"], country(d), t.get("buyer_en") or d.get("buyer") or "Not stated",
                     _date(d.get("deadline")) or "Not stated", x["verdict"], d.get("portal_name"), ""], SEC["new"], d["url"], 8)
    else:
        add(ws, ["New tender", "No new qualifying tenders this week", "", "", "", "All matches were checked; see the Filtered out tab for the reasons.", "", ""], SEC["none"])
    for r in tracked:
        note = next((v for k, v in upd.items() if r["opportunity"].startswith(k[:40])), "")
        star = "Priority: " if "★" in str(r.get("priority")) else ""
        dl = _date(r["deadline"]) if r.get("deadline") else (r.get("timing") or "")[:60]
        src = (r.get("source") or "").split(";")[0].strip()
        add(ws, [f"Tracker ({r.get('status')})", star + str(r["opportunity"]), r.get("country") or "", "", dl,
                 note or "No change found by the scan this week", "Your tracker", ""], SEC["tracked"],
            src if src.startswith("http") else None, 8)
    for x in intel:
        d, t = x["d"], x["t"]
        add(ws, ["Market intel (award)", t.get("title_en") or d["title"], country(d), t.get("buyer_en") or d.get("buyer") or "Not stated",
                 "Awarded", x["verdict"], d.get("portal_name"), ""], SEC["intel"], d["url"], 8)

    fs = wb.create_sheet("Filtered out")
    FW = [("Reason it was dropped", 60), ("Title (English)", 60), ("Country", 16), ("Deadline", 14),
          ("Found on", 20), ("Link", 13)]
    fs.append([c for c, _ in FW])
    for x in filtered:
        d, t = x["d"], x["t"]
        reason = x["verdict"] if x["verdict"] != "Not yet verified" else STATUS_EN.get(x["key"], x["key"])
        add(fs, [reason, t.get("title_en") or d["title"], country(d), _date(d.get("deadline")) or "Not stated",
                 d.get("portal_name"), ""], "FFFFFFFF", d["url"], 6)

    hs = wb.create_sheet("Portal health")
    HW = [("Portal", 34), ("Region", 16), ("Status", 10), ("Notices read", 12), ("Matched", 10),
          ("How it is read", 32), ("Problem (if any)", 70)]
    hs.append([c for c, _ in HW])
    rank = {"FAIL": 0, "WARN": 1, "OK": 2}
    for k, v in sorted(p.items(), key=lambda kv: (rank[kv[1]["status"]], kv[1]["region"], kv[1]["name"])):
        fill = {"FAIL": "FFFCE4D6", "WARN": "FFFFF2CC", "OK": "FFFFFFFF"}[v["status"]]
        add(hs, [NAME_EN.get(k, v["name"]), v["region"], {"OK": "OK", "WARN": "Partial", "FAIL": "Not read"}[v["status"]],
                 v["rows_seen"], v["matched"], _method_en(v["method"]), _problem_en(v["errors"]) or "None"], fill)

    thin = Side(style="thin", color="FFBFBFBF")
    for sheet, spec in ((ws, W), (fs, FW), (hs, HW)):
        for i, (_, w) in enumerate(spec, 1):
            sheet.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w
        for row in sheet.iter_rows():
            lines = 1
            for i, c in enumerate(row):
                c.alignment = Alignment(wrap_text=True, vertical="top")
                c.border = Border(top=thin, bottom=thin, left=thin, right=thin)
                if c.row > 1 and not c.hyperlink:
                    c.font = Font(name="Calibri", size=11, bold=(sheet is ws and i == 1))
                w = spec[i][1]
                text = str(c.value or "")
                est = sum(max(1, math.ceil(len(part) / max(1.0, (w - 2) * 0.95))) for part in text.split("\n"))
                lines = max(lines, est)
            sheet.row_dimensions[row[0].row].height = max(18, 15.5 * lines + 4)
        for c in sheet[1]:
            c.font = Font(name="Calibri", size=11, bold=True, color="FFFFFFFF")
            c.fill = PatternFill("solid", fgColor="FF1F3864")
            c.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
        sheet.row_dimensions[1].height = 32
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
    wb.save(out / "candidates.xlsx")


if __name__ == "__main__":
    import json
    import sys
    d = Path(sys.argv[1])
    write_xlsx(json.loads((d / "sweep.json").read_text()), d)
    print("wrote", d / "candidates.xlsx")
