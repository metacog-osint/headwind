# Headwind method (`headwind-1.6`)

## Purpose
Headwind measures economic stress: currencies, energy and food prices that move outside their own
normal range, changes to official sanctions and US screening lists, new export-control and sanctions
rules, US import reliance for mineral commodities, and the scheduled dates on which economic decisions and figures are published.
It reports measurements. It states no probability and gives no investment advice.

## Live lanes (13 Nov 2026)

| Lane | Source | Cadence | Measure |
|---|---|---|---|
| Exchange rates | ECB euro reference rates, restated per US dollar | TARGET business days | 5-day change against the currency's own 250 prior 5-day changes |
| Official monthly rates (since 15 Nov 2026) | World Bank Global Economic Monitor, official rate per US dollar, monthly average, for the 19 watched countries | Monthly, two to three months late | 1-month change against the country's own 60 prior monthly changes, 2% floor; older than four months is listed, not published |
| Market exchange rates (since 15 Nov 2026) | The exchange-rate rows in WFP's price files (many marked unofficial) | Monthly, one to three months late | Median 1-month change across a country's markets, against its own 60 prior medians, 5% floor |
| Energy | EIA spot prices for Brent, WTI and Henry Hub, from EIA's own API | Trading days, a day or two late | Same, with a 5% floor |
| Food indices | FAO Food Price Index and five sub-indices | Monthly | 1-month change against 120 prior monthly changes |
| Local food prices | WFP prices by market, from the Humanitarian Data Exchange | Monthly, one to three months late | Median 3-month change across a country's price series, against its own 60 prior medians |
| Country baseline | World Bank World Development Indicators | Annual | No anomaly test; context only, in `data/baseline.json` |
| Calendar | Federal Reserve, ECB and FAO schedule pages | As published | Dates for Verdict's calendar, in `data/events.json` |
| Sanctions lists | OFAC SDN list (`sdn.csv`); UN Security Council consolidated list (XML) | As the publishers update them | Entries added and removed since Headwind's last reading, by type and program |
| Screening lists | trade.gov Consolidated Screening List: the BIS Entity List and ten other US Commerce, State and Treasury lists (the SDN list is read from OFAC instead) | Re-imported hourly by trade.gov | Entries added and removed since Headwind's last reading, per list, by address country |
| Minerals | USGS Mineral Commodity Summaries data release (net import reliance; import shares by country) | Annual | No anomaly test; context only, in `data/minerals.json` |
| Rules | US Federal Register API: BIS and OFAC rules and proposed rules | Federal working days | What was published in the last 60 days, and the future dates each document names |

## The anomaly rule
For each series, the latest change is compared with the same series' earlier changes:

    z = (change - median(baseline)) / (1.4826 x MAD(baseline))

The median and the median absolute deviation are used because price changes have fat tails; one
past spike inflates a standard deviation enough to hide the next. An item is tier `anomaly` when
|z| >= 3.5 and the move is at least the lane's floor (1% currencies, 5% energy, 2% FAO indices,
10% local food). The floor keeps pegged currencies from being flagged for trivial moves, and the
scale in the formula is never allowed below floor / 3.5, so a nearly constant history cannot
produce a z in the hundreds.

Every item carries `flag_rate`: the share of the baseline's own changes that the same rule would
have flagged. It says how often that series trips the rule in ordinary times.

## What the measure does not do
- **The baseline is rolling only.** A long slide becomes the new normal. A fixed baseline beside it
  is not built yet.
