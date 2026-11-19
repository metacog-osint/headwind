# Headwind (`D:\Projects\headwind`)

Economic stress for The Intelligence Company (`tic-feed/2`, program id `headwind`, prefix `HW`): currencies, energy
and food prices against their own normal range; changes to official sanctions and US screening lists; export-control,
sanctions and trade rules (BIS, OFAC, USTR) and their public-inspection filings; tariff actions; US import reliance
for minerals; a calendar of dates for Verdict. Second strand, **legal events** (`HW-REQ-2`, 18 Nov 2026): highest
and international courts' decisions as each court publishes them, no anomaly test; US and UK Supreme Courts live.
Measurements only: no probabilities, no investment advice. Live at https://headwind.theintelligence.company (Pages project `headwind`,
`headwind-2lx.pages.dev`). Repo `metacog-osint/headwind`, **public since 15 Nov 2026**.

**Notes:** this file holds lasting facts only (12 KB cap). Current state and open items: `.claude/HANDOFF.md`.
Full notes to 18 Nov 2026 (98 KB: state, live checks, backtests, licences):
`.claude/notes-archive-2026-11-18.md` (git-ignored; copy in `C:\Users\PSRA User 4\Backups\handover\`). Method in
detail, lane by lane: `doctrine/method.md`. Registers: `doctrine/indicators.json` (1.4), `sources.json`,
`requirements.json`. Plan and scope: `D:\Projects\_ideas\new-programs.md` (row and step 13) and
`D:\Projects\_ideas\drafts\2026-11-15-headwind-coverage-plan.md` (items 5 to 12 not built).

## Commands
```bash
python tools/headwind.py collect              # every lane into data/snapshot.json
python tools/headwind.py collect --only fx    # some lanes; the rest keep their last copy
python tools/headwind.py build                # site/ from data/snapshot.json
python tools/headwind.py check                # validate the registers and lint the feed
python -m unittest discover -s tests          # offline tests against real fixtures
python tools/serve.py                         # site/ on http://127.0.0.1:8751 with _headers (CSP); preview entry headwind-site
```
`collect` never makes data up: a failed lane keeps its last good copy (`from_previous`) or stays empty, and `lanes`
says which. `build` refuses to run without a snapshot.

## Deploy and state
- **A push to `main` runs `.github/workflows/update.yml`** (no paths filter, so a notes-only push runs it too): tests,
  state restore, `collect`, `build`, `check`, history log, state save, `wrangler pages deploy`. Also cron `23 */6`
  and tic-dispatch's `workflow_dispatch` (:50 past 03, 09, 15, 21 UTC). Public repo, so Actions minutes are free.
- **`main` gains a `headwind-bot` history commit on most runs**: merge `origin/main` into your branch before every
  push; push by sha. The main checkout works on `live/first-slice`.
- **State** (`data/snapshot.json`, `data/state/`) must carry between runs or every run is a first reading: Actions
  cache (key `headwind-state-<run id>`), then the public prerelease `state` (`headwind-state.tar.gz` plus 14 dated
  copies). With neither, a run fails unless started by hand with `first_reading`. **The state is public**: nothing
  goes in it that may not be published (UN list text never does).
- **Retention** (`headwind/archive.py`): `history/deltas/YYYY-MM.jsonl.gz` (full list changes; removed individuals
  in full, `ARCHIVE_REMOVED_INDIVIDUALS = True`, Tom 19 Nov 2026), `history/fetch-index/`, dated states in release
  `state-YYYY-qN` (none deleted), ship-table versions beside them.
- **History log:** `doctrine/kit/tic.py history ... --reading-key data_as_of` writes `history/` and
  `site/data/ended.geojson`; a failure there is a warning, never a missed deploy. COP reads `ended` and
  `source_health` (COP `config/programs.json`).
- Secrets `EIA_API_KEY`, `CENSUS_API_KEY`, `CLOUDFLARE_PAGES_TOKEN`; variable `CLOUDFLARE_ACCOUNT_ID`. Set variables
  with `--body`, never a PowerShell pipe (a BOM broke a run on 13 Nov). `wrangler pages project create` needs `--force`.
- Kit: vendored in `doctrine/kit/` (0.5.13); a test checks it is unedited and, beside `../tic-doctrine`, current.
  `tic-doctrine/tools/sync.py` takes its first argument as the target (`--help` makes a folder named `--help`).

## Rules
- **Standard library only** (Python 3.11+). Raw copies to `data/raw/<source>/<sha12>.<ext>` + `index.jsonl`
  (git-ignored, ~150 MB, mostly WFP; WFP refetched only when HDX's `last_modified` changes). `GEMINI.md` and `data/`
  stay untracked.
- **One measure** (`stats.py`): latest change against the series' own earlier changes, robust z (median, MAD);
  anomaly at |z| >= 3.5 and at least the lane floor (1% currencies, 5% energy, 2% FAO, 10% local food, 3% Pink Sheet,
  10% phosphate rock). Local food and FAO also flag on a rise above their 95th percentile (`rank`) or six rises in a
  row (`run`). Every item carries `flag_rate`; an anomaly carries the kit's object `baseline_ref`.
- Describe Headwind publicly only from what is live.
- **No judgments in the feed** (seed's fixed 0.85 and `MADE_UP` records removed). Rules are tier `routine`; a list
  change is `anomaly` only when one of its designation batches is.
- **Stable per-series ids** (18 Nov 2026): `headwind:fx:<cur>`, `fxofficial:<cc>`, `fxmarket:<cc>`, `energy:<id>`,
  `food:<id>`, `pinksheet:<series>`, `localfood:<cc>`; a new reading logs as changed, not ended.
- **Indicators (register 1.4):** anomalies for a watched country (`feed.WATCHED`, from `config/wfp_countries.json`)
  carry HW-WP-2 ids: currency `HW-IND-4`/`HW-H-2A`, energy `HW-IND-5`/`HW-H-2B` (both diagnostic, direction supports),
  local food `HW-IND-6`/`HW-H-2A` (neutral, expected under both). FAO indices (`HW-IND-3`) and other currencies carry
  none. HW-WP-1: H-1A "OFAC designates ships or a procurement network in one action"; H-1B BIS or USTR extend stays
  before a scheduled date (`HW-IND-2`, public inspection); H-1C artefact with `HW-IND-7` (renames or re-keys more than
  half of a change); `HW-IND-1` = an OFAC change adds 3+ ships with IMO numbers; `feed.list_indicator` tags each
  change. Wording is Tom's.
- **Names** (Tom, 15-16 Nov 2026, option (b)): publish everything licences allow. People, organizations and ships
  are named on every list but the UN's (name, type, programs, address and nationality countries, listing date);
  feed names up to 25 per change, page and `data/list-changes.json` for 30 days; take-down
  support@theintelligence.company; `us_person_data` from address countries (OFAC `add.csv`). Ship owners never kept.
  OFAC and BIS notices on public inspection keep only `federalregister.gov/d/<number>`. USITC's `creator` never kept.
- **Court items** carry the court's own case title and number; `us_person_data` by party test (Tom accepted, 16 Nov).
  Courts, ICC and tariff litigation live inside Headwind as the legal-events strand, not a new program; BRICS membership goes to Readout.
- **Country placement** (Tom): `UKRAINE-EO13661/13662` Russia; `-EO13660/13685` Russia and Ukraine; `PAARSSR-EO13894`
  Syria; EU `UKR` and Canada's Ukraine regime Russia only; EU `SDNZ` Sudan; France: national entries apart,
  restatements counted only, no countries. Conduct programs stay unplaced; an unknown code shows as
  `unknown_programs`: add it to a map.
- **Keys** (EIA, Census): env var or `%USERPROFILE%\.headwind\<name>_api_key.txt`; added only to the request as sent;
  recorded URLs, raw index, snapshot and errors stay keyless (tests). Never print one. In an old PowerShell:
  `$env:EIA_API_KEY = [Environment]::GetEnvironmentVariable('EIA_API_KEY','User')`.
- **D: drive:** writes sometimes fail with `OSError: [Errno 22]`; patch scripts retry and read back. Never rerun a
  patch script that stopped part-way (anchors survive, so it inserts twice).
- Fixtures are real replies cut small (cut scripts in git-ignored `.claude/`); `.gitattributes` keeps the USGS CSVs
  byte for byte.

## Lanes
| Lane | Source (keyless unless marked) | Notes |
|---|---|---|
| `fx` | ECB reference rates, restated per US dollar | 29 currencies; footer says restated |
| `gem` | World Bank GEM (WDI source 15, `DPANUSSPB`), official monthly | 19 watched countries; 2% floor, >4 months old is stale |
| `wfp` | WFP prices by market (HDX), `config/wfp_countries.json` | local food plus market FX (`split` when markets differ 1.5x; Somalia); Cuba no file; re-reads a kept reading lacking `rules` |
| `energy` | EIA API v2 (Brent, WTI, Henry Hub). **EIA key** | not FRED (FRED's terms bar scraping) |
| `fao` | FAO Food Price Index CSV (link read from the page) | 6 indices; vintages kept |
| `pinksheet` | World Bank Pink Sheet xlsx (link read yearly) | fertilizers and 8 list metals; CC BY 4.0 (dataset 0038238) |
| `baseline` | World Bank WDI, six indicators | context, not in the feed |
| `calendar` | Fed and ECB schedule pages, FAO dates | rate decisions go to Verdict as `rule_date` |
| `sanctions` | OFAC `sdn.csv`, UN XML, EU FSF XML, UK Sanctions List XML, France `france-gels` JSON, Canada `canada-sema` XML, Australia `australia-dfat` xlsx, Japan `japan-mof` CSV + ship CSV (dated links read from MOF's page); AU and JP UN entries counted only | change = diff of two own readings; each list alone; short parse or >half lost fails the list; designation batches (`batches.py`) |
| `screening` | trade.gov CSL JSON (all but SDN) | re-keyed ids paired by name hash and type |
| `controls` | Federal Register: BIS, OFAC, USTR rules and USTR notices (60 d), register of dates (800 d), presidential tariff documents | 14 days in feed; dates to Verdict |
| `inspection` | Federal Register public inspection | `HW-IND-2` matcher; agency filter ignored by API, so whole issues read |
| `tariffs` | USITC HTS release list; White House actions RSS | tariff pace items |
| `trade` | Census intl trade API, 24 HS codes. **Census key** | context; Census endorsement notice required on page |
| `scotus` | supremecourt.gov slip opinion RSS + docket JSON | `TARIFF_DOCKETS` 24-1287, 25-250 |
| `uksc` | supremecourt.uk sitemap, latest page, case pages | OGL v3.0; Find Case Law not used (licence bars computational analysis) |
| `unpress` | UN press RSS, sanctions committee releases | number, date, link only; feed of 10 can drop releases (warning) |
| `minerals` | USGS MCS 2026 (ScienceBase); `CRITICAL_2025` constant | watches for MCS 2027 and a new critical list; change `ITEM_ID` and the constant by hand |

Source health (`health.py`): per source id, fresh/late/stale by its own rhythm, drift checks, quiet-publisher
warnings, one retry on timeout, 5xx or 429. Outputs in `site/data/`: `feed.geojson`, `events.json` (Verdict),
`snapshot.json`, `baseline.json`, `minerals.json`, `vessels.json` (IMO cross-list), `list-changes.json`,
`ended.geojson`, `question_drafts.json` (read by nothing).

## Licences (short; readings and dates in the archive)
WFP/HDX CC BY-IGO. World Bank (GEM, WDI, Pink Sheet) CC BY 4.0. FAO CC BY 4.0 with its citation form (not yet used)
and no commercial promotion. ECB free with source cited and changes stated. EIA public domain, credit "Source: U.S.
Energy Information Administration". Federal Register, Fed, OFAC, trade.gov, Census, USGS (CC0): US government.
EU 2011/833/EU reuse; UK OGL v3.0 (excludes personal data; names published anyway on Tom's (b)); France Licence
Ouverte 2.0; Canada reproduction for non-commercial use; Australia (DFAT) CC BY 4.0; Japan (MOF) PDL1.0 (source line 出典：財務省ウェブサイト + PDL1.0, and an edited-by note). **UN list: counts and a link only, never its content or
index** (UN terms withhold redistribution). UK Supreme Court OGL v3.0.

## Not built, and why
Switzerland SECO (needs written consent); New Zealand (MFAT terms bar automated access); IMF Board actions (terms bar automated
download); stock indices (OECD terms unread, Datastream, STOXX bars derivatives); CBP CSMS (no keyless feed); BLS and
IMF data API (403); France's date endpoint and legal-basis dates (unused); UKSC case filter (Next.js server action).
`HW-EEI-1` (designated vessels in Wake's tracks) not matched yet; `vessels.json` carries what it needs.
