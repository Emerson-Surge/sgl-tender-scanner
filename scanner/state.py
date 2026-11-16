"""Persistent state: what we've seen, what the tracker already has, run history.

Dedupe rules (fixes from the process review):
  * Primary identity is portal + reference (or URL). Only an exact identity match
    makes a candidate "seen".
  * A title-only match (same normalised first 60 chars, different identity) is
    NOT dropped: it is reported as "possible re-tender / duplicate".
  * Every seen item stores its deadline; a changed deadline is reported.
  * References/URLs found anywhere in the tracker workbook mark a candidate
    "in tracker" so it is never reported as new.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

from .matcher import norm

STATE_DIR = Path(__file__).resolve().parent.parent / "state"
SEEN = STATE_DIR / "seen.json"
HISTORY = STATE_DIR / "run_history.json"
TRACKER_REFS = STATE_DIR / "tracker_refs.json"


def _load(p, default):
    try:
        return json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        return default


def title_key(t: str) -> str:
    return norm(t).strip()[:60]


class State:
    def __init__(self):
        STATE_DIR.mkdir(exist_ok=True)
        self.seen: dict = _load(SEEN, {})            # identity -> record
        self.history: list = _load(HISTORY, [])
        self.tracker: dict = _load(TRACKER_REFS, {"refs": [], "urls": [], "titles": [], "blob": ""})
        self._titles = {}
        for k, rec in self.seen.items():
            self._titles.setdefault(rec.get("title_key", ""), []).append(k)
        self._blob = self.tracker.get("blob", "")

    # ---- window -------------------------------------------------------------
    def last_success(self, portal: str) -> dt.date | None:
        for run in reversed(self.history):
            p = run.get("portals", {}).get(portal)
            if p and p.get("status") in ("OK", "WARN") and p.get("rows_seen", 0) > 0:
                return dt.date.fromisoformat(run["date"])
        return None

    # ---- classification -----------------------------------------------------
    def in_tracker(self, c) -> bool:
        b = self._blob
        if not b:
            return False
        ref = (c.ref or "").strip()
        if len(ref) >= 5 and ref.lower() in b:
            return True
        if c.url and c.url.lower().rstrip("/") in b:
            return True
        tk = title_key(c.title)
        return len(tk) > 25 and tk in self.tracker.get("title_keys_blob", "")

    def classify(self, c) -> tuple[str, str]:
        """Return (status, note): new | seen | deadline_changed | possible_duplicate | in_tracker."""
        ident = c.key()
        rec = self.seen.get(ident)
        if rec:
            if c.deadline and rec.get("deadline") and c.deadline != rec["deadline"]:
                return "deadline_changed", f"deadline {rec['deadline']} -> {c.deadline}"
            return "seen", f"first seen {rec.get('first_seen')}"
        if self.in_tracker(c):
            return "in_tracker", "reference/URL/title already in tracker workbook"
        tk = title_key(c.title)
        others = [k for k in self._titles.get(tk, []) if k != ident] if len(tk) > 15 else []
        if others:
            o = self.seen.get(others[0], {})
            same_deadline = not c.deadline or not o.get("deadline") or c.deadline == o.get("deadline")
            if o.get("portal") != c.portal and same_deadline:
                return "seen", f"mirror of {others[0]}"
            return "possible_duplicate", (f"same title as {others[0]} (deadline {o.get('deadline') or '?'} -> "
                                          f"{c.deadline or '?'}): likely re-tender, check")
        return "new", ""

    def remember(self, c, today: dt.date):
        ident = c.key()
        rec = self.seen.get(ident, {"first_seen": today.isoformat()})
        rec.update({"title": c.title[:200], "title_key": title_key(c.title), "deadline": c.deadline,
                    "url": c.url, "last_seen": today.isoformat(), "portal": c.portal})
        self.seen[ident] = rec
        self._titles.setdefault(rec["title_key"], [])
        if ident not in self._titles[rec["title_key"]]:
            self._titles[rec["title_key"]].append(ident)

    def save(self, run_record: dict):
        self.history.append(run_record)
        self.history = self.history[-104:]  # two years of weekly runs
        SEEN.write_text(json.dumps(self.seen, ensure_ascii=False, indent=1))
        HISTORY.write_text(json.dumps(self.history, ensure_ascii=False, indent=1))


def import_tracker(xlsx_path: str) -> dict:
    """Pull every reference number, URL and title out of the tracker workbook."""
    import openpyxl
    wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
    texts, titles = [], []
    for ws in wb:
        for row in ws.iter_rows(values_only=True):
            cells = [str(v) for v in row if v is not None]
            texts.extend(cells)
            if ws.title in ("Details", "Closed & excluded") and len(cells) > 1:
                titles.append(cells[1] if ws.title == "Details" else cells[0])
    blob = "\n".join(texts).lower()
    rows = []
    if "Details" in wb.sheetnames:
        hdr = None
        for r in wb["Details"].iter_rows(values_only=True):
            if r and r[1] == "Opportunity":
                hdr = [str(h or "") for h in r]
                continue
            if hdr and r and r[1]:
                d = dict(zip(hdr, r))
                dd = d.get("Deadline (date)")
                rows.append({"priority": d.get("Priority") or "", "opportunity": d.get("Opportunity"),
                             "status": d.get("Status"), "country": d.get("Country"), "services": d.get("Services"),
                             "fit": d.get("Fit"), "timing": str(d.get("Deadline / Timing") or ""),
                             "deadline": dd.date().isoformat() if hasattr(dd, "date") else "",
                             "action": d.get("Action") or "", "source": str(d.get("Source") or "")})
    urls = sorted(set(re.findall(r"https?://[^\s;,)'\"]+", blob)))
    data = {"imported_from": Path(xlsx_path).name, "imported_at": dt.date.today().isoformat(),
            "urls": urls, "titles": titles, "blob": blob, "rows": rows,
            "title_keys_blob": "\n".join(title_key(t) for t in titles)}
    STATE_DIR.mkdir(exist_ok=True)
    TRACKER_REFS.write_text(json.dumps(data, ensure_ascii=False))
    return data