- **Official exchange rates.** The ECB quotes about 30 currencies and none for the rouble. Countries
  with a parallel market are understated or absent (assumption `HW-ASM-2`). Since 15 Nov 2026 the watched
  countries also get the World Bank's official monthly average (15 of 19) and WFP's market rates (8 of 19,
  most marked unofficial). Markets more than half again apart (Somalia's two shillings) give no single level and
  no comparison with the official rate. An official figure can be one the market does not use: GEM gives Yemen
  about 238 rials per US dollar while WFP's markets give about 1,556 (Aug 2026); the comparison prints the gap
  as measured and does not say which rate is in use.
- **WFP exchange rates are not food prices.** Before `headwind-1.6` they were counted among a country's price
  series in the local food median; now they are read only as market rates (Sudan's 3-month food median moved
  from 50.1% to 50.0% on the 15 Nov file).
- **Nominal prices.** WFP prices are in local currency and not adjusted for inflation; the test
  against a country's own history is what makes them comparable.
- **Revisions.** FAO revises earlier months. Each snapshot keeps the last twelve months as issued.
  The other lanes keep only the raw files under `data/raw/` (git-ignored).
- **Stale local prices.** A country whose newest WFP month is more than four months old is listed
  on the page as having no recent data and is left out of the feed.

## Sanctions lists and rules
A list change is the difference between two of Headwind's own readings of an official list, matched on
the publisher's entry id. It is reported as counts by type (individual, entity, vessel, aircraft) and
by sanctions program. Headwind does not republish the names of people or organizations; the item links to the official list. Vessels are named, with IMO number, MMSI, flag and type as the list gives them, because a vessel is not a person and the IMO number is how a vessel is matched elsewhere.

- **The date is the date Headwind saw the change**, not the date of the designation. A change made
  and reversed between two readings is not seen at all.
- **The first reading sets the baseline** and reports nothing.
- **A broken download is not a delisting.** A list that parses short, or that loses more than half
  its entries, fails the lane and keeps the last good copy.
- **Countries** are attached only where a program names one country. Programs aimed at conduct
  (terrorism, narcotics, cyber) are left unplaced.
- **Rules** are reported as the agency titled and described them. Dates come from the document's
  effective date, its comment deadline and dates written out in its DATES paragraph. Headwind does
  not say what a rule means or whether a stay will be extended.
- **No anomaly rule yet.** Every list and rule item is tier `routine`; a baseline needs a history of
  Headwind's own readings.
- **Edits are seen (`headwind-1.4`).** An entry on both readings whose type or programs changed is
  counted as changed, with the programs gained and lost across those entries. A listed vessel whose
  name, IMO number, MMSI, flag or type changed is named, before and after.
- **A ship remade under a new id is one entry (`headwind-1.5`).** A vessel that goes and a vessel that
  comes on the same list with the same IMO number, and no other vessel with that number going or coming,
  are counted once, as re-keyed, and compared as one entry. The UK revokes and remakes a ship's
  specification under a new id (2 Oct 2026: two ships); the ship never leaves the list.
- **Ships across lists (15 Nov 2026).** After every reading, ships on the OFAC SDN list and the UK Sanctions
  List are matched by IMO number: how many numbers are on both, on one only, and how many entries give no
  number. `vessels.json` lists every number with each list's entry ids, name and flag (owners left out). A
  ship named in a change carries the other list that holds its number after that reading ("also on"). Names
  are not matched, because the lists spell them differently (AN SAN 1 and An San 1, IMO 7303803). This adds
  a table; it changes no count, so the method version stays `headwind-1.5`.
- **UK ship names.** The UK names many ships it specifies by IMO number, as `IMO 9344411 ("GALLE ENERGY")`
  or as the number alone with the ship's name given only as an alias. Headwind shows the name in brackets,
  else the alias, marked as an alias.

## USTR, public inspection and HW-IND-2 (`headwind-1.6`)
- **USTR.** The rules lane reads USTR's rules and its notices (Section 301 actions, exclusions and their
  extensions) beside BIS's and OFAC's rules, in the same form. USTR notices about the office itself
  (Performance Review Board, Privacy Act, meetings) are left out.
- **The register of scheduled dates.** The same agencies' documents of the last 800 days give every date a
  document set: one written out in its DATES paragraph, its effective date, the close of its comment
  period. Each is kept with the document's RINs and docket numbers and, for USTR, the investigation its
  title names (the words after the title's colon, without case, punctuation or small words). A date stays
  45 days after it passes.
- **Public inspection.** Each run reads the issues of the last five days from the Office of the Federal
  Register and keeps BIS's, OFAC's and USTR's filings for 30 days, with the time each was filed and the day
  it is to be published. The text of each rule, proposed rule and USTR notice is read once for its action
  line, RINs, docket numbers, the first sentence of its summary and each date it says was already
  scheduled ("was set to end", "scheduled to expire": the first date after the phrase). The text itself
  is not kept. OFAC's and BIS's notices (sanctions actions, denial orders) are counted, not titled,
  because their titles and texts can name people and companies. A filing stays in the feed 7 days.
- **HW-IND-2 is measured, not judged.** A BIS or USTR filing meets it when (1) its title, action line or
  summary's first sentence makes it a stay, suspension, extension or Entity List filing (not a comment
  period or information collection), and (2) a scheduled date falls on the day it was filed or within 14
  days after: a date that an earlier document of the same agency set and that shares the filing's RIN, a
  docket number or (USTR) its investigation, or a date the filing itself says was scheduled. The item
  then carries `indicator_id` HW-IND-2, `hypothesis_id` HW-H-1B, `direction` supports and
  `indicator_state` present; otherwise absent (neutral), or no_data when the text could not be read and
  nothing else matched. The tier stays `routine`: there is no baseline, and a met condition is not a
  warning. Matching on the same agency alone is not enough, because comment deadlines and effective dates
  of unrelated rules fall within 14 days of most filings.
