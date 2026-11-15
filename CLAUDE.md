# Headwind (`D:\Projects\headwind`)

Economic stress for The Intelligence Company (`tic-feed/2`, program id `headwind`, prefix `HW`): currencies,
energy and food prices measured against their own normal range, changes to official sanctions and US screening
lists, export-control, sanctions and trade rules (BIS, OFAC, USTR) and their filings on Federal Register public
inspection, US import reliance for minerals, plus a calendar of dates for Verdict. Measurements only. No
probabilities, no investment advice.

**State, 15 Nov 2026, 12:25 PM CST: step 10 and HW-WP-2 done, nothing pushed; hand-over for steps 11 to 16.**
Committed on `live/first-slice`, not pushed: `5a996d8` (step 10: USTR documents, the register of scheduled dates,
the `inspection` lane for Federal Register public inspection, HW-IND-2 measured; method `headwind-1.6`) and the
HW-WP-2 commit (register 1.2; anomaly items carry `HW-IND-4` to `HW-IND-6`), with this note. 56 tests pass, check
PASS. Still waiting from before: `d320d8e`, `0ec47f2`, `ce03e81`, `08c0caa`. `origin/main` has `0814445` (house bar
tic-nav v1.12, another session's) that `live/first-slice` does not: merge it before pushing. **Verdict:** `main` holds
`800efd6` and the merge `4454345` (origin/main's pre-EASA guards kept beside the Headwind sync; asked for by the
Verdict pre-EASA session, 33 tests, `check --base origin/main` PASS); pushed by the Verdict session on Tom's yes at about 12:10 PM CST, so `origin/main` is `4454345` and nothing of Verdict waits. Verdict `main` now has a ruleset blocking force-push and deletion, with squash and rebase merges off. The method
bump to `headwind-1.6` covers everything in this batch, since none of it is deployed yet. Next, in order, each
built, tested, checked and committed before the next, nothing pushed until Tom says so:
- **Step 11, currency gap.** ECB covers only PH of the 19 watched countries. The WFP files already downloaded
  (`data/raw/wfp-prices-*`) carry exchange rates, many unofficial, for CD, LB, SD, SO, SS, YE; World Bank GEM (WDI
  source 15) has monthly official rates. Then a per-country view. HW-IND-4 attaches to watched countries only
  (`feed.WATCHED`), so new rates widen it.
- **Step 12, World Bank Pink Sheet** (fertilizers, ten critical-list metals). Confirm its licence first; stop and
  ask Tom if it does not allow reuse.
- **Step 13, anomaly rule for designation batches** (EU, UK and Entity List files carry designation dates; OFAC
  needs Headwind's own readings).
- **Step 14:** adopt the kit history log (`tic-history/1`, `doctrine/kit/docs/history-log.md`); add the ended URL
  to COP's config (`D:\Projects\cop`, read its CLAUDE.md).
- **Step 15:** COP reads per-source health from Headwind's feed (COP repo).
- **Step 16:** Census trade data for minerals. Check that the user-level `CENSUS_API_KEY` is set (read it like the
  EIA key, never print it); if not, give Tom `gh secret set CENSUS_API_KEY --repo metacog-osint/headwind` and the
  user-level command, and skip.
- Then update Headwind's row and step 13 in `D:\Projects\_ideas\new-programs.md` and list each repo's commits ahead
  (`git log origin/<branch>..<branch>`, as its own step) for Tom's yes.

**State, 15 Nov 2026, 9:35 AM CST: steps 7, 8 and 9 done, nothing pushed.** Commits waiting for Tom's push at the
end: Headwind `d320d8e` (step 7), `0ec47f2` (notes), `ce03e81` (step 9, ships across lists) and this notes commit,
on `live/first-slice`; **Verdict `800efd6` on `main`** (step 8: `calendar --sync headwind`, the daily workflow pulls
Headwind's events after Cordon's and only warns if Headwind fails; a Federal Register document number links
forecasts like a CZIB number; kit 0.5.2 synced, so Headwind is listed live; 23 Verdict tests pass, the dry run merged
all 11 of Headwind's events with no calendar problem). Headwind's `question_drafts.json` is still read by nothing:
a Verdict draft needs a probability Tom approves, and Headwind's drafts carry only a base rate. Next: step 10, then
HW-WP-2 into the register, 11, 12, 13, 14, 15, 16, as listed below. Before pushing, list what is ahead in each repo
(Verdict's `main` is shared with other sessions; a worktree `D:\Projects\_worktrees\verdict-pre-easa` exists).

**State, 14 Nov 2026, 10:00 PM CST: working through the remaining plan** (Tom: "complete all remaining open and
incomplete items"; commit each step once tests and check pass, **push nothing until Tom says so at the end**, in any
repo). Done: **step 7** (`d320d8e`, watch for the next USGS Summaries and a newer critical minerals list; see
Minerals), committed on `live/first-slice`, not pushed. Stopped at 92% of the 5-hour usage window. Next, in this
order: step 8 (Verdict repo: calendar sync reads Headwind's `events.json`, kit copy 0.4.2 still calls Headwind
planned), 9, 10, 11, 12 (confirm the Pink Sheet licence first), 13, 14 (kit history log; COP config gets the ended
URL), 15 (COP repo), 16 (Census). Tom's decisions for the rest:
- **HW-WP-2: add it to the register** (`doctrine/indicators.json`) and tie `HW-IND-4` to `HW-IND-6` to it, so
  anomaly items carry indicator ids. The 14 Nov draft is in no file; write it fresh from the indicators Headwind has.
- **Census key:** Tom has one and sets it himself as the user-level `CENSUS_API_KEY` and the repo secret
  `CENSUS_API_KEY` (`gh secret set CENSUS_API_KEY --repo metacog-osint/headwind`). Read it like the EIA key; never
  print it. Not yet confirmed set.
- **HW-H-1B review (first pass, from the registers only, not checked against current events):** (1) the title
  states an intent, "calibrated diplomatic truce", that no indicator can show; a neutral form is "BIS or USTR
  extend stays or suspensions ahead of scheduled deadlines". (2) Its only emerging indicator, `HW-IND-2`, needs
  USTR notices and Federal Register public inspection, which Headwind does not read (step 10), so `collectable`
  is true on paper only. (3) `HW-IND-1`'s `dual_use_network == true` is not something Headwind computes (people and
  organizations are counts only), so only its vessel half is collectable; `HW-IND-1` and `HW-IND-2` are the two
  halves of every hypothesis, so H-1A and H-1B are mirror images and H-1C (artefact) has no emerging indicator.
  Rewording needs Tom's yes.

**State, 14 Nov 2026, 9:10 PM CST: `headwind-1.5` live** (Tom: push, keep the method bump, delete `tic-nav-v1.10`,
update the plan file without committing it). `9fbc526` is on `main` and `live/first-slice`; run 43670866655 (9:07 PM
CST) passed every step and deployed: all ten lanes ok, 60 items, 13 health entries (4 fresh, 9 up), check PASS, state
from cache key `headwind-state-43664358348-1`, saved as `-43670866655-1`. It logged "uk-sanctions: vessel details
were kept in an older form; not compared this run" once in collect, as expected; the run after it should not. Still
no list change on the live site (0 sanctions and 0 screening changes; baselines unchanged). The local branch
`tic-nav-v1.10` is deleted. Headwind's row and step 13 in `_ideas/new-programs.md` were brought up to date, not
committed. The paragraph below is the state before this.

**State, 14 Nov 2026, 8:45 PM CST: `headwind-1.5` committed on `live/first-slice`, not pushed or deployed** (plan
step 6, Tom's "Start with step 6", then "Commit"). The stale worktree `headwind-nav110` was removed the same
evening (Tom's yes). Vessel naming was tested on real UK changes: six Wayback copies of the UK Sanctions List (1 Oct
to 12 Nov 2026) run through Headwind's own code and checked against FCDO's notices. Two faults found and fixed: UK
ship names came out as FCDO's "IMO n (NAME)" form, and a ship FCDO revoked and remade under a new id showed as
removed and added. See "UK ships and step 6" below. 41 tests pass. `ce7f31b` (EU `UKR` and `SDNZ`) is live
(run 43664358348, 7:42 PM CST). The paragraph below is the state before this.

**State, 14 Nov 2026, 7:30 PM CST: `headwind-1.4` live** (Tom's "Build items 1-5", then yes to commit and to push).
Source health in the feed and on the page, one fetch retry, drift checks, edits to entries that stay on a list
(and re-keyed trade.gov entries), kit 0.5.2 with a kit test, and a second private copy of the run state in the
release `state`. See "Source health and state (`headwind-1.4`)" below. `6865f16` is on `main` and
`live/first-slice`; run 43662609087 (7:20 PM CST) passed every step and deployed: 60 items, 13 health entries
(4 fresh, 9 read), state restored from the cache, and the `state` prerelease created with `headwind-state.tar.gz`
and `headwind-state-2026-11-15.tar.gz` (468 KB each). 38 tests pass. Drift checks start after three readings. Still
open for Tom: COP reading per-source health (a COP change) and the stale worktree `D:\Projects\_worktrees\headwind-nav110`. The paragraph
below is the state before this.

**State, 14 Nov 2026, 3:40 PM CST: live and updating itself.** Ten lanes, method `headwind-1.3`; the sanctions lane
reads four lists (OFAC, UN, EU, UK) since `df39196`, and the minerals lane carries the 2025 critical minerals list
since `b528333`. `main` and `live/first-slice` are both `622f78b` and pushed (run 43642037862 deployed it; EU and UK
baselines set on the runner at 3:18 PM CST). Hub: tic-doctrine 0.5.2 (`3bffa17`) and COP's kit sync (`4ceecd5`,
deployed) carry Headwind's new terms and owns. Open for Tom then: EU `UKR` and `SDNZ` (decided 14 Nov, see the EU and UK lists); the stale worktree `D:\Projects\_worktrees\headwind-nav110`. A push to `main` runs the workflow,
which collects, builds, checks and deploys. The house bar lists Headwind and the suite registry lists it as live
(see Deploy). Untracked and to stay that way: `GEMINI.md` and `data/`. Commit history before the deploy:
`ed4e461` first live slice, `472e802` sanctions and rules (`headwind-1.2`), `921d8f6` screening and minerals
(`headwind-1.3`), `14e3501` energy from EIA, `da87b11` vessels and house bar, `39819ab` light and dark theme,
`3281d97` state in the Actions cache and FAO's licence.

**Planned scope** (`D:\Projects\_ideas\new-programs.md`, program row and roadmap step 13): sanctions, export
controls, prices, currency and energy, with critical minerals, trade.gov screening-list diffs and UN list deltas
(needs a Census key). Built so far: prices, currency, energy, OFAC, UN, EU and UK list changes, BIS and OFAC rules, trade.gov screening-list
changes, USGS mineral import reliance and the 2025 critical minerals list. Not built: Census trade data for minerals (needs a key, which Tom
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
- **tic-dispatch starts the workflow** (seen 14 Nov 2026: `workflow_dispatch` runs at :50 past 03, 09, 15 and 21
  UTC). The 6-hourly cron stays as a fallback.

## Commands

```bash
python tools/headwind.py collect              # fetch every live lane into data/snapshot.json
python tools/headwind.py collect --only fx    # one or more lanes; the rest keep their last copy
python tools/headwind.py build                # build site/ from data/snapshot.json
python tools/headwind.py check                # validate the registers and lint the feed
python tools/headwind.py restore --from URL   # a scheduled run: read the last state from the published site
python -m unittest discover -s tests          # 64 offline tests against real fixtures
python tools/serve.py                         # site/ on http://127.0.0.1:8751 with the headers in _headers (CSP)
```

`collect` never falls back to made-up data. A lane that fails keeps its last good copy (`from_previous`) or stays
empty, and `lanes` in the snapshot says which. `build` refuses to run without a snapshot.

## Lanes

| Lane | Module | Source (all keyless) | Checked live 12 Nov |
|---|---|---|---|
| `fx` | `markets.py` | ECB reference rates, history zip; restated per US dollar | 29 currencies |
| `gem` | `markets.py` | World Bank Global Economic Monitor (WDI API source 15, `DPANUSSPB`), official rate per US dollar, monthly average, the 19 watched countries in one request | 15 Nov: 16 countries with a rate (5 with old data: IR Jan 2026, MM Mar 2024, SD Oct 2024, SO Jun 2018, VE Nov 2025), CU, PS, SS none; World Bank updated 8 Sep 2026, newest month Aug 2026 |
| `energy` | `markets.py` | EIA's own API v2 (Brent `RBRTE`, WTI `RWTC`, Henry Hub `RNGWHHD`). **Needs a free EIA key** | 13 Nov, 9:35 AM CST: 3 series to 11 Nov (Brent 92.14, WTI 89.62, Henry Hub 3.00), the same prices FRED gave |
| `fao` | `food.py` | FAO Food Price Index CSV; the link is read from FAO's page because it changes | 6 indices |
| `wfp` | `food.py` | WFP prices by market from HDX, for the countries in `config/wfp_countries.json` | 18 of 19 countries; Cuba has no file, Venezuela's newest month is May 2025 |
| `baseline` | `baseline.py` | World Bank WDI API, six indicators | 213 countries. The API timed out twice earlier the same evening |
| `calendar` | `releases.py` | Federal Reserve and ECB schedule pages; FAO release dates | 9 events in the next 180 days |
| `sanctions` | `sanctions.py` | OFAC `sdn.csv` (5.8 MB), the UN Security Council consolidated list (XML), the EU's Financial Sanctions Files (XML, 26 MB) and the UK Sanctions List (XML, 22 MB) | 14 Nov, 2:57 PM CST: 19,565 OFAC (1,570 vessels), 1,007 UN, 6,269 EU, 6,440 UK (694 ships). The EU download takes 30 s to 2 min |
| `screening` | `screening.py` | trade.gov Consolidated Screening List (one 34 MB JSON), every list but the SDN list | 13 Nov, 8:46 AM CST: 12 lists, 6,702 entries (Entity List 3,419). First reading, so no change to report yet. The download took 4 s |
| `controls` | `controls.py` | Federal Register API: BIS, OFAC and USTR rules and proposed rules and USTR notices, last 60 days; the same agencies' documents of the last 800 days for the register of scheduled dates | 13 Nov: 25 rules; 2 future dates for Verdict (3 Dec polysilicon rule ends, 10 Jan 2027 affiliates-rule stay ends). 15 Nov: 34 rules and USTR notices, 18 scheduled dates |
| `inspection` | `inspection.py` | Office of the Federal Register, public inspection: the issues of the last 5 days (30 on a first run or after a gap), BIS, OFAC and USTR filings, and each rule's or USTR notice's text | 15 Nov: 30 days read, 26 filings (17 notices counted only); HW-IND-2 met by BIS 2026-22793 and USTR 2026-22925 and 2026-22867 |
| `minerals` | `minerals.py` | USGS Mineral Commodity Summaries 2026 data release on ScienceBase (item JSON, then two CSVs) | 13 Nov: 68 commodities with net import reliance, 47 with import shares by country |

The sanctions lane was read three times on 13 Nov (to about 9 AM CST) and both files were byte-for-byte the same as
on 12 Nov, so Headwind has still not seen a real list change. The trade.gov file says OFAC last updated on 9 Nov.

Outputs in `site/data/`: `feed.geojson` (60 items on 13 Nov), `events.json` (Verdict's `sync_calendar` format),
`baseline.json` and `minerals.json` (not in the feed), `question_drafts.json` (drafts only), `snapshot.json` (what
the page reads).

## Currencies of watched countries (plan step 11, built 15 Nov 2026, `headwind-1.6`)
- **Three readings per country.** ECB daily (PH; PS shows the shekel in the country view only, its feed item
  stays Israel's), World Bank GEM official monthly average (`gem` lane, `fx_official`), WFP market rates
  (`food.measure_wfp_fx`, in the `wfp` lane, `market_fx`; nested as `market_fx` in each `local_food` record for the
  HDX cache). GEM: 1 month against 60, 2% floor, more than four months old is stale (listed, not in the feed).
  WFP market: median one-month change across markets, from one market up, 5% floor; `split` when the highest
  market rate is over 1.5 times the lowest (Somalia: 11,000 to 50,000, Somaliland's and Somalia's shillings), and
  then no level and no comparison. `unofficial` when WFP labels any series so.
- **Exchange-rate rows left WFP's food median** (`food.is_fx_row`). Small moves on 15 Nov: SD 50.1 to 50.0, SO
  0.7 to 0.6, SS 1.1 to 0.0, YE 1.9 to 2.1, CD's series 1,307 to 1,249. Covered by the `headwind-1.6` bump.
- **Feed items** `headwind:fxofficial:<cc>:<month>` (source `worldbank-gem`, new in `sources.json`) and
  `headwind:fxmarket:<cc>:<month>` (WFP's dataset); both `HW-IND-4` and `HW-H-2A` when anomalous, anchor
  `#countries`. Month ends never date an item after the collection (`feed._month_end_by`, now used for local food
  too).
- **Country view** (`feed.country_view`, snapshot `country_view`, page section `#countries`): per watched country
  the daily, official and market rates, market against official (the newest month both give, from each record's
  `recent` 13 months), local food, and `indicators_present`. Nothing is combined into a score.
- **Live 15 Nov, 12:40 PM CST:** one anomaly, Sudan's unofficial market rate (Khartoum, WFP) 23.3% weaker in Oct
  2026, z +5.1, so Sudan carries `HW-IND-4`. Market against official: CD +0.8%, LB +0.1%, YE +555.1% (GEM's Yemen
  figure is about 238 per dollar and flat; WFP's markets, Aden's side, about 1,556; which rate GEM reports is not
  verified). Health: `worldbank-gem` fresh (window 100/160 days after the month's end).
- **Not covered:** Cuba (no WFP file, no GEM rate); BF, ML, NE use the CFA franc, pegged to the euro, which GEM
  gives; the peg is not derived from the ECB's euro rate.

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
- **EU and UK lists (added 14 Nov 2026).** EU: the Commission's Financial Sanctions Files, XML v1.1, keyed on each
  entry's `logicalId`, grouped by programme code (34 codes); people and enterprises only, because EU vessel measures
  sit in regulation annexes, not in this file. The EU file was last generated 23 Oct 2026 (the Commission's RSS feed
  says the same), so it changes less often than OFAC's. UK: the FCDO's UK Sanctions List, the only UK list since
  OFSI's Consolidated List closed on 28 Jan 2026, keyed on `UniqueID`, grouped by regime short name (`uk_regime()`,
  31 regimes). UK ships are named like OFAC vessels (name, IMO, flag, type; owners left out); 693 of 694 have an
  IMO number. Countries come from per-list maps, `EU_PROGRAMME_COUNTRY` and `UK_REGIME_COUNTRY`, with the conduct
  regimes left unplaced on purpose (`EU_UNPLACED`, `UK_UNPLACED`). Tom's decisions, 14 Nov 2026: EU `UKR` (Ukraine's
  territorial integrity) is placed on Russia only (1,609 of its 2,962 entries give Russia, 86 Ukraine), and EU
  `SDNZ` on Sudan (Sudanese and UAE addresses; cites EU Sudan acts such as 2024/384). A code or regime in neither map nor the unplaced set shows as
  `unknown_programs` on the list's status: add it to a map. First readings on the runner set the baselines.
- **Each list stands alone** (since 14 Nov): a list that cannot be read or parsed keeps its index from the run before
  and shows the error on the page; the lane fails only when no list can be read.
- **Rules:** a document stays in the feed 14 days. Future dates come from its effective date, its comment
  deadline, and dates written out in its DATES paragraph (`named_dates`); each becomes a `rule_date` for Verdict.
  Countries are only those a title names. USTR's notices are read since step 10 (see below).
- **Rules are tier `routine`; a list change is `anomaly` only when one of its designation batches is** (plan step
  13, `headwind/batches.py`; see "Designation batches" below).

## Designation batches (plan step 13, built 15 Nov 2026, `headwind-1.6`)
- **A batch is the entries a list gives one designation date**: EU `designationDate` (5,698 of 6,269 entries on
  15 Nov), UK `DateDesignated` (all 6,440), UN `LISTED_ON` (all 1,007), and trade.gov's `start_date` (Entity List
  3,266 of 3,419; also DPL, MEU, ACN). The parsers fill an optional `dates` dict; dates are never kept in the index,
  the state or the feed. When a change adds entries, each designation date among them is measured: its size (all
  entries on the list with that date, now) against the list's 60 earlier designation dates, robust z on the log
  of the size, unusual at z >= 3.5 (upward only) and at least 10 entries (`BATCH_FLOOR`). The scale never drops
  below log 2 / 3.5, so the UN's one-entry dates give a batch of 2 a z of 3.5; the floor keeps it routine.
- **OFAC has no dates** (and a change whose added entries carry none): the batch is what Headwind saw added
  between two readings, against `added_history` (up to 120 earlier changes seen, kept per list in
  `sanctions_index.json` and per screening list in `screening_index.json`). It starts empty, so OFAC shows "no
  baseline yet" until 24 changes are kept. A rekeyed vessel is not an addition.
- **On the delta:** `batches` (basis, date, added, size, z, baseline_n, flag_rate, anomaly) and `anomaly`. Feed: tier
  `anomaly` with `baseline_ref`, a "Designation batches: ..." sentence, `measures.batch_size_max` and
  `batch_z_max`; no indicator id (none in the register fits; HW-IND-1 is vessels in a dual-use network). Page:
  "unusual" badge, a batches line, and the "Unusual now" list.
- **Backtest on the 15 Nov files** (every date with 24 earlier): EU 2 of 401 dates flagged (2005, 2008), UK 8 of 430
  (April and June 2021, 24 Feb 2022 and the 11 and 15 Mar 2022 Russia batches of 382 and 357), UN 1 of 225 (Sep 2014),
  Entity List 0 of 122. The EU's 213 entries of 23 Jul 2026 are z +2.0 (large EU packages are its usual). Past
  batches are counted from today's file, so delisted entries are missing from them.
- Live 15 Nov: no list change on either lane since the code went in, so no batch has been measured on a real change.

## UK ships and step 6 (`headwind-1.5`, built 14 Nov 2026)
- **FCDO names many ships by IMO number.** The primary name is `IMO 9344411 ("GALLE ENERGY")` (quotes or none;
  54 of 694 ships on 12 Nov) or `IMO 9958303` alone with the ship's name only as an alias (11, all from the 12 Nov
  notice). `uk_ship_name()` takes the name in brackets, else the first alias that is not an IMO number, and marks
  the second case `name_is_alias` (shown as "alias" in the feed and on the page). Other primary names are kept as
  printed. Checked on both the 1 Oct and 12 Nov files: every ship has a clean name; one has no IMO number.
- **A ship remade under a new id is one entry** (`rekeyed_vessels()`): a vessel that goes and one that comes on the
  same list with the same IMO number, that number on no other vessel going or coming, counts once (`rekeyed`,
  `vessels_rekeyed` with `old_id`) and is compared as one entry, so a move between regimes shows as programs
  gained and lost. Applies to every list with vessels (OFAC too). Title: "..., 2 under a new id".
- **`vessel_format`** in each list's state (`sanctions.VESSEL_FORMAT`, UK = 2): a reading kept in an older form is
  not compared field by field, so the change of name form is not reported as 65 ships renamed. **The first run after
  this deploys** will log "uk-sanctions: vessel details were kept in an older form; not compared this run" once;
  additions, removals and re-key pairing still work that run.
- **What the Wayback copies showed** (1 Oct 15:38 UTC to 13 Nov 14:54 UTC; files generated 1 Oct to 12 Nov): 75
  added, 5 removed, 2 under a new id. Every figure matches FCDO: Russia notices of 2 Oct ("2 additions, 2
  corrections, 2 revocations": RUS3739 and RUS3747 revoked, remade as RUS3752 BEBEK-E and RUS3751 GALLE ENERGY), 8 Oct
  (38 additions: 26 designations, 12 ships) and 12 Nov (20 additions: 9 entities, 11 ships); and the GOV.UK change
  notes for Iran (+2, 12 Oct), Iraq (−1, 7 Oct), Syria (−1, 6 Oct), Sudan (+15, 26 Oct) and ISIL/Al-Qaida (−3, 27
  Oct). GOV.UK's change note for 12 Nov says "11 new designations, 9 new specifications"; the notice itself and the
  list give 9 entities and 11 ships, so the note has them swapped. Trust the notice PDF over the change note.
- **Not seen, by design:** FCDO "variations" and "corrections" (12 Nov, 16 and 27 Oct ISIL, 3 Nov) change details of
  people and organizations, which Headwind does not compare (type and regime only). They show as no change.
- **Fixtures** `uk_ships_2026-10-01.xml` and `uk_ships_2026-11-12.xml` are cut from those Wayback copies with each
  Designation kept as published (tests in `TestUkShips`). OFAC vessel naming is still untested on a real change: the
  Wayback Machine has no copies of `sdn.csv`.

## Ships across lists (plan step 9, built 15 Nov 2026)
- `sanctions.vessel_crosslist()` matches ships on OFAC and the UK list (`VESSEL_LISTS`) by IMO number after every
  run, from this run's indexes (a list that failed uses its kept index and is named in `from_earlier_run`).
  Snapshot: `vessel_crosslist` (counts, on the page under the list rows) and `vessel_table` (one record per IMO,
  written to `site/data/vessels.json`, about 440 KB, not in the page snapshot). `mark_also_on()` gives each ship in
  a change `also_on`; the feed text says "also on the OFAC SDN list" and the page the same.
- Live 15 Nov, 9:24 AM CST: 1,944 IMO numbers, 304 on both, 1,251 OFAC only, 389 UK only; 15 OFAC entries and 1 UK
  entry give no number; no IMO number has two entries on one list. Names differ in case and spelling between
  lists, so only numbers are matched. Fixtures `crosslist_ofac.csv` and `crosslist_uk.xml`: AN SAN 1 (IMO
  7303803), OFAC 23730 and UK DPR0097, as read 14 Nov.
- Not a method change (no count moves). `HW-EEI-1` (matching designated vessels with Wake's tracks) can use
  `vessels.json`; the match itself is still not built.

## USTR and public inspection (plan step 10, built 15 Nov 2026, `headwind-1.6`)
- **USTR** (`trade-representative-office-of-united-states`) is the third agency of the rules lane: its rules and
  its notices, which is how it publishes Section 301 actions and exclusions. Notices about the office itself
  (`controls.ADMIN_TITLE`: Performance Review Board, Privacy Act, meetings) are left out. The lane now makes four
  Federal Register requests: rules (60 days, with abstracts), USTR notices (60 days), and the register's two (800
  days, no abstracts; 173 rules and 99 USTR notices on 15 Nov). Records carry `rins` and `dockets`.
- **The register of scheduled dates** (`controls.scheduled()`, snapshot `scheduled_dates`, not published): each
  date a document set (DATES paragraph, effective date, comment close), from 45 days ago on, with the document's
  RINs, dockets and, for USTR, `subject()`: the words after the title's first colon, before any "; ...", without
  small words, so "Notice of Modification of Section 301 Action: China's Targeting of the Maritime, ..." and
  "Section 301 Action: China's Targeting the Maritime, ...; Modification" are one investigation.
- **Public inspection** (`inspection.py`, lane `inspection`, source `fr-public-inspection`). The API ignores the
  agency filter on public inspection (checked 15 Nov), so each issue is read whole (about 100 to 140 filings) and
  filtered. Issues by `available_on`; weekends return none. `days_to_read()`: 5 days after a good reading, back to
  the last good reading after a gap, 30 on a first run. Filings kept 30 days in the snapshot (`inspection`, merged
  by document number, `first_seen_at` kept), 7 in the feed. OFAC's and BIS's notices (sanctions actions, denial
  orders) are `counted_only`, with no title: their titles and texts can name people and companies. For each rule,
  proposed rule and USTR notice the raw text (`raw_text_url`, UTF-8) is read once per `pdf_updated_at` for its
  action line, RINs, docket numbers, the first sentence of its SUMMARY and the dates it says were scheduled
  (`_SCHEDULED`: "was set to end", "scheduled to expire", first date after the phrase); the text is not kept
  (the raw copy is, in git-ignored `data/raw/`). A text that cannot be read is `text_error` on the filing.
- **HW-IND-2** (`inspection.match()`, run in `finish_snapshot`): a BIS or USTR filing whose title, action or
  summary's first sentence makes it a stay, suspension, extension or Entity List filing, with a scheduled date on
  the filing day or up to 14 days after it, from an earlier document of the same agency sharing a RIN, a docket or
  (USTR) the investigation, or named by the filing as scheduled. Feed items `headwind:inspection:<doc>` carry
  `indicator_id` HW-IND-2, `hypothesis_id` HW-H-1B, `direction` supports (present) or neutral, and
  `indicator_state` present, absent or no_data; tier `routine`; `requirement_ids` HW-EEI-2 and HW-PIR-2. OFAC
  filings get no indicator (HW-IND-2 is written for BIS or USTR). Same agency alone is not a match: unrelated
  comment deadlines and effective dates fall within 14 days of most filings.
- **Checked live 15 Nov** on the 30-day backfill: met by BIS 2026-22793 (affiliates-rule suspension extended,
  filed 5 Nov 4:15 PM ET, 4 days before the 9 Nov end set by 2025-19846, RIN 0694-AK34; the filing also says
  "The suspension was set to end November 9, 2026."), USTR 2026-22925 (178 China exclusions extended) and
  2026-22867 (maritime Section 301 action further suspended), both filed 9 Nov, the day 2025-21671 and 2025-19873
  had set. Not met: USTR 2026-22868 (Vietnam investigation extended; nothing scheduled in the register) and
  2026-21755 (filed 23 Oct, 17 days before). HW-H-1B's wording ("calibrated diplomatic truce") is still Tom's to
  change; the items now point at it.
- Fixtures: the 5 and 9 Nov issues cut to the three agencies' filings and one other, four filing texts without
  their contact paragraph, and cut replies for USTR notices and the register (`TestInspection`).

## Source health and state (`headwind-1.4`, built 14 Nov 2026)
- **`health` in the feed and on the page** (`headwind/health.py`). One entry per source, keyed by the source id the
  items carry (`ecb-eurofxref`, `eia-spot`, `fao-ffpi`, `wfp-food-prices-hdx`, `ofac-sdn`, `un-sc-consolidated`,
  `eu-fsf`, `uk-sanctions-list`, `trade-gov-csl`, `us-federal-register`) plus `worldbank-wdi`, `release-calendars`
  and `usgs-mcs`; Cordon's shape (`state`, `last_ok`, `last_error`, `failures`, `checked_at`, `detail`) plus
  `lane`, `data_as_of`, `warnings`, and `error` when failing. States: fresh, late or stale by the source's own
  rhythm (`WINDOWS`: ECB 4/8 days, EIA 7/14, FAO 40/70 and WFP 75/135 after the month's end, capped at today);
  `up` when read with no date to judge; `failing` when not read this run. Each sanctions list has its own entry.
  The kit's history log (`tic.py history`) reads this record as it is: tried 14 Nov on the live build, 61 items
  logged new, nothing ended. **COP does not read per-lane health yet** (it judges Headwind by `generated_at`):
  that is a COP change. The history log itself is not adopted yet (plan item 14).
- **Drift** (`health.DRIFT`): sizes of the last ten good readings per source in the snapshot (`drift_history`).
  From three readings on, under half the median fails the lane for sources parsed from pages or files (fx,
  energy, FAO indices, baseline, the two calendars, minerals), keeping the last good copy; under four fifths, or
  for sizes that move on their own (rules window, WFP countries, FAO release dates, the screening file, which has
  written its index before the check runs), a warning. Warnings go to `health[...]["warnings"]` and, on the
  runner, to `::warning::` lines.
- **Quiet publishers** (`QUIET_DAYS`, `QUIET_SEEN_DAYS`): a warning when the UN file's date is over 3 days old, the
  EU's or UK's over 30, or when OFAC (no file date) has shown no change for 21 days (`last_change_at`, kept per list
  in `sanctions_index.json` and on each list's status). Not a failure.
- **Retry** (`fetch.get`): one more try after 10 s on a timeout, a dropped connection, a 5xx or a 429; never on
  another 4xx. Prompted by EIA's timeouts on 13 and 14 Nov.
- **Edits**: `sanctions.edits` counts ids on both readings whose type or programs changed (programs gained and lost)
  and names vessels whose name, IMO, MMSI, flag or type changed, before and after. `screening` keeps a 12-character
  SHA-1 of each entry's normalised name as a fourth index field (private state only) and pairs a removed and an
  added id with the same name and type as one re-keyed entry (`rekeyed`), then compares them as one. An index
  written before this has no name keys: no pairing that run, and no false edits (only the first three fields are
  compared). Checked 13-14 Nov: trade.gov rewrote the `ids` field of 620 SDN entries with no change of
  substance, which is why only type, programs and address countries are compared.
- **Kit 0.5.2** synced 14 Nov. `tests/test_robustness.py` checks that nothing in `doctrine/kit/` was edited (works on
  the runner) and, when `../tic-doctrine` sits beside the checkout, that the copy is current (skipped on the runner:
  the kit repo is private). Note: `tic-doctrine/tools/sync.py` takes its first argument as the target, so
  `sync.py --help` copies the kit into a folder named `--help` (happened once on 14 Nov; removed).
- **Second copy of the state** (workflow, needs `contents: write`): after the deploy, `data/snapshot.json` and
  `data/state/` go as `headwind-state.tar.gz` and a dated daily copy (14 kept) to the prerelease `state` in this
  private repository. A run restores the Actions cache first, then that asset; with neither it fails (`::error::`)
  unless run by hand with `first_reading` ticked. **Delete the release before the repository is ever made public**:
  the indexes hold the publishers' entry ids for people. Not yet run on GitHub.

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
  assigns. Whether that hash changes when a publisher edits an entry is not known (no BIS or State entry changed
  between the 13 and 14 Nov copies). Since `headwind-1.4` a removed and an added id with the same name and type
  count as one re-keyed entry. Check it when the first real change arrives.
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
  arsenic, natural graphite, niobium and tantalum, which are on the 2025 list. It is kept as `usgs_flag`.
- **The Final 2025 List of Critical Minerals** (60 minerals, 90 FR 50494, document 2025-19813, 7 Nov 2025) is carried
  since 14 Nov as `CRITICAL_2025` in `minerals.py`, a constant, not fetched: a test reads the notice's own sentence
  from `tests/fixtures/fr_critical_minerals_2025.txt` and checks the tuple. Each USGS row gets `critical`, the list
  members it stands for, matched on its first word; "Rare earths" stands for the fourteen rare earths the list names
  one by one; a form ("MAGNESIUM COMPOUNDS", "TITANIUM, sponge metal") is marked with its mineral. All 47 rows of
  USGS's import-sources figure are list minerals; ruthenium is the one list mineral not in it. The reliance table
  has 40 list-mineral rows of 68 and no row for beryllium, boron, hafnium, iridium, metallurgical coal, phosphate,
  rhodium, ruthenium and uranium. `minerals.json` carries the list as `critical_list`. Change the constant by hand
  when a new final list is published (at least every three years).
- **`ITEM_ID` in `minerals.py` is the 2026 edition** and has to be changed by hand when USGS publishes the next
  Summaries (the 2026 one came out on 6 Feb 2026).
- **Watch for both (step 7, 14 Nov 2026).** Each run of the lane also asks ScienceBase for "Mineral Commodity Summaries
  <edition year + 1>" (`SB_SEARCH_URL`; the 2026 search returns 3 items, the edition's own "... 2026 Data Release"
  among them) and the Federal Register for Geological Survey or Interior notices titled with a List of Critical
  Minerals, draft, final or correction, other than 2025-19813 and dated on or after it (`FR_LISTS_URL`; the search
  also returns notices that only share words, such as OCS leasing). A hit is a warning on the `usgs-mcs` health
  entry (`watch_notes`), shown on the page and as a `::warning::` on the runner; a search that fails is a warning
  too, never a failed lane. Kept in `minerals.json` as `watch`. Checked live 14 Nov, 9:51 PM CST: nothing newer.
- Each CSV is checked against the MD5 that ScienceBase lists for it. `.gitattributes` keeps the two fixture CSVs
  byte for byte so that test passes on any checkout.

## Rules
- **Standard library only** (Python 3.11+).
- **Raw copies** go to `data/raw/<source>/<sha12>.<ext>` with a line in `data/raw/index.jsonl`. Git-ignored;
  about 150 MB after one run, nearly all WFP files. A WFP file is fetched again only when HDX's
  `last_modified` changes.
- **`data/snapshot.json` is the last-good store.** A scheduled build has to carry it between runs or a failed
  lane goes empty.
- **Anomaly items carry indicator ids for HW-WP-2** (economic stress in a watched country; added to
  `doctrine/indicators.json` 15 Nov 2026, register 1.2, Tom's decision of 14 Nov): an anomaly for a currency of a
  watched country (`feed.WATCHED`, from `config/wfp_countries.json`) carries `HW-IND-4` and `HW-H-2A`, an energy
  anomaly `HW-IND-5` and `HW-H-2B`, a local food anomaly `HW-IND-6` and `HW-H-2A`; each with `direction`
  supports and `indicator_state` present. Routine items, other countries' currencies and FAO indices (`HW-IND-3`)
  carry none. HW-H-2A is stress within the country (currency and food out of range, energy within), HW-H-2B
  stress from outside (energy shock reaching local food, currency holding), HW-H-2C artefact. `HW-IND-4` and
  `HW-IND-5` are now marked diagnostic (they tell 2A from 2B); `HW-IND-6` is not (expected under both). Written
  from the indicators Headwind has, not checked against current events; the wording is Tom's to change. Until
  step 11, ECB rates covered only PH of the 19 watched countries; since step 11 the World Bank's official monthly
  rates and WFP's market rates carry `HW-IND-4` too (see "Currencies of watched countries").
- **No judgments in the feed.** The seed build's sanctions and rule blocks carried a fixed 0.85 probability and
  invented test records (`MADE_UP`); both are removed. `commodities.py` (the old IGC lane) is unused.
- A rate decision is exported to Verdict as kind `rule_date`, the nearest kind Verdict accepts.

## Not done
- **Planned and not built:** Census trade data for minerals (needs a key). USTR notices and Federal Register
  public inspection are built (step 10).
- **Edits to entries that stay on a list** are reported since `headwind-1.4` (see Source health and state).
- `HW-EEI-1` (vessel matches in Wake) is unmet. Headwind now carries the IMO numbers it needs; the match itself
  is not built, and Wake is seed data only. `HW-EEI-2` (public-inspection filings) is served since step 10.
- Page layout was checked on 13 Nov at 1280 and 375 pixels wide for the sanctions, rules, screening and minerals
  sections. Fixed then: links had no colour set (browser blue on the dark panel), date badges stretched and wrapped,
  and the rules card listed all 25 documents (now six, with the rest behind a control). Wide tables scroll sideways
  on a phone.
- **The house bar and Time menu were looked at on 13 Nov** (about 10:30 AM CST) at 1024 and 375 pixels wide, light
  and dark, served by `tools/serve.py` with the CSP: no console errors and no CSP violations, no sideways scroll on a
  phone, and the Time menu changes every time on the page. Two faults were fixed in `site_src/style.css`: the page
  was dark only while the house bar's panel follows the viewer's setting, and the Time dialog's text was dark on
  the dark panel because `tic-time.css` reads `--ink` and `--line`, which the page did not define. The page now
  follows the viewer's light or dark setting. The preview entry is `headwind-site` in `D:\Projects\.claude\launch.json`.
- **Full collect 13 Nov, 10:28 AM CST:** all ten lanes current (EIA timed out once at 60 s and passed on a second
  try), 60 feed items, `check` PASS. Still no list change: the OFAC and UN files are byte for byte the same as on
  12 Nov, and trade.gov's file changed its bytes but none of its 6,702 entries.
- **First real list change, seen locally 14 Nov, 2:26 PM CST:** OFAC SDN 19,563 to 19,565, 2 entities added
  (SDGT 2, FTO 1, ILLICIT-DRUGS-EO14059 1), no countries (conduct programs), no vessels. It matches OFAC's 13 Nov
  "Counter Narcotics and Counter Terrorism Designations". The live site will never report it: the runner's
  baseline (13 Nov, 10:43 AM CST) was set after OFAC published. The change item and feed text read right; vessel
  names and trade.gov's entry ids are still untested. `check` PASS, all ten lanes ok. UK vessel naming was tested
  on 14 Nov against Wayback copies (see "UK ships and step 6"); OFAC's and trade.gov's are still untested.
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
- World Bank Global Economic Monitor: CC BY 4.0 as the World Bank's default for its datasets (see World Bank
  below); GEM's own licence line was not read separately (unverified).
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
- Final 2025 List of Critical Minerals: a Federal Register notice, so reproducible without restriction (see Federal
  Register above).
- EU Financial Sanctions Files: the EU open data portal's record for the dataset, read 14 Nov 2026, gives the
  European Commission reuse notice (Decision 2011/833/EU) for the XML and CSV files, and CC BY 4.0 for one CSV.
  The decision allows reuse with the source acknowledged. Headwind publishes counts and a link.
- UK Sanctions List: GOV.UK's page for it, read 14 Nov 2026, says all content is under the Open Government Licence
  v3.0 except where otherwise stated. Headwind publishes counts, ship names and a link.
- trade.gov Consolidated Screening List: a US government work, stated from memory. Its page, read 13 Nov 2026,
  states no terms of reuse.
- Energy: EIA's reuse page, read 13 Nov 2026, says US government publications are in the public domain and asks
  for credit as "Source: U.S. Energy Information Administration" with a date. EIA's API terms of service, read
  the same day, allow building a service that displays and analyses its data, ask that EIA be named as the source,
  and bar implying its endorsement or changing content while still crediting EIA. The lane left FRED on 13 Nov because FRED's legal page bars scraping and passing stored content on; the
  snapshot's energy rows have come from EIA since 9:35 AM CST that day. Old FRED raw copies are still under
  `data/raw/eia-spot-fred/` (git-ignored).
