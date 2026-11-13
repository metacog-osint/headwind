# Headwind (`D:\Projects\headwind`)

Economic stress for The Intelligence Company (`tic-feed/2`, program id `headwind`, prefix `HW`): currencies,
energy and food prices measured against their own normal range, plus a calendar of economic dates for Verdict.
Measurements only. No probabilities, no investment advice.

**State, 12 Nov 2026 (about 11:30 PM CST): the first live slice is built and runs locally. Nothing is committed,
pushed or deployed.** The site address in the feed (`headwind.theintelligence.company`) does not exist yet, and the
suite registry still lists Headwind as planned with seed data.

## Commands

```bash
python tools/headwind.py collect              # fetch every live lane into data/snapshot.json
python tools/headwind.py collect --only fx    # one or more lanes; the rest keep their last copy
python tools/headwind.py build                # build site/ from data/snapshot.json
python tools/headwind.py check                # validate the registers and lint the feed
python -m unittest discover -s tests          # 14 offline tests against real fixtures
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

Outputs in `site/data/`: `feed.geojson` (55 items on 12 Nov), `events.json` (Verdict's `sync_calendar` format),
`baseline.json` (not in the feed), `question_drafts.json` (drafts only), `snapshot.json` (what the page reads).

## The measure (`stats.py`, `doctrine/method.md`)
One rule for every series: the latest change against the series' own earlier changes, as a robust z (median and
MAD). Anomaly at |z| >= 3.5 and a move above the lane's floor. Each item carries `flag_rate`, how often the series
trips the rule in ordinary times. On 12 Nov nothing was flagged; the largest z was 3.0 (Australian dollar).

## Rules
- **Standard library only** (Python 3.11+).
- **Raw copies** go to `data/raw/<source>/<sha12>.<ext>` with a line in `data/raw/index.jsonl`. Git-ignored;
  about 150 MB after one run, nearly all WFP files. A WFP file is fetched again only when HDX's
  `last_modified` changes.
- **`data/snapshot.json` is the last-good store.** A scheduled build has to carry it between runs or a failed
  lane goes empty.
- **Anomaly items carry no `indicator_id`.** The contract ties an indicator to a hypothesis, and Headwind has no
  warning problem for economic stress yet. `HW-IND-4` to `HW-IND-6` are registered for when Tom writes one.
- **The sanctions and export-control code has no collector.** `sanctions.py`, `controls.py` and their feed blocks
  are kept; the only records for them are the invented ones in `tests/test_headwind.py` (`MADE_UP`), which must
  never be published. `commodities.py` (the old IGC lane) is unused.
- A rate decision is exported to Verdict as kind `rule_date`, the nearest kind Verdict accepts.

## Not done
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
- FAO: CC BY-NC-SA 3.0 IGO, carried from the seed build, not rechecked.
- ECB, EIA through FRED, World Bank (CC BY 4.0), Federal Reserve: stated from memory. Check each before deploy.
