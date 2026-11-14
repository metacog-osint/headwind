# Headwind (`[local path]`)

Economic stress for The Intelligence Company (`tic-feed/2`, program id `headwind`, prefix `HW`): currencies,
energy and food prices measured against their own normal range, changes to official sanctions and US screening
lists, export-control and sanctions rules, US import reliance for minerals, plus a calendar of dates for Verdict. Measurements only. No probabilities, no investment advice.

**State, 13 Nov 2026: live at https://headwind.theintelligence.company and updating itself.** Ten lanes, method
`headwind-1.3`. `main` and `live/first-slice` are the same commit and pushed; a push to `main` runs the workflow,
which collects, builds, checks and deploys. The house bar lists Headwind and the suite registry lists it as live
(see Deploy). Untracked and to stay that way: `GEMINI.md` and `data/`. Commit history before the deploy:
`ed4e461` first live slice, `472e802` sanctions and rules (`headwind-1.2`), `921d8f6` screening and minerals
(`headwind-1.3`), `14e3501` energy from EIA, `da87b11` vessels and house bar, `39819ab` light and dark theme,
`3281d97` state in the Actions cache and FAO's licence.

**Planned scope** (`[local path]`, program row and roadmap step 13): sanctions, export
controls, prices, currency and energy, with critical minerals, trade.gov screening-list diffs and UN list deltas
(needs a Census key). Built so far: prices, currency, energy, OFAC and UN list changes, BIS and OFAC rules, trade.gov screening-list
changes, and USGS mineral import reliance. Not built: Census trade data for minerals (needs a key, which Tom
creates). Describe Headwind publicly from what is live.

## Deploy (13 Nov 2026)
- **Live at https://headwind-2lx.pages.dev** since about 10:41 AM CST, 13 Nov (`headwind.pages.dev` was taken).
  Cloudflare Pages project `headwind`, created with `wrangler pages project create headwind --production-branch
  main --force` (without `--force` wrangler 4.151.3 hands the command to Workers and creates nothing). The first
  deploy was by hand from the 10:28 AM CST build, at `3281d97`.
- **The workflow deploys since 12:42 PM CST, 13 Nov** (run 43485220044, started by hand): tests, state restored
  from the Actions cache, all ten lanes ok on the runner, check PASS, state saved, `wrangler pages deploy`. The
  first run (43465309003, 10:42 AM CST) did everything but deploy, because `CLOUDFLARE_PAGES_TOKEN` was not yet
  set; Tom set it at 12:25 PM CST. Secret `EIA_API_KEY` and repo variable `CLOUDFLARE_ACCOUNT_ID` are set.
- **A byte-order mark broke one run.** The account ID was copied from Blackout's repo with a PowerShell pipe
  (`gh variable get ... | gh variable set ...`), which put a BOM in front of the value; run 43482685192 failed at
  the deploy step with "Invalid account ID". The variable was set again at 12:28 PM CST and runs pass. Set
  variables with `--body`, not a PowerShell pipe.
- **State carries between runs:** the list baseline on the live page is still the first CI run's (10:43 AM CST).
  The local `data/` and the runner's cache are separate histories; the live site follows the runner's.
- **Custom domain: https://headwind.theintelligence.company**, active with HTTPS and HSTS since about 11:00 AM CST,
  13 Nov (Pages API domain + Squarespace `CNAME headwind -> headwind-2lx.pages.dev`, 4 hrs; Squarespace asked Tom
  to reauthenticate before it took the record).
- **Suite listing, 13 Nov (done by a separate hub session; its report, with the Headwind page checked here):** house
  bar `tic-nav.js` v1.8 lists Headwind (`Systems · economic stress`, beta) and is on this page since `7df0baa`; the
  hub and the other program sites carry it, PropertyCast from its 14 Nov publish; the registry row, COP's drawing
  entry and a tic-dispatch entry are pushed and deployed. Details are in the hub's `HISTORY.md` and `HANDOFF.md`.
- **Not done:** Tom adds `headwind` to the `tic-dispatch` token's repository access; until then the dispatcher's
  start returns 404 and the workflow runs on its own 6-hourly cron, which GitHub fires 4-9 h late.

## Commands

