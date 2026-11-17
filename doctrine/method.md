# Headwind method (`headwind-1.10`)

## Purpose
Headwind measures economic stress: currencies, energy and food prices that move outside their own
normal range, changes to official sanctions and US screening lists, new export-control and sanctions
rules, US tariff actions and revisions of the US tariff schedule, the US Supreme Court's opinions and the
tariff-authority cases, US import reliance for mineral commodities, and the scheduled dates on which economic
decisions and figures are published.
It reports measurements. It states no probability and gives no investment advice.

## Live lanes (15 Nov 2026)

| Lane | Source | Cadence | Measure |
|---|---|---|---|
| Exchange rates | ECB euro reference rates, restated per US dollar | TARGET business days | 5-day change against the currency's own 250 prior 5-day changes |
| Official monthly rates (since 15 Nov 2026) | World Bank Global Economic Monitor, official rate per US dollar, monthly average, for the 19 watched countries | Monthly, two to three months late | 1-month change against the country's own 60 prior monthly changes, 2% floor; older than four months is listed, not published |
| Market exchange rates (since 15 Nov 2026) | The exchange-rate rows in WFP's price files (many marked unofficial) | Monthly, one to three months late | Median 1-month change across a country's markets, against its own 60 prior medians, 5% floor |
| Energy | EIA spot prices for Brent, WTI and Henry Hub, from EIA's own API | Trading days, a day or two late | Same, with a 5% floor |
| Food indices | FAO Food Price Index and five sub-indices | Monthly | 1-month change against 120 prior monthly changes |
| Fertilizers and critical-list metals (since 16 Nov 2026, `headwind-1.10`) | World Bank Commodity Price Data (the Pink Sheet), monthly prices in nominal US dollars: phosphate rock, DAP, TSP, urea, potassium chloride; aluminum, copper, lead, tin, nickel, zinc, platinum, silver | Monthly, on the second business day of the next month | 1-month change against the series' own 120 prior monthly changes, 3% floor (phosphate rock 10%) |
| Local food prices | WFP prices by market, from the Humanitarian Data Exchange | Monthly, one to three months late | Median 3-month change across a country's price series, against its own 60 prior medians |
| Country baseline | World Bank World Development Indicators | Annual | No anomaly test; context only, in `data/baseline.json` |
| Calendar | Federal Reserve, ECB and FAO schedule pages | As published | Dates for Verdict's calendar, in `data/events.json` |
| Sanctions lists | OFAC SDN list (`sdn.csv`); UN Security Council consolidated list (XML); the EU's Financial Sanctions Files (XML); the UK Sanctions List (XML); since 16 Nov 2026 France's Registre national des gels (JSON) and Canada's Consolidated Canadian Autonomous Sanctions List (XML) | As the publishers update them | Entries added and removed since Headwind's last reading, by type and program; a change is scored by its designation batches (below) |
| US Supreme Court (since 16 Nov 2026) | The Court's slip opinion feeds (this term and the last) and its dockets (JSON) | As the Court publishes | Every signed and per curiam opinion, with the Court's case title, docket number and decision date; the tariff-authority dockets tracked; no anomaly test |
| UN sanctions committee releases (since 16 Nov 2026) | The UN's Meetings Coverage and Press Releases feed (RSS) | As the UN publishes | Security Council sanctions committees' press releases: document number, date and link only; no anomaly test |
| Screening lists | trade.gov Consolidated Screening List: the BIS Entity List and ten other US Commerce, State and Treasury lists (the SDN list is read from OFAC instead) | Re-imported hourly by trade.gov | Entries added and removed since Headwind's last reading, per list, by address country; scored by designation batches where the list gives dates |
| Minerals | USGS Mineral Commodity Summaries data release (net import reliance; import shares by country) | Annual | No anomaly test; context only, in `data/minerals.json` |
| Rules | US Federal Register API: BIS, OFAC and USTR rules and proposed rules, and USTR notices | Federal working days | What was published in the last 60 days, and the future dates each document names; no anomaly test |
| Tariff actions (since 15 Nov 2026) | US Federal Register API: presidential documents whose title is a tariff action; BIS's and ITA's Section 232 notices | Federal working days; a presidential document 3 to 7 days after signing | The documents of the last 60 days and the dates they set; the count of presidential tariff actions in 28 days against the 27 windows before |
| Tariff schedule (since 15 Nov 2026) | US International Trade Commission, Harmonized Tariff Schedule release list; The White House, presidential actions (RSS) | As posted | Revisions posted in 28 days against the 27 windows before; actions signed and not yet in the Federal Register |
| Public inspection (since 15 Nov 2026) | Office of the Federal Register, public inspection: BIS, OFAC and USTR filings | Federal working days | Filings of the last 30 days; HW-IND-2 measured on BIS and USTR filings (below); no anomaly test |
| US mineral imports (since 15 Nov 2026) | US Census Bureau international trade API, general imports by HS code and country | Monthly, about six weeks late | The last 12 months against the 12 before, leading sources, China's share; context only, in `data/minerals.json`, no anomaly test |

