# SGL tender scanner

Weekly sweep of public procurement portals for airborne-geophysics tenders (magnetics, gravity,
radiometrics, EM, LiDAR, data licensing). Python standard library + `requests`, headless Chromium
(Node Playwright) for JavaScript-only portals. No logins, no form submissions beyond public
searches, and no attempts to get past bot protection: blocked portals are listed as manual checks.

## Run
```
python3 tests/test_matcher.py      # matcher regression tests (every past miss is a case)
python3 -m scanner.run             # weekly run, about 10-12 minutes
python3 -m scanner.try_portal ted 30   # test one adapter
python3 -c "from scanner.state import import_tracker; import_tracker('path/to/SGL_Tender_Tracker.xlsx')"
```
Output: `runs/<date>/report.html`, `report.md`, `candidates.xlsx`, `sweep.json`.
The Monday scheduled session follows `WEEKLY_RUN.md`.

## What it does differently from the other pipeline
- **Never quiet.** Every run prints one summary line and a portal health table. A portal returning
  fewer rows than its floor is flagged (layout change), not treated as a quiet week.
- **Self-healing window.** Each portal sweeps from its own last successful run minus 2 days, so a
  failed Monday is re-swept next week.
- **Dedupe by portal + reference.** Title-only matches are shown as possible re-tenders, never
  dropped. Deadlines are stored, and changes are reported.
- **Tracker-aware.** References and URLs in the tracker workbook mark items "already tracked".
- **Accent-folded multilingual matcher** (EN FR PT ES DE NL Nordic FI PL TR IT RU EL AR KO JA ZH VI TH ID),
  with whole-word short terms, negative hints (lab, ground, well logging, aerial photos), and an airborne
  flag that splits "likely airborne" from "geophysics, review".
- **Awards kept**, not discarded, for the weekly award re-check. Drone-only notices are listed as excluded.
- **Official APIs where they exist:** TED v3 (keyless), World Bank, IDB, CanadaBuys, PNCP, SECOP, BOAMP, TenderNed, UK FTS/Contracts Finder, Greece KIMDIS.
- **Headless browser** for JS-only listings (dgMarket, Petronect, QTenders, NEN, ComprasMX, PhilGEPS, Pertamina).
- **World Bank project watch** for P506438 (DRC Inga 3) and P510607 (Peru minerals).

## Optional free keys (set as environment variables)
`SAM_API_KEY` (api.data.gov), `KONEPS_API_KEY` (data.go.kr), `MERCADOPUBLICO_TICKET`, `ALERTALICITACAO_TOKEN`.
Time budgets: `PNCP_BUDGET_S` (420), `PLACSP_BUDGET_S` (600), `FTS_BUDGET_S` (580).

## Manual checks (blocked for automated access)
AusTender (CloudFront), GeM bidplus (connection reset), CPPP India (captcha), EKAP Turkey (captcha),
Thailand e-GP (bot defence), Indonesia LPSE/INAPROC (Cloudflare), Mongolia tender.gov.mn (Cloudflare),
AfDB (403), Senegal / Egypt e-tenders (connection reset), zakup.sk.kz and xarid (click-only paging),
Côte d'Ivoire SIGOMAP (account needed), Mali / Guinea portals (unreachable).