```bash
python tools/headwind.py collect              # fetch every live lane into data/snapshot.json
python tools/headwind.py collect --only fx    # one or more lanes; the rest keep their last copy
python tools/headwind.py build                # build site/ from data/snapshot.json
python tools/headwind.py check                # validate the registers and lint the feed
python tools/headwind.py restore --from URL   # a scheduled run: read the last state from the published site
python -m unittest discover -s tests          # 24 offline tests against real fixtures
python tools/serve.py                         # site/ on http://127.0.0.1:8751 with the headers in _headers (CSP)
```

`collect` never falls back to made-up data. A lane that fails keeps its last good copy (`from_previous`) or stays
empty, and `lanes` in the snapshot says which. `build` refuses to run without a snapshot.

## Lanes

| Lane | Module | Source (all keyless) | Checked live 12 Nov |
|---|---|---|---|
| `fx` | `markets.py` | ECB reference rates, history zip; restated per US dollar | 29 currencies |
| `energy` | `markets.py` | EIA's own API v2 (Brent `RBRTE`, WTI `RWTC`, Henry Hub `RNGWHHD`). **Needs a free EIA key** | 13 Nov, 9:35 AM CST: 3 series to 11 Nov (Brent 92.14, WTI 89.62, Henry Hub 3.00), the same prices FRED gave |
| `fao` | `food.py` | FAO Food Price Index CSV; the link is read from FAO's page because it changes | 6 indices |
| `wfp` | `food.py` | WFP prices by market from HDX, for the countries in `config/wfp_countries.json` | 18 of 19 countries; Cuba has no file, Venezuela's newest month is May 2025 |
| `baseline` | `baseline.py` | World Bank WDI API, six indicators | 213 countries. The API timed out twice earlier the same evening |
| `calendar` | `releases.py` | Federal Reserve and ECB schedule pages; FAO release dates | 9 events in the next 180 days |
| `sanctions` | `sanctions.py` | OFAC `sdn.csv` (5.8 MB) and the UN Security Council consolidated list (XML) | 12 Nov, 11:55 PM CST: 19,563 OFAC entries (1,570 vessels) and 1,007 UN entries. First reading, so no change to report yet |
| `screening` | `screening.py` | trade.gov Consolidated Screening List (one 34 MB JSON), every list but the SDN list | 13 Nov, 8:46 AM CST: 12 lists, 6,702 entries (Entity List 3,419). First reading, so no change to report yet. The download took 4 s |
| `controls` | `controls.py` | Federal Register API: BIS and OFAC rules and proposed rules, last 60 days | 13 Nov: 25 rules; 2 future dates for Verdict (3 Dec polysilicon rule ends, 10 Jan 2027 affiliates-rule stay ends) |
| `minerals` | `minerals.py` | USGS Mineral Commodity Summaries 2026 data release on ScienceBase (item JSON, then two CSVs) | 13 Nov: 68 commodities with net import reliance, 47 with import shares by country |

The sanctions lane was read three times on 13 Nov (to about 9 AM CST) and both files were byte-for-byte the same as
on 12 Nov, so Headwind has still not seen a real list change. The trade.gov file says OFAC last updated on 9 Nov.

Outputs in `site/data/`: `feed.geojson` (60 items on 13 Nov), `events.json` (Verdict's `sync_calendar` format),
`baseline.json` and `minerals.json` (not in the feed), `question_drafts.json` (drafts only), `snapshot.json` (what
the page reads).

## The measure (`stats.py`, `doctrine/method.md`)
One rule for every series: the latest change against the series' own earlier changes, as a robust z (median and
MAD). Anomaly at |z| >= 3.5 and a move of at least the lane's floor: 1% currencies, 5% energy, 2% FAO indices,
10% local food (constants in `markets.py` and `food.py`). Each item carries `flag_rate`, how often the series
trips the rule in ordinary times. On 12 Nov nothing was flagged; the largest z was 3.0 (Australian dollar).

## Sanctions lists and rules (`headwind-1.2`)
- **A list change is the difference between two of Headwind's own readings.** Each run reduces a list to
  `entry id -> [type, programs]`, compares it with `data/state/sanctions_index.json` from the run before, and
  reports counts by type and program. The date on a change is when Headwind saw it, not the designation date.
  The first run only sets the baseline. A change stays in the snapshot 30 days and in the feed 7.
- **People and organizations are counts only. Vessels are named** (Tom, 13 Nov 2026): an OFAC vessel entry
  carries its name, IMO number, MMSI, flag and type in the index, the snapshot (`vessels_added`,
  `vessels_removed`), the feed summary (first 25) and the page. The owner column is not carried because it can name
  a person, and `us_person_data` stays `none`. On 13 Nov, 1,555 of 1,570 listed vessels had an IMO number. A vessel
  removed from an index written before 13 Nov is counted but not named. The UN list has no vessels.