## The anomaly rule
For each series, the latest change is compared with the same series' earlier changes:

    z = (change - median(baseline)) / (1.4826 x MAD(baseline))

The median and the median absolute deviation are used because price changes have fat tails; one
past spike inflates a standard deviation enough to hide the next. An item is tier `anomaly` when
|z| >= 3.5 and the move is at least the lane's floor (1% currencies, 5% energy, 2% FAO indices,
3% Pink Sheet prices, 10% for phosphate rock, 10% local food). The floor keeps pegged currencies from being flagged for trivial moves, and the
scale in the formula is never allowed below floor / 3.5, so a nearly constant history cannot
produce a z in the hundreds.

Every item scored by an anomaly rule carries `flag_rate`: the share of the baseline's own changes that
the same rule would have flagged. It says how often that series trips the rule in ordinary times. A list
change carries the flag rate of its highest-scoring designation batch. Rules, public-inspection filings and
context tables are not scored and carry none.

An anomaly carries `baseline_ref` in the kit's form: `id` (the lane's rule, such as `headwind-fxmarket` or
`headwind-designation-batch`), `window` (the baseline and threshold in words), `type` `rolling`, and `version`
(the method version).

## What the measure does not do
- **The baseline is rolling only.** A long slide becomes the new normal. A fixed baseline beside it
  is not built yet.
- **Official exchange rates.** The ECB quotes about 30 currencies and none for the rouble. Countries
  with a parallel market are understated or absent (assumption `HW-ASM-2`). Since 15 Nov 2026 the watched
  countries also get the World Bank's official monthly average (15 of 19) and WFP's market rates (8 of 19,
  most marked unofficial). Markets more than half again apart (Somalia's two shillings) give no single level and
  no comparison with the official rate. An official figure can be one the market does not use: GEM gives Yemen
  about 238 rials per US dollar while WFP's markets give about 1,556 (Aug 2026); the comparison prints the gap
  as measured and does not say which rate is in use. Since 15 Nov 2026 the page carries a caveat with Yemen's
  gap (two rials in use; which rate the World Bank reports is not verified) and with any other gap of 100% or
  more. The comparison uses the newest month both sources give, and never a month in which the country's
  markets were more than half again apart (tested month by month, not only on the latest month).
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
by sanctions program. Since `headwind-1.9` the people and organizations added, changed and removed are named on
every list but the UN's (see Names on list changes). Vessels are named, with IMO number, MMSI, flag and type as the
list gives them, because the IMO number is how a vessel is matched elsewhere.

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
- **Rules have no anomaly rule** and are tier `routine`. A list change is tier `anomaly` only when one of
  its designation batches is (see Designation batches, since `headwind-1.6`); otherwise `routine`.
- **Edits are seen (`headwind-1.4`).** An entry on both readings whose type or programs changed (since
  `headwind-1.9` also its name) is counted as changed, with the programs gained and lost across those entries. A listed vessel whose
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

## France's asset-freeze register (`headwind-1.8`, 16 Nov 2026)
- **What it is.** The French Treasury's Registre national des gels lists every person, entity and ship whose assets
  are frozen in France, keyed on its own `IdRegistre`, each with one or more legal bases. Most entries restate
  measures the EU and the UN Security Council took, which Headwind already reads on their own lists; a few are
  France's own national freezes (ministerial orders under the Code monétaire et financier, articles L. 562-2 and
  following). On the 6 Nov 2026 file: 8,226 entries, 6,963 under EU regimes only, 1,022 under UN regimes only
  (all 39 ships, North Korea), 161 under both, and 80 national (58 individuals, 22 entities), none of them also EU
  or UN.
