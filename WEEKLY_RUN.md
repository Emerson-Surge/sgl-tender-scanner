# Weekly run instructions (read by the Monday scheduled session)

You are running SGL's weekly airborne-geophysics tender sweep. Work in this repo.

## 1. Run the sweep
```
python3 tests/test_matcher.py          # must print 4 PASS lines; if not, stop and report
python3 -m scanner.run
```
It prints one summary line and writes `runs/<date>/` (report.html, report.md, sweep.json, candidates.xlsx),
and updates `state/seen.json` and `state/run_history.json`. Never edit state files by hand.

## 2. Verify each NEW, deadline-changed and possible re-tender candidate
Open each candidate's URL (read only, no logins, no form submissions). For each, decide:
- In scope? Airborne (manned aircraft or helicopter) magnetics, gravity, radiometrics/gamma, EM, or
  airborne geophysics data licensing. Drone-only, ground-only, seismic-only, equipment purchase,
  aerial photography and LiDAR-only are OUT (say so in one line).
- Deadline: confirm from the notice itself, else write "unverified".
- Value if stated, and whether it is in the ~$500k to $30M range.
- Eligibility notes (foreign bidders, registration, language).
Write the verdicts to `runs/<date>/verified.md` as a table: verdict (QUALIFIES / OUT / CHECK),
client, country, services, deadline, value, source URL, one-line reason.
Never invent a winner, value or deadline. Public sources only.

Then write `runs/<date>/translations.json` covering EVERY row in the Candidates sheet (all buckets),
keyed "portal:ref" exactly as in sweep.json, with plain-English values:
`{"portal:ref": {"title_en": "...", "buyer_en": "...", "verdict": "QUALIFIES / OUT / CHECK / AWARD / EXCLUDED: one-line reason"}}`.
Translate every non-English title and buyer name into English. Then rebuild the spreadsheet so it carries them:
`python3 -m scanner.report runs/<date>` (every cell must be English; the sheet wraps text and sizes rows itself).

## 3. Commit
`git add -A && git commit -m "Sweep <date>: <summary line>" && git push`

## 4. Gmail draft (NEVER send)
Create a Gmail draft: TO surveys@sgl.com, CC elalonde@sgl.com, subject
"SGL tender sweep <date>: <N> qualifying". Body: lead with QUALIFIES rows (client, country, services,
deadline, value, link), then CHECK rows, then one line on portal health (portals OK/warn/failed, and
names of any failed portal), then the manual-check list from the report. Keep it short; detail lives in
the report. Do not send. Always create the draft, even when nothing qualifies, so a missing draft
means the run did not happen.

## 5. Final message
End with the summary line, the count of QUALIFIES, and any portal that FAILED two weeks running
(check `state/run_history.json`): those need an adapter fix.