- **A list that parses short or loses over half its entries fails the lane** and is never reported as delistings.
- **`data/state/` must be carried between scheduled runs**, like `data/snapshot.json`, or every run is a first run.
- **Countries on a list change** come from the program name where it names one country (`PROGRAM_COUNTRY` in
  `sanctions.py`; conduct programs such as SDGT are left unplaced). Checked 13 Nov against all 72 program tags on
  the live SDN list and the 14 UN list types: `HRIT-SY` was going to Iran and `CAATSA - RUSSIA`, `CAATSA - IRAN`,
  `MAGNIT`, `PEESA`, `SSIDES` and `UHRPA` were unplaced; all are fixed, and each tag was then read against
  OFAC's program tag definitions page. `SSIDES` is the 2014 Ukraine support act (Russia), not South Sudan as first
  entered. Tom's decisions, 13 Nov: `UKRAINE-EO13661` and `-EO13662` are Russia; `UKRAINE-EO13660` and `-EO13685`
  (Crimea) are Russia and Ukraine; `PAARSSR-EO13894` is Syria. A map value can be a tuple of two countries.
- **Rules:** a document stays in the feed 14 days. Future dates come from its effective date, its comment
  deadline, and dates written out in its DATES paragraph (`named_dates`); each becomes a `rule_date` for Verdict.
  Countries are only those a title names. USTR notices and public-inspection filings are not read.
- **Every list and rule item is tier `routine`.** No anomaly rule exists for them yet: there is no history of
  Headwind's own readings to measure against.

## Energy and the EIA key (changed 13 Nov 2026, Tom's decision)
- **The energy lane reads EIA's API, not FRED.** FRED's terms bar scraping and passing stored content on.
- **The key** is read from the `EIA_API_KEY` environment variable, or from a one-line file at
  `%USERPROFILE%\.headwind\eia_api_key.txt` (another path with `HEADWIND_EIA_KEY_FILE`). On this machine Tom set
  it on 13 Nov as a user-level environment variable; there is no key file. A shell opened before that does not
  have it: in PowerShell run `$env:EIA_API_KEY = [Environment]::GetEnvironmentVariable('EIA_API_KEY','User')`
  first. Never print the value. A scheduled run needs the key as a secret.
- **EIA takes the key only in the URL.** `eia_url` builds the request without it, the lane adds it as the request
  is sent, and the recorded URL, the raw-copy index and any error text stay keyless (there is a test for each).
- **With no key the lane fails** and keeps its last good copy, like any failed lane.
- **Proven against EIA on 13 Nov 2026.** The routes (`petroleum/pri/spt`, `natural-gas/pri/fut`), series ids and
  row fields worked as written. EIA's reply echoes the request without the key, and the key was searched for in
  the raw copies, `index.jsonl` and the snapshot and not found. The two test fixtures (`eia_petroleum.json`,
  `eia_natural_gas.json`) are that day's real replies, cut to the last 300 rows of each series.
- Two requests a run (one per EIA dataset), about 1,100 rows; EIA's limit is 5,000 rows a request.

## Screening lists (`headwind-1.3`)
- **Same measure as the sanctions lane**, one change item per list: entries added and removed between two readings,
  counted by the address country the list gives, and by program where the list has programs. State is in
  `data/state/screening_index.json` (about 530 KB) and has to be carried between runs.
- **The SDN list is skipped** because the sanctions lane reads it from OFAC directly.
- **Entry ids:** Treasury's lists carry OFAC's own numbers. The BIS and State lists carry a long hash that trade.gov
  assigns. Whether that hash changes when a publisher edits an entry is not known; if it does, an edit shows as one
  removed and one added. The page and the feed say so. Check it when the first real change arrives.
- **A list named in the file with no entries** (Foreign Sanctions Evaders on 13 Nov) is kept as an empty list, so its
  first entry is seen as an addition. A list of 20 or more that loses over half its entries fails the lane.
- **The raw copy is stored gzipped** (2.8 MB against 34 MB). trade.gov re-imports hourly and stamps the file, so every
  run stores a new copy.
- **US persons:** the Denied Persons List is mostly US addresses (1,106 of its address records). Counts only is why
  `us_person_data` stays `none`; publishing names would change that.