- **The test.** Each legal basis reads "<act> du <date> (<regime>)". The regime in the last brackets starts "UE"
  (an EU regime), "ONU" (a UN regime) or "Dispositif national de gel des avoirs" (a national freeze). An entry is
  national when any of its bases is national. Every one of the 1,107 legal bases on the 6 Nov file is one of the
  three; a basis that is none of them is shown on the list's status as an unknown program.
- **Counted apart** (Tom, 16 Nov 2026). A change is reported as national freezes added, removed and changed, by type
  and by article, and scored by the observed-batch rule (France's file gives no designation date, so the batch is
  what Headwind saw added between two readings, against the earlier national additions it saw). Entries that
  restate EU and UN measures are one count line: added, removed and changed, never scored and placing no country,
  so an EU package is not counted twice. National freezes are conduct measures and place no country either.
- **Ships** are named with their IMO number, as on the OFAC and UK lists, and matched with them by IMO number
  (37 of France's 39 on 16 Nov 2026). Copies to August 2026 named them after their owner ("<company> - navire HUI
  CHON"); the owner is cut and the ship's name kept, so that change is not a rename. The register gives no flag,
  type or MMSI.
- **Ids are stable.** On the Wayback Machine's copies of 17 Jul and 7 Aug 2026 (it keeps only their first 5 MiB,
  about 2,890 entries each), every id on both copies and on the 6 Nov file kept its nature; names changed only for
  those seven ships and five spelling edits.

## Canada's consolidated list (`headwind-1.8`, 16 Nov 2026)
- **What it is.** Global Affairs Canada's Consolidated Canadian Autonomous Sanctions List: 5,781 records on the
  10 Nov 2026 file (3,543 individuals, 1,507 entities, 731 ships, all under the Russia regulations, each with an IMO
  number), 19 regimes, each record with its date of listing.
- **No entry id.** A record is its regime, schedule and item number (5,781 unique; schedule and item alone clash 792
  times). Spelling is normalized ("Moldova " and "Moldova", "1,Part 3" and "1, Part 3").
- **Tested on five copies** (Wayback 30 Aug, 6 Oct, 24 Oct and 8 Nov 2026, and the 10 Nov file): no key that stayed
  on the list ever pointed to a different name. Canada does renumber: between 8 and 10 Nov four records listed on
  4 Sep 2026 moved from items 1700-1703 to 1620-1623 (Russia, Schedule 1, Part 1). So a key that goes while a record
  of the same type and name comes under a new item number in the same regime and schedule is counted once, as
  renumbered, not as a removal and an addition. The name is kept only as a 12-character hash in Headwind's run
  state (public with the repository; the hash, not the name). The first reading under this rule has no hashes from before and pairs nothing.
- **Measured** like the EU and UK lists: counts by type and regime, ships named (name, IMO number, type; the list
  gives no flag), designation batches from the dates of listing. Countries come from the regime; the Ukraine
  regulations are placed on Russia only, as the EU's Ukraine regime is; JVCFOR (corrupt foreign officials), Hamas
  Terrorist Attacks and Extremist Settler Violence are conduct regimes and left unplaced.
- **Layout.** Canada renamed every field between its June and August 2026 files (Country to Country-Pays). A file
  with none of the expected fields fails the list, keeping the reading before; it is never read as delistings.

## UN sanctions committee press releases (`headwind-1.8`, 16 Nov 2026)
- **Source.** The UN's Meetings Coverage and Press Releases RSS feed, the only feed found. A release counts when its
  link is a Security Council document (SC/nnnnn) and its title names a sanctions committee ("... Sanctions
  Committee ..." or "Committee (established) pursuant to resolution N", other than the 1540 and Counter-Terrorism
  committees). Headwind keeps and publishes the document number, date and link only (UN terms of use: personal,
  non-commercial use, no redistribution); the title is read for that test and not kept. No country is attached.
