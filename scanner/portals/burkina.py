"""Burkina Faso DGCMEF "Quotidien des marchés publics" (official daily public
procurement bulletin), public PDFs listed at
https://www.dgcmef.gov.bf/index.php/fr/appels-d-offre (10 latest issues).
For each issue dated >= ctx.since we download the PDF, extract text with
pdftotext, and split it into items at each procedure reference line
("Demande de prix n°…", "Appel d'offres … n°…", "Avis à manifestation d'intérêt
n°…", "Demande de propositions n°…"). Each item is one Candidate (ref =
issue-number + item index, url = the issue PDF). Items include both new
notices and published evaluation results (the bulletin mixes them).
Note: the DGCMEF list page lags (latest issue listed 21 Oct 2026 on 13 Nov
2026), so the health check may see quiet weeks.
"""
import datetime as dt
import re
import subprocess
import tempfile

from ..core import Candidate, PortalInfo, PortalResult, RunContext, get

PORTAL = PortalInfo(key="burkina", name="Burkina Faso Quotidien des marchés publics (DGCMEF)", region="Africa",
                    method="Public daily bulletin PDFs (pdftotext, split per item)", min_rows=1,
                    url="https://www.dgcmef.gov.bf/index.php/fr/appels-d-offre")

LIST = "https://www.dgcmef.gov.bf/index.php/fr/appels-d-offre"
MONTHS = {"janvier": 1, "fevrier": 2, "février": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6, "juillet": 7,
          "aout": 8, "août": 8, "septembre": 9, "octobre": 10, "novembre": 11, "decembre": 12, "décembre": 12}
START = re.compile(r"(?i)^\s*(?:avis\s+(?:de\s+|d.|[àa]\s+)?)?(demande\s+de\s+prix|appel\s+d.offres?|manifestation\s+d.int[ée]r[êe]t|"
                   r"demande\s+de\s+propositions?|consultation\s+restreinte|pr[ée]qualification)"
                   r"[^\n]{0,60}?\bn\s*[°o]\s*\S")


def _issue_date(title):
    m = re.search(r"(\d{1,2})\s+([a-zéû]+)\s+(\d{4})", title.lower())
    if m and m[2] in MONTHS:
        try:
            return dt.date(int(m[3]), MONTHS[m[2]], int(m[1]))
        except ValueError:
            return None
    return None


def _items(text):
    lines = text.splitlines()
    starts = [i for i, ln in enumerate(lines) if START.search(ln)]
    for k, i in enumerate(starts):
        j = starts[k + 1] if k + 1 < len(starts) else min(len(lines), i + 80)
        chunk = "\n".join(lines[i:j])
        yield re.sub(r"\s+", " ", chunk).strip()


def fetch(ctx: RunContext) -> PortalResult:
    res = PortalResult(portal=PORTAL.key)
    try:
        r = get(LIST, timeout=ctx.timeout)
        res.queries += 1
        if r.status_code != 200:
            res.errors.append(f"list HTTP {r.status_code}")
            return res
        issues = re.findall(r'<a href="[^"]*/node/\d+"[^>]*>([^<]+)</a>\s*</td>\s*<td[^>]*>.*?<a href="([^"]+\.pdf)"',
                            r.text, re.S | re.I)
        if not issues:
            res.errors.append("no bulletin links found (layout change?)")
        for title, pdf in issues:
            d = _issue_date(title)
            if d and d < ctx.since:
                continue
            num = (re.search(r"n\s*°\s*(\d+)", title, re.I) or [None, ""])[1]
            p = get(pdf, timeout=120)
            res.queries += 1
            if p.status_code != 200 or not p.content.startswith(b"%PDF"):
                res.errors.append(f"{title}: PDF HTTP {p.status_code}")
                continue
            with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
                f.write(p.content)
                f.flush()
                txt = subprocess.run(["pdftotext", "-layout", f.name, "-"], capture_output=True, text=True,
                                     timeout=120).stdout
            n = 0
            for n, item in enumerate(_items(txt), 1):
                res.rows_seen += 1
                res.candidates.append(Candidate(
                    portal="burkina", ref=f"Q{num}-{n}", title=item[:300], url=pdf, country="Burkina Faso",
                    published=d.isoformat() if d else "", description=item[:2000],
                    notice_type="bulletin item", language="fr",
                    extra={"issue": title.strip(), "issue_no": num}))
            if n == 0:
                res.notes.append(f"{title.strip()}: no items split from {len(txt)} chars")
    except Exception as e:  # noqa: BLE001
        res.errors.append(f"{type(e).__name__}: {e}")
    return res