- **Seen on the real filings of 5 and 9 Nov 2026:** BIS's extension of the affiliates-rule suspension
  (filed 5 Nov, 4 days before the 9 Nov end that document 2025-19846 set, same RIN 0694-AK34), and USTR's
  extension of 178 China exclusions and further suspension of the maritime Section 301 action (both filed
  9 Nov, the day documents 2025-21671 and 2025-19873 had set). USTR's extension of its Vietnam
  investigation (same day) met no scheduled date in the register.

## HW-WP-2: economic stress in a watched country (15 Nov 2026)
An anomaly for a watched country's currency (HW-IND-4) or local food prices (HW-IND-6), or for an energy
benchmark (HW-IND-5), carries its indicator, the hypothesis it is emerging under (HW-H-2A, stress within the
country, for the first two; HW-H-2B, stress from outside, for energy), `direction` supports and
`indicator_state` present. It stays a measurement (tier anomaly, no probability): which hypothesis holds is
told apart by which indicators are present together, and that reading is an analyst's. Routine items carry no
indicator. Watched countries are those whose WFP prices Headwind reads (`config/wfp_countries.json`).
HW-IND-4 is carried by an anomaly in any of a watched country's three currency readings: the ECB's daily rate,
the World Bank's official monthly average or WFP's market rate. The page's "Watched countries side by side"
table (`country_view` in the snapshot) sets them next to the local food reading; nothing combines them.

## Designation batches (15 Nov 2026)
A list change is a measurement of what Headwind saw change. Since `headwind-1.6` it is also scored: each
designation date among the entries it adds is a batch, sized from the publisher's own dates in the same file (EU,
UK, UN, and trade.gov's screening lists), and judged against the list's 60 earlier designation dates with the robust
z on the logarithm of the size. Unusual at z >= 3.5 and at least 10 entries; a smaller or ordinary batch stays
routine. OFAC's file has no designation dates, so its batch is what Headwind saw added at once, against the earlier
changes Headwind itself saw (no baseline until 24 are kept). Past batches are counted from the current file, so
entries since removed are missing from them. The item stays an observation with no probability; no indicator id is
attached.

## Screening lists
The same measure, applied to each list in the US International Trade Administration's Consolidated
Screening List. One item per list that changed, with counts by the address country the list gives
for each entry and, where the list has them, by program.

- **Address country is where the list places the entry**, not a finding about who controls it. An entry
  with addresses in three countries is counted under each.
- **Entry ids** on the Commerce and State lists are assigned by trade.gov (a hash). Whether an id
  changes when a publisher edits an entry has not been observed either way. Since `headwind-1.4` an id
  that goes and an id that comes on the same list, with the same name and type and no other entry of
  that name going or coming, are counted once, as re-keyed, and compared as one entry. The name is kept
  only as a short hash in Headwind's private state; it is never published.
- **Edits** (an entry whose type, programs or address countries changed) are counted, with the programs
  gained and lost.
- **A list that loses more than half its entries** (lists of 20 or more) fails the lane and is not
  reported as delistings.

## Source health (`headwind-1.4`)
The feed carries a `health` member, one entry per source keyed by the source id its items carry: whether
this run read the source (`failing` when not; the page shows the last good copy), the date of its newest
data, and a state against the source's own rhythm: fresh, late or stale for the ECB (4 and 8 days, for
business days and long weekends), EIA (7 and 14), FAO (40 and 70 days after the month's end) and WFP
(75 and 135); `up` (read, no date to judge) for the rest.

- **Drift.** Each run keeps the size of what a source gave (rows, dates, entries) for its last ten good
  readings. Once there are three, a reading under half the median fails the lane for sources parsed from
  pages or files whose layout Headwind does not control, and the last good copy is kept; under four
  fifths, or for sizes that move on their own (the 60-day window of rules, WFP's countries, FAO's release
  dates, the screening file), it is a warning.
- **Quiet publishers.** A note, not a failure, when a list's own file date has not moved for 3 days
  (UN, which regenerates daily) or 30 days (EU, UK), or when Headwind has seen no change on OFAC's list,
  which carries no date, for 21 days.

## Minerals
Net import reliance and import shares are copied from the US Geological Survey's Mineral Commodity
Summaries data release as printed, including bounds such as ">75" where USGS withholds the exact
figure. They are annual and are not feed items. Headwind adds one count: the number of commodities
for which each country is named first among the major import sources. It is a count of USGS's own
ordering and says nothing about substitutes, stockpiles or domestic capacity.

## Not live
Census trade data for minerals.

## Verdict
`data/question_drafts.json` holds draft questions on the next FAO release with a climatology
baseline (the share of the last 120 months in which the index rose). They are drafts; nothing is
registered by Headwind.