- **The feed can drop releases.** It holds the ten newest releases of every UN body: about 7 hours on 13 Nov 2026,
  and from 4 hours to 3 days on ten Wayback copies from 2026. The 26 Oct 2026 release SC/16488 (a committee removing
  three entries) was gone from the copy of 27 Oct. Headwind runs every 4 to 9 hours, so each reading states whether
  the feed reached back to the reading before; when it did not, the page and the source's health say a release may
  have been missed. Release pages and listings sit behind a bot challenge, so Headwind does not walk the numbers.
  The committees' changes to the UN list itself are read from the list, not from this feed.

## The US Supreme Court (`headwind-1.8`, 16 Nov 2026)
- **What is covered.** Every opinion in the Court's slip opinion feeds for the current term and the one before
  (a term starts in October): signed opinions of the Court and per curiam opinions, including those on applications
  (the emergency docket) that the Court lists there. Decrees in original cases are not opinions and are left out.
  Not covered: orders lists (the Court publishes no feed of them), opinions relating to orders and in-chambers
  opinions (other pages, not read). On 16 Nov 2026: 75 opinions (56 signed, 19 per curiam).
- **What an item says.** That the Court issued an opinion in a case on a date, by whom (or per curiam), with the
  Court's own case title and docket number as the Court publishes them (Tom, 15 Nov 2026), the link to the opinion
  and to the docket. Headwind does not summarize, characterize or score a decision. An opinion is in the feed for 14
  days from its decision date; the page lists both terms.
- **The decision date** comes from the docket: the entry that links the opinion, or, where the entry names it
  without a link, the entry saying who delivered the opinion. The feed's own date is when the PDF was last posted,
  which moves when the reporter version replaces the slip opinion (West Virginia v. B. P. J., decided 30 Jun 2026,
  was posted again on 28 Oct 2026). Each docket is read once.
- **`us_person_data`.** A case title does not say whether a party is a US person, so the label is cautious:
  `individuals` when either side reads as a person (a name with no mark of a government or an organization; an
  official named in office is a person), else `organizations` when a side is an organization that is not a
  government, else `none` (governments on every side). On the 75 opinions of 16 Nov 2026: 64 individuals, 11
  organizations, none `none`. A mistake goes toward `individuals` (Al Otro Lado, an organization, reads as a person);
  the other way, a person whose surname is an organization word (Church, Bank) would read as an organization. The
  label is for consumers bound by US-person rules; it never keeps a case out.
- **Tariff authority.** Dockets 24-1287 (Learning Resources, Inc. v. Trump) and 25-250 (Trump v. V.O.S.
  Selections, Inc.) are read every run, with any docket they name as related: the judgment (20 Feb 2026: 24-1287
  vacated and remanded with instructions to dismiss for lack of jurisdiction; 25-250 affirmed), the newest docket
  entry, and a feed item for a new entry within 14 days. A later tariff case is added by hand.
- **Licence.** Opinions and dockets are US government works (17 USC 105, stated from memory; the Court's site gives
  no reuse statement).