## Portals (48), status on first run 2026-11-13
| Region | Portal | Key | Method | First-run status |
|---|---|---|---|---|
| Africa | Burkina Faso Quotidien des marchés publics (DGCMEF) | `burkina` | Public daily bulletin PDFs (pdftotext, split per item) | FAIL only 0 rows (expected >= 1): page layout may have changed or portal is empty |
| Africa | Nigeria NipeX current opportunities (NNPC/upstream) | `eprocng` | Public HTML cards | OK  |
| Africa | eTenders South Africa | `etenderza` | Public DataTable JSON (PaginatedTenderOpportunities) | OK  |
| Africa | Ghana GHANEPS current tenders | `ghaneps` | Public HTML list (ePPS displaytag) | OK  |
| Africa | Tanzania NeST published tenders | `nest` | Public page's GraphQL list query | OK  |
| Africa | Zambia ZPPA e-GP (latest tenders only) | `zppa` | Public home page 'Latest Tenders' block (full list is captcha-gated) | OK  |
| Africa/MENA | BAOSEM (Algeria energy & mines bulletin) | `baosem` | Public search form HTML (subscriber fields hidden) | OK  |
| Americas | Alerta Licitação (Brazil) | `alertalicitacao` | Official API v1 (token in ALERTALICITACAO_TOKEN); website manual-only | FAIL ALERTALICITACAO_TOKEN not set (token needs an Alerta Licitação account); website |
| Americas | CanadaBuys (Canada) | `canadabuys` | Official open-data CSVs (keyless) | OK  |
| Americas | ComprasMX (Mexico) | `comprasmx` | Public site 'Anuncios vigentes', headless render + paging | WARN render: page 4 did not change |
| Americas | ControlBid (Petronect mirror) | `controlbid` | Public HTML listing + detail pages | OK  |
| Americas | Diário Oficial da União - Seção 3 (Brazil) | `dou` | Public reader page, embedded jsonArray (one GET per weekday) | OK  |
| Americas | Mercado Público (Chile) | `mercadopublico` | Official API (ticket, optional) + public search page keyword render | OK  |
| Americas | MERX (Canada) | `merx` | Public search page, keyword queries (plain HTML) | OK  |
| Americas | Petronect (Petrobras) | `petronect` | Public list page, headless render + on-page keyword search | OK  |
| Americas | PNCP (Brazil) | `pncp` | Official Consultation API v1 (keyless) | OK  |
| Americas | SAM.gov (USA) | `sam` | Official Opportunities API v2 (free key in SAM_API_KEY) | FAIL SAM_API_KEY not set: register free key at api.data.gov |
| Americas | SECOP II (Colombia) | `secop` | datos.gov.co Socrata SODA API (official open data, keyless) | OK  |
| Asia-Pacific | FirstTender (India) | `firsttender` | Public keyword/buyer pages, schema.org JSON-LD | OK  |
| Asia-Pacific | GETS (New Zealand) | `gets` | Public current-tenders list (all pages) | OK  |
| Asia-Pacific | KONEPS (Korea, data.go.kr) | `koneps` | Official data.go.kr Open API (key in KONEPS_API_KEY) | FAIL KONEPS_API_KEY not set |
| Asia-Pacific | Pertamina procurement announcements | `pertamina` | Public announcement pages, headless render | OK  |
| Asia-Pacific | PhilGEPS (Philippines) | `philgeps` | Public open-opportunities keyword search (form) | OK  |
| Asia-Pacific | QTenders (Queensland) | `qtenders` | Public search, headless render (all open tenders) | OK  |
| Asia-Pacific | TenderNews (India/global) | `tendernews` | Public keyword listing pages | OK  |
| Asia-Pacific | Tenders WA (Western Australia) | `tenderswa` | Public open-tender list | OK  |
| Asia/Middle East | Pakistan PPRA e-PMS active tenders | `ppra` | Public HTML list (paged) | OK  |
| Europe | BOAMP (France) | `boamp` | Official Opendatasoft API on boamp.fr (export + full-text search) | OK  |
| Europe | UK Contracts Finder | `contractsfinder` | Official OCDS search API (keyless), stages=tender | OK  |
| Europe | Doffin (Norway) | `doffin` | Website's keyless JSON search API, 7-day chunks | OK  |
| Europe | Greece KIMDIS (ESHDHS) | `eshdhs` | Official open-data API (keyless), title + CPV search | OK  |
| Europe | eTenders (Ireland) | `etendersie` | Public notice listing (HTML, 100/page) | OK  |
| Europe | e-Zamówienia BZP (Poland) | `ezamowienia` | Board's keyless JSON search (subject/CPV/buyer queries) | WARN time budget hit at {'CpvCode': '71352000-0'} |
| Europe | UK Find a Tender | `fts` | Official OCDS API (keyless), cursor pagination | WARN time budget hit after 41 pages; older releases skipped |
| Europe | Hilma (Finland) | `hilma` | Website's keyless search proxy (Azure Search OData), full window | OK  |
| Europe | NEN (Czech Republic) | `nen` | Headless render of public quick-search pages | OK  |
| Europe | PLACSP (Spain) | `placsp` | Official ATOM syndication feed 643 (time-budgeted, newest first) | OK  |
| Europe | TED (EU) | `ted` | Official Search API v3 (keyless) | OK  |
| Europe | TenderNed (Netherlands) | `tenderned` | Official public API (keyless), full window | OK  |
| Europe | udbud.dk (Denmark) | `udbud` | Website's keyless JSON search endpoint, all active notices | OK  |
| Europe | Útboðsvefur / Útboð.is (Iceland) | `utbod` | Public open-tender listings (static HTML) | OK  |
| Global | dgMarket (CPV listing) | `dgmarket` | Public CPV listing, headless render (listing fields only) | OK  |
| Global | Tender Impulse | `tenderimpulse` | Public keyword search (POST form) + country index page | OK  |
| Global/Donor | IDB procurement notices | `idb` | Official CKAN datastore SQL API (keyless) | OK  |
| Global/Donor | UNGM (UN Global Marketplace) | `ungm` | Public notice search (page's JSON POST) | OK  |
| Global/Donor | World Bank procurement notices | `worldbank` | Search API v2 procnotices (keyless) | OK  |
| Middle East | Etimad (Saudi Arabia) | `etimad` | Public visitor search JSON (AllSupplierTendersForVisitorAsync) | WARN {} p3: HTTP 400 (stopping; rate limit is respected) |
| Middle East | Oman Tender Board e-Tendering | `omantb` | Public dashboard HTML (New Tenders, paged) | OK  |