## Minerals (`headwind-1.3`)
- **Annual context, like the baseline lane: not in the feed.** USGS's Figure 2 table gives net import reliance for
  2025 for 68 commodities; its Figure 3 table gives import shares by country for 2021-24 for 47.
- **Figures are copied as printed**, including bounds such as ">75". Figure 3 gives a bare number where Figure 2
  prints a bound; `reliance_as_printed` takes the printed form from Figure 2 when the two numbers agree.
- **The only derived number** is a count: how many commodities name each country first among major import sources
  (China 18, Canada 10, South Africa 7 of the 65 with sources given).
- **`Critical_Mineral` in USGS's Figure 3 table is not used.** The metadata does not define it and it is "N" for
  arsenic, natural graphite, niobium and tantalum, which are on the 2025 list. It is kept as `usgs_flag`. Headwind does
  not yet carry the 2025 critical minerals list itself (60 minerals, Federal Register 2025-19813, 7 Nov 2025).
- **`ITEM_ID` in `minerals.py` is the 2026 edition** and has to be changed by hand when USGS publishes the next
  Summaries (the 2026 one came out on 6 Feb 2026).
- Each CSV is checked against the MD5 that ScienceBase lists for it. `.gitattributes` keeps the two fixture CSVs
  byte for byte so that test passes on any checkout.

## Rules
- **Standard library only** (Python 3.11+).
- **Raw copies** go to `data/raw/<source>/<sha12>.<ext>` with a line in `data/raw/index.jsonl`. Git-ignored;
  about 150 MB after one run, nearly all WFP files. A WFP file is fetched again only when HDX's
  `last_modified` changes.
- **`data/snapshot.json` is the last-good store.** A scheduled build has to carry it between runs or a failed
  lane goes empty.
- **Anomaly items carry no `indicator_id`.** The contract ties an indicator to a hypothesis, and Headwind has no
  warning problem for economic stress yet. `HW-IND-4` to `HW-IND-6` are registered for when Tom writes one.
- **No judgments in the feed.** The seed build's sanctions and rule blocks carried a fixed 0.85 probability and
  invented test records (`MADE_UP`); both are removed. `commodities.py` (the old IGC lane) is unused.
- A rate decision is exported to Verdict as kind `rule_date`, the nearest kind Verdict accepts.

## Not done
- **Planned and not built:** Census trade data for minerals (needs a key), the critical minerals list itself, EU
  and UK sanctions lists, USTR notices, Federal Register public inspection.
- **A list change is only an added or removed id.** An entry that stays on a list and changes its programs or type
  is not reported, in either list lane.
- `HW-EEI-1` and `HW-EEI-2` (vessel matches in Wake, public-inspection filings) are unmet. Headwind now carries
  the IMO numbers `HW-EEI-1` needs; the match itself is not built, and Wake is seed data only.
- Page layout was checked on 13 Nov at 1280 and 375 pixels wide for the sanctions, rules, screening and minerals
  sections. Fixed then: links had no colour set (browser blue on the dark panel), date badges stretched and wrapped,
  and the rules card listed all 25 documents (now six, with the rest behind a control). Wide tables scroll sideways
  on a phone.
- **The house bar and Time menu were looked at on 13 Nov** (about 10:30 AM CST) at 1024 and 375 pixels wide, light
  and dark, served by `tools/serve.py` with the CSP: no console errors and no CSP violations, no sideways scroll on a
  phone, and the Time menu changes every time on the page. Two faults were fixed in `site_src/style.css`: the page
  was dark only while the house bar's panel follows the viewer's setting, and the Time dialog's text was dark on
  the dark panel because `tic-time.css` reads `--ink` and `--line`, which the page did not define. The page now
  follows the viewer's light or dark setting. The preview entry is `headwind-site` in `[local path]`.
- **Full collect 13 Nov, 10:28 AM CST:** all ten lanes current (EIA timed out once at 60 s and passed on a second
  try), 60 feed items, `check` PASS. Still no list change: the OFAC and UN files are byte for byte the same as on
  12 Nov, and trade.gov's file changed its bytes but none of its 6,702 entries.
- **First real list change, seen locally 14 Nov, 2:26 PM CST:** OFAC SDN 19,563 to 19,565, 2 entities added
  (SDGT 2, FTO 1, ILLICIT-DRUGS-EO14059 1), no countries (conduct programs), no vessels. It matches OFAC's 13 Nov
  "Counter Narcotics and Counter Terrorism Designations". The live site will never report it: the runner's
  baseline (13 Nov, 10:43 AM CST) was set after OFAC published. The change item and feed text read right; vessel
  names and trade.gov's entry ids are still untested. `check` PASS, all ten lanes ok.
