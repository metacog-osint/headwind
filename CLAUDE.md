# Headwind (`D:\Projects\headwind`)

Economic stress for The Intelligence Company (`tic-feed/2`, program id `headwind`, prefix `HW`): currencies,
energy and food prices measured against their own normal range, changes to official sanctions lists, export-control
and sanctions rules, plus a calendar of dates for Verdict. Measurements only. No probabilities, no investment advice.

**State, 13 Nov 2026: the first live slice is committed and pushed on branch `live/first-slice` (`ed4e461`).
The sanctions and rules lanes (method `headwind-1.2`, last run live 12 Nov about 11:55 PM CST) are committed on
the same branch in the commit after it, which is not pushed. Nothing is merged or deployed.** `main` is still the
4 Nov seed snapshot (`36daed6`). Untracked: `GEMINI.md` and `data/`. The site address in the feed
(`headwind.theintelligence.company`) has no DNS record, and the suite registry still lists Headwind as planned
with seed data.

**Planned scope** (`D:\Projects\_ideas\new-programs.md`, program row and roadmap step 13): sanctions, export
controls, prices, currency and energy, with critical minerals, trade.gov screening-list diffs and UN list deltas
(needs a Census key). Built so far: prices, currency, energy, OFAC and UN list changes, and BIS and OFAC rules.
Not built: the trade.gov screening-list diffs and critical minerals. Describe Headwind publicly from what is live.

## Commands

```bash
python tools/headwind.py collect              # fetch every live lane into data/snapshot.json
python tools/headwind.py collect --only fx    # one or more lanes; the rest keep their last copy
python tools/headwind.py build                # build site/ from data/snapshot.json
python tools/headwind.py check                # validate the registers and lint the feed
python -m unittest discover -s tests          # 18 offline tests against real fixtures
```

`collect` never falls back to made-up data. A lane that fails keeps its last good copy (`from_previous`) or stays
empty, and `lanes` in the snapshot says which. `build` refuses to run without a snapshot.

## Lanes

| Lane | Module | Source (all keyless) | Checked live 12 Nov |
|---|---|---|---|
| `fx` | `markets.py` | ECB reference rates, history zip; restated per US dollar | 29 currencies |
| `energy` | `markets.py` | EIA spot prices through FRED's CSV download (Brent, WTI, Henry Hub) | 3 series, one day behind |
| `fao` | `food.py` | FAO Food Price Index CSV; the link is read from FAO's page because it changes | 6 indices |
| `wfp` | `food.py` | WFP prices by market from HDX, for the countries in `config/wfp_countries.json` | 18 of 19 countries; Cuba has no file, Venezuela's newest month is May 2025 |
| `baseline` | `baseline.py` | World Bank WDI API, six indicators | 213 countries. The API timed out twice earlier the same evening |
| `calendar` | `releases.py` | Federal Reserve and ECB schedule pages; FAO release dates | 9 events in the next 180 days |
| `sanctions` | `sanctions.py` | OFAC `sdn.csv` (5.8 MB) and the UN Security Council consolidated list (XML) | 12 Nov, 11:55 PM CST: 19,563 OFAC entries (1,570 vessels) and 1,007 UN entries. First reading, so no change to report yet |
| `controls` | `controls.py` | Federal Register API: BIS and OFAC rules and proposed rules, last 60 days | 12 Nov, 11:55 PM CST: 21 rules; 2 future dates for Verdict (3 Dec polysilicon rule ends, 10 Jan 2027 affiliates-rule stay ends) |

Outputs in `site/data/`: `feed.geojson` (56 items late on 12 Nov), `events.json` (Verdict's `sync_calendar` format),
`baseline.json` (not in the feed), `question_drafts.json` (drafts only), `snapshot.json` (what the page reads).

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
- **Counts only, no names** (Claude's choice, 12 Nov; say if names of entities and vessels should show). The index
  file holds ids, types and programs, never names.
- **A list that parses short or loses over half its entries fails the lane** and is never reported as delistings.
- **`data/state/` must be carried between scheduled runs**, like `data/snapshot.json`, or every run is a first run.
- **Countries on a list change** come from the program name where it names one country (`PROGRAM_COUNTRY` in
  `sanctions.py`; conduct programs such as SDGT are left unplaced). The map was written from memory; check it.
- **Rules:** a document stays in the feed 14 days. Future dates come from its effective date, its comment
  deadline, and dates written out in its DATES paragraph (`named_dates`); each becomes a `rule_date` for Verdict.
  Countries are only those a title names. USTR notices and public-inspection filings are not read.
- **Every list and rule item is tier `routine`.** No anomaly rule exists for them yet: there is no history of
  Headwind's own readings to measure against.

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
- **Planned and not built:** trade.gov Consolidated Screening List diffs (keyless download checked 12 Nov:
  34 MB JSON, 26,265 entries, 13 lists including the BIS Entity List; took 40 to 130 s), critical minerals
  (USGS, Census trade with a key), EU and UK sanctions lists, USTR notices, Federal Register public inspection.
- The new lanes' page sections were checked in a preview for content and console errors only; the layout was
  not looked at, and `HW-EEI-1` and `HW-EEI-2` (vessel matches in Wake, public-inspection filings) are unmet.
- `live/first-slice` is not merged to `main`. That needs Tom's yes.
- No workflow, no Pages project, no DNS, and no place in `tic-dispatch`. Each needs Tom's yes.
- The suite registry (`tic-doctrine/vocab/programs.json`) still describes the seed build and its licences.
- `tic-time.js` and the house bar are not on the page; the page shows the collection time in the viewer's zone
  with the zone named, and data dates as dates.
- US inflation and jobs dates: bls.gov refused automated requests (403). IMF's data API also refused (403).
- No fixed baseline beside the rolling one. No Wayback capture of sources.
- Vintages are kept for FAO only (the last twelve months as issued, in each snapshot).
- COP's freshness window for Headwind (fresh 24 h, stale 72 h) will trip over a long weekend, because the
  ECB publishes on business days only.

## Licences (unverified unless marked)
- WFP on HDX: CC BY-IGO, read from HDX's own metadata on 12 Nov 2026.
- FAO: CC BY-NC-SA 3.0 IGO, carried from the seed build, not rechecked. FAO may have changed its database
  licence since; read its current terms before deploy.
- ECB, World Bank (CC BY 4.0), Federal Reserve: stated from memory. Check each before deploy.
- OFAC list and Federal Register: US government works, stated from memory. UN Security Council list: no
  licence statement found (the 29 Oct source research found none either). Check before deploy.
- Energy: EIA's data is US government work, but Headwind downloads it from FRED, so FRED's terms of use apply to
  the download as well. Neither was read. Check both before deploy.