## Names on list changes (`headwind-1.9`, 16 Nov 2026)
- **What is named.** People, organizations and ships added, changed and removed on every list Headwind reads but the
  UN Security Council's: OFAC's SDN list, the EU's, the UK's, France's and Canada's lists, and trade.gov's screening
  lists. Each named entry carries its name as the publisher prints it ("LAST, First" on OFAC's list, "Nom, Prénom" on
  France's), its type, its programs, the countries of its addresses and nationality as printed, and the listing date
  where the list gives one. Birth dates, identity documents, street addresses, statements of reasons, aliases and
  contact details are not carried. OFAC's countries come from its own address file (`add.csv`); Canada's list prints
  no address or nationality.
- **Why these lists and not the UN's.** Tom, 15 Nov 2026: publish what the licences allow. OFAC's and trade.gov's
  lists are US government works. Canada allows non-commercial reproduction. France's Licence Ouverte 2.0 and the EU's
  reuse decision (2011/833/EU) allow reuse of personal data within data-protection law; the UK's Open Government
  Licence v3.0 does not cover personal data, which leaves the question to data-protection law too (all read 16 Nov
  2026). Headwind carries the least that identifies an entry, shows a removal as a removal, and takes down on request
  the name of someone no longer listed (support@theintelligence.company). The UN's terms of use bar redistributing its
  content, so its list stays counts, ids, types and dates.
- **Where.** A feed item names up to 25 entries: those added, those changed, and organizations removed. The page
  names every entry of a change, removed people included, and `data/list-changes.json` holds them all, for the 30
  days a change is kept. A person removed from a list is counted in the feed item, not named: feed text goes into
  the history log for good, and someone no longer listed should not stay named there.
- **Removed and changed.** A removed entry reads "no longer on the list", with the reading that saw it go. An entry
  that stays and changes its name, type or programs is named as changed, with its name before; spelling corrections
  therefore show as changes. Addresses and other details are not compared.
- **The first reading under this rule.** Indexes kept before 16 Nov 2026 hold no names, so the first change after the
  deploy counts its removals without naming them and compares no names; from the next reading all of it works. A
  later change in how a name is read (`name_format`) is handled the same way, never reported as renames.
- **`us_person_data`.** `individuals` when a named person, or an entry of unstated type (trade.gov gives no type for
  the Entity List and the Denied Persons List), has a US address or nationality; `organizations` when only
  organizations do; otherwise `none`. Entries of Canada's list, which prints no address, cannot set it. The label is
  for consumers bound by US-person rules; it never keeps an item out.

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
  is not kept. OFAC's and BIS's notices (sanctions actions, denial orders) were counted, not titled, until
  `headwind-1.9`; since then they carry their titles and the register's own address, as every filing does (Federal
  Register documents may be reproduced without restriction). Their texts are still not read, and HW-IND-2 is not
  measured on them. A BIS order names its party in its title, often a US person, so such an item carries
  `us_person_data` `individuals`. A filing stays in the feed 7 days.
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
country, for the first two; HW-H-2B, stress from outside, for energy) and `indicator_state` present. `direction`
is supports for HW-IND-4 and HW-IND-5, and neutral for HW-IND-6 (register 1.3, 15 Nov 2026), which is expected
under HW-H-2A and HW-H-2B alike and so tells them not apart. It stays a measurement (tier anomaly, no probability): which hypothesis holds is
told apart by which indicators are present together, and that reading is an analyst's. Routine items carry no
indicator. Watched countries are those whose WFP prices Headwind reads (`config/wfp_countries.json`).
HW-IND-4 is carried by an anomaly in any of a watched country's three currency readings, each by its own rule
(register 1.3 states all three): the ECB's daily rate (five business days, 1% floor), the World Bank's official
monthly average (one month, 2% floor) or WFP's market rate (median one-month change, 5% floor). The page's "Watched countries side by side"
table (`country_view` in the snapshot) sets them next to the local food reading; nothing combines them.

## Designation batches (15 Nov 2026)
A list change is a measurement of what Headwind saw change. Since `headwind-1.6` it is also scored: each
designation date among the entries it adds is a batch, sized from the publisher's own dates in the same file (EU,
UK, UN, and trade.gov's screening lists), and judged against the list's 60 earlier designation dates with the robust
z on the logarithm of the size. Unusual at z >= 3.5 and at least 10 entries; a smaller or ordinary batch stays
routine. The item carries the largest batch, the highest z and that batch's `flag_rate`. OFAC's file has no designation dates, so its batch is what Headwind saw added at once, against the earlier
changes Headwind itself saw (no baseline until 24 are kept). Past batches are counted from the current file, so
entries since removed are missing from them. The item stays an observation with no probability; no indicator id is
attached.

## Screening lists
The same measure, applied to each list in the US International Trade Administration's Consolidated
Screening List. One item per list that changed, with counts by the address country the list gives
for each entry and, where the list has them, by program, and since `headwind-1.9` the entries added, changed and
removed named (see Names on list changes).

- **Address country is where the list places the entry**, not a finding about who controls it. An entry
  with addresses in three countries is counted under each.
- **Entry ids** on the Commerce and State lists are assigned by trade.gov (a hash). Whether an id
  changes when a publisher edits an entry has not been observed either way. Since `headwind-1.4` an id
  that goes and an id that comes on the same list, with the same name and type and no other entry of
  that name going or coming, are counted once, as re-keyed, and compared as one entry. The name is kept
  as a short hash in Headwind's run state for this pairing (the name itself is kept beside it since `headwind-1.9`).
- **Edits** (an entry whose type, programs, address countries or, since `headwind-1.9`, name changed) are counted
  and named, with the programs gained and lost.
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