- **The workflow** (`.github/workflows/update.yml`) follows Blackout's: tests, state from the Actions cache,
  `collect`, `build`, `check`, state saved, then `wrangler pages deploy`. **It does not publish state** (Tom, 13
  Nov: go with the recommendation): the list indexes hold the publishers' entry ids for people, and people are
  counts only, so `data/snapshot.json` and `data/state/` are kept in the repository's Actions cache
  (`actions/cache/restore` and `save` v6, key `headwind-state-<run id>`, newest entry restored). GitHub drops an
  entry unread for 7 days; with none, a run is a first reading and says so in a warning. State is saved before the
  deploy, so a failed deploy does not lose a change. `restore --from` and `build --publish-state` stay in the CLI,
  unused by the workflow; `restore` exits 1 when a site cannot be reached, and a missing file (404, or a page in
  place of JSON) is a first reading. The repo is private, so runs use Actions minutes (a run takes about 1 min
  15 s). `site_src/_headers` carries the CSP and CORS on `/data/*`.
- `tic-time.js` v1.3 is on the page since 13 Nov, copied from the hub's `site/shared/`: times show in the viewer's
  zone with the zone named, and data dates as dates.
- US inflation and jobs dates: bls.gov refused automated requests (403). IMF's data API also refused (403).
- No fixed baseline beside the rolling one. No Wayback capture of sources.
- Vintages are kept for FAO only (the last twelve months as issued, in each snapshot).
- COP's freshness window for Headwind (fresh 24 h, stale 72 h) will trip over a long weekend, because the
  ECB publishes on business days only.

## Licences (unverified unless marked)
- WFP on HDX: CC BY-IGO, read from HDX's own metadata on 12 Nov 2026.
- FAO: its database terms page, read 13 Nov 2026, gives CC BY 4.0 unless a dataset's own page says otherwise, with
  a set citation form and a bar on use "for or in conjunction with the promotion of a commercial enterprise". The
  Food Price Index page, read the same day, showed no licence statement to the reader. Since 13 Nov the feed,
  page and `sources.json` say CC BY 4.0, as the database terms do (Tom: go with the recommendation); the seed
  build's CC BY-NC-SA 3.0 IGO had no source. FAO's set citation form is not yet used on the page.
- ECB: its disclaimer page, read 13 Nov 2026, allows free use with the ECB cited as the source, and says a change
  to the figures must be stated. Headwind restates the rates per US dollar; the page footer says so (13 Nov).
- World Bank: CC BY 4.0 is the default for its own datasets (licence page read 13 Nov 2026; it does not name WDI).
- Federal Reserve: its disclaimer page, read 13 Nov 2026, says website information is in the public domain unless
  marked otherwise and asks that the Board be cited.
- Federal Register: the National Archives' page about it, read 13 Nov 2026, says everything that appears in the
  Federal Register may be reproduced without restriction. federalregister.gov itself turned the reader away.
- OFAC list: a US government work, stated from memory. Treasury's site-policies page had no reuse statement.
- **UN Security Council list: the open one.** The UN's website terms of use, read 13 Nov 2026, allow copying for
  personal, non-commercial use and withhold the right to redistribute or make derivative works. The list page
  states no licence of its own. Headwind publishes only counts taken from the list and a link to it, never its
  content, and since 13 Nov does not publish its index of the list either. Tom, 13 Nov: that is enough to deploy
  (the recommendation); asking the UN is still open as a courtesy.
- USGS Mineral Commodity Summaries data release: CC0 1.0, read from the ScienceBase record on 13 Nov 2026.
- trade.gov Consolidated Screening List: a US government work, stated from memory. Its page, read 13 Nov 2026,
  states no terms of reuse.
- Energy: EIA's reuse page, read 13 Nov 2026, says US government publications are in the public domain and asks
  for credit as "Source: U.S. Energy Information Administration" with a date. EIA's API terms of service, read
  the same day, allow building a service that displays and analyses its data, ask that EIA be named as the source,
  and bar implying its endorsement or changing content while still crediting EIA. The lane left FRED on 13 Nov because FRED's legal page bars scraping and passing stored content on; the
  snapshot's energy rows have come from EIA since 9:35 AM CST that day. Old FRED raw copies are still under
  `data/raw/eia-spot-fred/` (git-ignored).