## US mineral imports by country (15 Nov 2026)
For 24 HS codes standing for minerals on the 2025 List of Critical Minerals, the Census Bureau's monthly general
imports (customs value) by country of origin: the last 12 calendar months against the 12 before, the leading
sources and China's share. Context only, not feed items, no anomaly test. An HS heading can hold more than one
mineral, and ores, metals and compounds are separate codes, so a code's figures are not a mineral's whole trade.

## Tariff actions and the tariff schedule (`headwind-1.7`, 15 Nov 2026)
- **Which documents.** A presidential document (proclamation, executive order, memorandum) is a tariff action when
  its title says tariff, duties, duty-free, adjusting imports, import adjustment, Section 122, 232, 301 or 338, or
  harmonized tariff. Read against every presidential document from September 2024 to November 2026: 60 of 839
  matched, all by title (24 in 2026 to 15 Nov, 36 in 2025). "Duty" alone does not count ("Line of Duty").
  BIS's and ITA's notices that say "section 232" count when their title names a tariff or an inclusions
  window, less information collections.
- **Dates.** A proclamation states when it takes effect as "12:01 a.m. eastern time on <date>"; each such
  date from its publication day on is kept. "Within N days of the date of this proclamation" is counted from
  the signing date and kept apart as computed (the 28 Oct 2026 wind-turbine and robotics proclamations set
  180 days for an agreement: 20 and 26 Apr 2027). Each text is read once. All dates go into the register of
  scheduled dates and to Verdict's calendar.
- **Pace.** The number of tariff actions the Federal Register published in the last 28 days, against the same
  count in each of the 27 windows of 28 days before (robust z, as every Headwind series). Unusual at z of 3.5
  or more and at least four documents. The same rule counts revisions of the Harmonized Tariff Schedule (at
  least three). Neither says what a tariff does or what it costs; they count published acts.
- **Signed, not yet published.** The White House posts a document the day it is signed. A tariff action there
  whose title (case and punctuation aside) is not yet a Federal Register presidential document is listed as
  signed, not yet published, for 30 days. Page only, not a feed item.
- **Not read:** CBP's Cargo Systems Messaging Service (no keyless feed), what each HTS revision changed (the
  release list gives none). Court rulings on tariff authority are read since `headwind-1.8` (see the US Supreme
  Court); other courts' tariff cases (the Court of International Trade, the Federal Circuit) are not.

## Fertilizers and critical-list metals (`headwind-1.10`, 16 Nov 2026)
- **Source.** The World Bank's Commodity Price Data (the Pink Sheet), monthly file `CMO-Historical-Data-Monthly.xlsx`,
  linked from the Commodity Markets page; the address changes each year, so it is read from the page each run. The
  World Bank's data catalog lists the data as "Commodity Prices - History and Projections" (dataset 0038238, read 16
  Nov 2026: "Commodity prices are updated in the second business day of the month"; licence Creative Commons
  Attribution 4.0). The file's Description sheet names the market reporters behind each price (Bloomberg, Platts,
  S&P Global, Green Markets and others); the World Bank publishes the compiled prices under CC BY 4.0.
- **Series.** The five fertilizers and the eight metals in the file that are on the US Final 2025 List of Critical
  Minerals (phosphate rock and potash are on the list too). Iron ore and gold are in the file and not on the list, so
  they are not read. Each is a monthly average in nominal US dollars, in the file's unit.
- **Measure.** As FAO's indices: the latest month's change against the series' own 120 prior monthly changes, robust
  z, anomaly at |z| >= 3.5 and a move of at least 3%. Phosphate rock is flat for months and then steps; at 3% the rule
  would trip on 27.5% of its last 120 months, so its floor is 10% (5.8%, about TSP's rate). Measured on the 3 Nov
  2026 file. No indicator in the register; items answer HW-PIR-6 (register 1.2).
- **Failure.** A page without the link, a workbook without the "Monthly Prices" sheet or with fewer than 10 of the
  13 columns fails the lane, which keeps its last good copy.

## Not live
Nothing planned is held. Later sources (more courts and sanctions lists, stock indices) are still being read for
their terms.

## Verdict
`data/question_drafts.json` holds draft questions on the next FAO release with a climatology
baseline (the share of the last 120 months in which the index rose). They are drafts; nothing is
registered by Headwind.
