# Headwind method (`headwind-1.10`)

## Purpose
Headwind has two strands.

**Economic stress** (`HW-REQ-1`): currencies, energy and food prices that move outside their own normal range,
changes to official sanctions and US screening lists, new export-control and sanctions rules, US tariff actions and
revisions of the US tariff schedule, the tariff-authority cases, US import reliance for mineral commodities, and the
scheduled dates on which economic decisions and figures are published.

**Legal events** (`HW-REQ-2`, since 18 Nov 2026): the decisions of highest national courts and of international
courts, listed as each court publishes them (below, "The legal events strand"). The US Supreme Court and the UK
Supreme Court are live. Courts and tariff litigation were placed in Headwind rather than in a program of
their own (15 Nov 2026); the ICC is not carried, because its terms bar redistributing or compiling its material
without written permission (20 Nov 2026). Legal events are a strand apart because they do not measure economic stress. The strands meet in the
tariff-authority cases, which are tracked by docket under economic stress (`HW-PIR-2`).

It reports measurements and records. It states no probability and gives no investment advice.

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
| Sanctions lists | OFAC SDN list (`sdn.csv`; entry dates from `sdn_advanced.zip`); UN Security Council consolidated list (XML); the EU's Financial Sanctions Files (XML); the UK Sanctions List (XML); since 16 Nov 2026 France's Registre national des gels (JSON) and Canada's Consolidated Canadian Autonomous Sanctions List (XML); since 19 Nov 2026 Australia's Consolidated List (xlsx) and Japan's asset-freeze list (CSV, with its ship file) | As the publishers update them | Entries added and removed since Headwind's last reading, by type and program; a change is scored by its designation batches (below) |
| US Supreme Court (since 16 Nov 2026) | The Court's slip opinion feeds (this term and the last) and its dockets (JSON) | As the Court publishes | Every signed and per curiam opinion, with the Court's case title, docket number and decision date; the tariff-authority dockets tracked; no anomaly test |
| UK Supreme Court (since 18 Nov 2026) | The Court's own site: sitemap, latest-judgments page, case pages | As the Court publishes | Every judgment this year and last, with the Court's case title, case id and neutral citation; no anomaly test |
| Court of Justice of the EU (since 19 Nov 2026) | The Publications Office's SPARQL endpoint (the metadata behind EUR-Lex) | Same day | Every judgment of the Court of Justice and the General Court in the last 60 days; in the feed, the Grand Chamber's and full Court's and those on restrictive measures; no anomaly test |
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

**Food lanes, two more rules beside z (`headwind-1.10`, 16 Nov 2026, Tom's yes, from the 15 Nov suite review).**
Local food (WFP) and the FAO indices are also an anomaly when the latest reading is a rise above the 95th percentile
of the same baseline (`rank`), or when the reading has risen six or more months in a row (`run`), in both cases with
a move of at least the lane's floor (`stats.rank_run`). Why: Sudan's food prices rose a median 50% in three months to
September 2026, the seventh straight monthly rise and the third-highest reading in five years, and z could not flag
it (z +2.4; the trending, fat-tailed baseline put the line at +67.6%); six of 17 countries and three FAO indices had
never tripped z in their baselines. Currencies and energy keep z alone. Items carry `rules` (which fired) and
`rise_run`, and `flag_rate` counts all three rules on the baseline's own readings (5% to 20% on the 16 Nov files).
Checked on the local WFP files of 16 Nov: only Sudan flags (+55.9% to October 2026, rank and run, nine rises).

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

## Australia's consolidated list (19 Nov 2026)
- **What it is.** The Australian Sanctions Office's (DFAT) Consolidated List, one xlsx at a fixed address: 4,021
  entries on the copy saved 17 Nov 2026 (2,581 individuals, 1,081 entities, 359 ships), one row per name (primary
  name, aliases, original script) under a Reference ("2" for the entry, "2a", "2b" for its other names). 29 regimes:
  14 autonomous, 15 under Security Council resolutions.
- **Terms.** DFAT's copyright page (read 19 Nov 2026): everything on the site but the Coat of Arms is CC BY 4.0,
  attributed "Department of Foreign Affairs and Trade website – www.dfat.gov.au"; robots.txt allows the file.
  dfat.gov.au timed out from Headwind's machine on 15 Nov and on the morning of 19 Nov, then answered in about 8 s.
- **UN restatements counted only** (Tom, 19 Nov 2026). The 1,067 entries under Security Council regimes ("1267",
  "1718", "1988" ...) restate the UN's lists, whose terms withhold redistribution; DFAT's licence covers only its own
  material. They are kept as [type, regime] and nothing else: counted, never named, not scored, placing no country,
  and their ships left out of the cross-list. As with France, the change is split: Australia's own designations are
  named and scored by the observed-batch rule, the restatements are one count line. "1373 (2001)" is not a UN
  restatement: the UN keeps no list under resolution 1373, and those entries are Australia's own terrorism listings.
- **Ids are stable.** On the Wayback copies of 12 Sep and 13 Nov 2026 and the live copy, 3,899 References stayed;
  one changed its name (2693, a patronymic) and none its type or regime.
- **Countries.** Citizenships as printed (";" between them), and from each address the country it ends with when
  that is a citizenship name of the same file or one of a short list of address spellings ("Russian Federation",
  "Japan"), whole or after a comma. Addresses are free text with street lines; only the country is kept, and a place
  that is not a country ("Tehran", "Northern Ireland") gives none. Regimes place countries as on the EU and Canadian
  lists ("Autonomous (Ukraine)" on Russia only; the vessel designations are Russia's); FFRY, the three thematic
  regimes and 1373 are unplaced.
- **No designation date.** The file's Control Date is the date an entry last changed, and its listing text is UN
  wording for UN entries, so batches use Headwind's own readings, as for OFAC and France. The publisher's date is
  the time DFAT saved the workbook (its `dcterms:modified`); the same part names who saved it, which is never kept.
- **Layout.** The sheet's name carries a date on some copies ("Consolidated List - 13_11_2026"); a file without the
  expected columns fails the list, keeping the reading before.

## Japan's asset-freeze list (19 Nov 2026)
- **What it is.** The Ministry of Finance's list of everyone whose assets are frozen under the Foreign Exchange and
  Foreign Trade Act (資産凍結等対象者一覧), one CSV (UTF-8, 32 columns), and a second CSV of the IMO numbers of the
  ships under Japan's services ban (特定の船舶に関する役務取引等の規制措置, from 2 Oct 2026). Both names carry a date
  (`shisantouketsu20261120.csv`), so the links are read from MOF's list page each run; the newest of each is taken,
  and the list's date in the name is the publisher's date. 2,931 entries on the copy of 20 Nov 2026: 2,028
  individuals, 868 entities, 35 ships.
- **Terms.** MOF's terms page (著作権・リンク等について, read 19 Nov 2026) puts the site under the Public Data License
  1.0 (PDL1.0, Digital Agency): reproduction, redistribution and adaptation allowed, commercial use too, compatible
  with CC BY 4.0. It asks for a source line (出典：財務省ウェブサイト（URL）、PDL1.0（URL）) and, for edited content,
  a note that it was edited and by whom, never presented as MOF's unedited data. The page and the feed carry both.
  Nothing on the terms page bars scripted reading, and MOF serves no robots.txt (404 on 19 Nov 2026).
- **Programs.** The list's 区分 is a number per program and type (40 in use; a program's people and organizations
  are often two numbers). Headwind maps each number to an English name for the page's heading (`JP_PROGRAMS`); a number not
  in the map shows as "category n" among the list's unknown programs and is counted only until it is read.
- **UN restatements counted only** (Tom, 19 Nov 2026, as for Australia). The 1,002 entries under Security Council
  programs (1267/1988, Iraq, DR Congo, Sudan, 1718, Iran, Somalia, Libya, Central African Republic, Yemen, South
  Sudan, Haiti) are kept as [type, program]: counted, never named, not scored, placing no country. Category 3, Japan's
  resolution-1373 listing of people and organizations already on the UN's Al-Qaida list (each marked 重複, a
  duplicate of a category-2 entry), is counted only too. Japan's own: category 4 (its resolution-1373 terrorism
  listings: the UN keeps no list under 1373), category 13 (its 2006 listings under resolution 1695 on North Korea:
  no UN list either), and every program "in coordination with the US, EU and others" (FRY, North Korea, Syria,
  Ukraine, Russia, Belarus, third countries, Israeli settlers) and the ship ban.
- **Ids are stable.** On the Wayback copies of 23 Jun 2025 and 14 Oct 2026 and the live copy of 20 Nov 2026,
  2,649 and then 2,896 番号 stayed, none changed its category, and no entry went and came back under a new number;
  names changed on 11 and then 1 (spacing, full-width brackets, an acronym added). Between 14 Oct and 20 Nov MOF
  removed 4 UN entries and added none.
- **Names and countries.** The English name column as printed, NFKC-normalized (full-width letters and brackets read
  as plain ones). Countries from the nationality and address-country columns, English where given, else the
  Japanese through a short map (北朝鮮 North Korea, 中華人民共和国 China); the city and street columns are never read.
  Birth dates, birthplaces, passports, identity numbers, positions, aliases, titles, other information and MOFA's
  notice text are never carried. Ships carry only their IMO number: the file gives no name, flag or type.
- **Designation dates.** 告示日付 is the notice date (later dates on it are revisions, marked 改訂), so Japan's own
  entries are scored by designation batch, as the EU's and UK's are; UN entries carry no date into the measure.
- **Placement.** "Ukraine (Crimea and eastern Ukraine)" on Russia only (as the EU's UKR and Canada's Ukraine
  regulations); "Russia (third countries)" and the ship ban on Russia (MOF lists the ship file under its Russia
  measures, and all 35 ships are on OFAC's and Canada's Russia lists); North Korea, Syria and Belarus on their
  countries; FRY, 1373 and the settlers program unplaced.
- **Failure.** A page without the two links, a file without the expected columns, an entry number out of form, or
  an unreadable ship file fails the list, keeping the reading before (the ships are never reported as removed).

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

## The legal events strand (18 Nov 2026)
- **What it lists.** A court's decisions as the court publishes them: the court's own case title and number, the
  decision date and the links. Never a summary, a characterization or a score.
- **Which decisions, without judgment.** At a court that decides few cases (the US and UK Supreme Courts, about 50 to
  70 a year), every merits decision. Where the court itself selects (a press release, a decision type), the court's
  own selection. Where neither holds, only a fixed and published text rule, marked as a text match. Never a reading
  of importance or of subject, with one stated exception (Tom, 19 Nov 2026): a court's own subject index may select
  the cases it files under restrictive measures (sanctions), because they bear on Headwind's lists; the item says
  that this is why it is listed.
- **Not measured.** No anomaly test and no indicator: a court's pace says nothing measured about stress. Court items
  are tier `routine` and carry `HW-REQ-2`. The strand has no warning problem; one would need its own hypotheses.
- **One court at a time,** each after its licence and access are read and recorded here.

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

## The UK Supreme Court (18 Nov 2026)
- **What is covered.** Every judgment the Supreme Court of the United Kingdom has handed down this calendar year and
  the last (a neutral citation, `[2026] UKSC 36`, is numbered by calendar year). One item per judgment: appeals
  decided together in one judgment (six cases under `[2025] UKSC 48`) are listed together. Not covered: permission to
  appeal decisions, the Judicial Committee of the Privy Council, hearings and their video.
- **Source: the Court's own site** (supremecourt.uk; Tom chose it on 18 Nov 2026 over The National Archives' Find
  Case Law, whose Open Justice Licence excludes computational analysis without a separate licence). The site has no
  feed, and its case list filters only through a Next.js server action (`updateCases`) whose id changes with every
  build of the site; fetched as a page, `/cases?cs=Judgment+given` ignores the filter and shows the newest 15 cases of
  1,607. Headwind uses the sitemap instead: it lists every case page and, for every case with a judgment, a judgment
  page `/cases/judgments/<case>` with the time it last changed. Checked on 18 Nov 2026 by reading all 160: the 159
  real judgment pages (the 160th, `mock-case-id2`, is a test page that answers 404) cover `[2024] UKSC 1` to `43`,
  `[2025] UKSC 1` to `49` and `[2026] UKSC 1` to `36` with no gap, and none last changed before its hand-down.
- **What is read.** The sitemap and the latest-judgments page every run. Each case page with a judgment page in the
  window is read once (again only if its judgment page changes): the Court's case id, case title, judgment date,
  neutral citation and the links to the Court's PDF and the National Archives' copy. A judgment page last changed
  before 1 January of last year cannot hold a judgment in the window and is not read. A case named on the
  latest-judgments page that the sitemap does not list yet is read too (a cross-check; the sitemap had the newest
  hand-down on 18 Nov 2026). At most 120 case pages and two minutes of reading a run (the workflow job has 15
  minutes); pages left over are read on the next run, newest first, and the page says how many are left. The first
  reading on 18 Nov 2026 read the window's 108 case pages in one go (the whole lane took 1 min 35 s). No judgment
  text, issue, facts, parties' details or written arguments are read.
- **What an item says.** That the Court handed down a judgment, with its neutral citation, on a date, in a case
  or cases named by the Court's own case title and case id (Tom, 15 Nov 2026, for court items), and the links: the
  Court's PDF and the case page. Headwind does not summarize, characterize or score a judgment. A judgment is in the
  feed for 14 days from its judgment date; the page lists the window. Titles are kept exactly as the Court publishes
  them, including a few where the Court's own text has the replacement character U+FFFD in place of an apostrophe
  (in "His Majesty's Revenue and Customs"), because the licence asks for accurate reproduction.
- **`us_person_data`.** The US Supreme Court's test (individuals when either side reads as a person, organizations
  when a side is a non-government organization, none when every side is a government), after a UK clean-up: role
  tags ("(Appellant)"), "R (on the application of X)" (X is the party), "In the matter of", "and others", "No 2". "R"
  alone is the Crown. Company suffixes (Ltd, Limited, Plc, LLP, Inc) are read first and outside brackets, then UK and
  US government words (Secretary of State, His Majesty's Revenue and Customs, Council, Kingdom, Court, and the
  rest), then the organization words. Initials ("BDN", "CHK", "X and Y") are anonymised people, so a side in
  capitals reads as a person, where the US test reads it as an organization. On the 85 judgments of 18 Nov 2026: 50
  individuals, 32 organizations, 3 none. A mistake goes toward individuals (Oatly AB and King Crude Carriers SA read
  as people). The label never keeps a case out.
- **Licence.** The Court's terms and conditions (read 18 Nov 2026): Crown copyright material on the site, other than
  the Royal Arms and departmental logos, may be re-used under the Open Government Licence v3.0 "provided it is
  reproduced accurately and not in a misleading context"; video footage of proceedings is under the Open Supreme
  Court Licence and is not used. Items and the page carry "Contains public sector information licensed under the
  Open Government Licence v3.0." Linking needs no permission (same terms page).

## The Court of Justice of the European Union (19 Nov 2026)
- **What is covered.** Every judgment of the Court of Justice and of the General Court dated in the last 60 days,
  one item per judgment (per CELEX number and ECLI). Not covered: orders, Advocate General opinions, the courts'
  press releases and calendars, and judgments before the window.
- **Source and terms.** The Publications Office's SPARQL endpoint on CELLAR (`publications.europa.eu/webapi/rdf/sparql`,
  keyless), which holds the metadata EUR-Lex shows. EUR-Lex's legal notice (read 19 Nov 2026): "EUR-Lex metadata is
  dedicated to the public domain" under CC0 1.0, and its documents may be reused "for commercial or non-commercial
  purposes" under Decision 2011/833/EU. EUR-Lex's robots.txt (same day) asks a 10-second crawl delay and disallows
  its webservice (`/smartapi`) and document downloads; Headwind sends one query a run to the Publications Office and
  only links to EUR-Lex's document pages, which robots.txt allows. The EUR-Lex webservice (it needs registration)
  and CURIA's own pages are not used. Items, the page and the feed's licence carry "Source: EUR-Lex, © European
  Union, https://eur-lex.europa.eu".
- **What is read.** One query a run for the window, read whole each time, so a judgment whose English heading
  arrives later is updated in place: CELEX number, ECLI, date, court, the Court's own heading (for the formation,
  "Judgment of the Court (Grand Chamber) of ..."), the case numbers and the parties as the Court names them, and the
  Court's subject words, read only for whether they name restrictive measures and not kept. Each judgment has a twin
  record (CELEX `_1`, marked `do_not_index`) that is skipped. When the English version is not out yet, the French
  one (the Court's working language) is read and the page and item say so; a heading the Office has not filled in
  ("__[unreferenced:...]__") gives no formation. A reply that is not SPARQL JSON, or a judgment of an unknown court
  or CELEX form, fails the lane; an empty window (the summer vacation) is a reading. Measured on 19 Nov 2026: a
  judgment of that morning was on the endpoint the same day (record at 10:38 CET, English heading by 14:34); the
  60 days held 221 judgments (110 Court of Justice, 111 General Court), 3 of the Grand Chamber, 18 on restrictive
  measures, 3 not yet in English; the query took about a second.
- **Which go in the feed (the strand's rule above).** The courts decide about 900 cases a year, so not every
  judgment: the Court of Justice's own selection, the judgments of its Grand Chamber and full Court (the formations
  it keeps for its weightiest cases). A judgment whose own subject words name restrictive measures (sanctions) is
  also in the feed, under the rule's one stated exception (Tom, 19 Nov 2026; `cjeu.FEED_RESTRICTIVE_MEASURES`),
  from either court; the item says it is listed because the Court's own subject words name restrictive measures.
  On 19 Nov 2026 that was 18 judgments in the 60 days beside the 3 of the Grand Chamber. 14 days in the feed, 60 on
  the page.
- **What an item says.** That the court gave a judgment (its ECLI) on a date, in a case or cases named by the
  Court's own case numbers and parties, with the formation, why it is listed, and the EUR-Lex link. No summary, no
  characterization, no country (the Court's decisions bind the Union; `countries` is empty, as for UN releases).
- **`us_person_data`.** The UK test with EU words, side by side and also split on "and" (so "Heinz Reinwald and HK
  Evolution LTD" still reads as a person): company forms used across the member states (GmbH, SpA, a.s., sp. z o.o.,
  d.o.o., BV and the rest) are organizations; the EU's institutions, bodies and agencies, member states named alone,
  and government words in English and French are government; everything else, including the initials the Court gives
  anonymised people, is a person. A national authority named in its own language (Skatteverket,
  Maahanmuuttovirasto) reads as a person, so mistakes go toward individuals. On the 221 judgments of 19 Nov 2026: 144
  individuals, 61 organizations, 16 none.

## Who listed a ship first (26 Nov 2026)
- Ships on two or more of the lists that date their ship entries, matched by IMO number: OFAC's SDN list (since 27
  Nov 2026: the "Created" date, `SanctionsEntry/EntryEvent` type 1, in the SDN advanced XML, `sdn_advanced.zip`,
  matched to the entry id of `sdn.csv`; the earliest where an entry has one event per legal basis), the UK Sanctions List
  (DateDesignated), Canada's consolidated list (DateOfListing) and Japan's ship list (its notice date). A list's
  date for a ship is the earliest of its entries for that number. For each two lists: how many ships both list, how
  many each listed first (with the median and largest number of days the other followed) and how many on the same
  day. Every ship's dates are in `data/lead-time.json`.
- "Created" is when OFAC's entry was created. For a ship removed and listed again under a new entry, it is the later
  listing. The date serves this table only; OFAC's batch rule still uses Headwind's own readings. If the advanced XML
  cannot be read, the dates of the reading before are kept.
- France's and Australia's files give no designation date, so their ships are not placed in time; a ship
  also on one of them says so (`also_on_undated`). A list whose ship measure began later can only follow: Japan's
  ship list starts with one notice of 2 Oct 2026, and Canada's ship entries run from 21 Feb 2025.
- These are the publishers' own dates. The table measures the publishers, not Headwind, and says nothing about a
  ship's conduct.

## A move of the US dollar itself (26 Nov 2026)
- Every currency is measured per US dollar, so a move of the dollar shows in all of them at once: on 17 Mar 2020,
  23 of the 29 currencies Headwind reads were unusually weaker the same day. On a day when 10 or more currencies are
  anomalies in the same direction, Headwind reports the move once, as `headwind:fx:usd-broad` (tier anomaly), and
  those currencies' own items stay in the feed as routine, marked `common_move`, with their measures unchanged. A
  currency that moved the other way keeps its own anomaly. The item is published every run: the median currency's
  change per US dollar and how many currencies were unusual each way.
- Back-test on the ECB's file, 2 Jan 2019 to 26 Nov 2026 (2,025 days): 11 days reach 10 currencies in one direction,
  7 reach 15. Measuring each currency net of the median move was tried and not used: it removed most of the broad
  days but raised the flags in ordinary times (897 to 1,057) and still flagged 15 currencies on 17 Mar 2020.
- HW-IND-4 is unchanged: a watched country's currency inside a dollar-wide move does not carry it.

## Names on list changes (`headwind-1.9`, 16 Nov 2026)
- **What is named.** People, organizations and ships added, changed and removed on every list Headwind reads but the
  UN Security Council's: OFAC's SDN list, the EU's, the UK's, France's, Canada's, Australia's and Japan's lists (their
  own designations; Australia's and Japan's UN restatements are counted only), and trade.gov's screening lists. Each named entry carries its name as the publisher prints it ("LAST, First" on OFAC's list, "Nom, Prénom" on
  France's), its type, its programs, the countries of its addresses and nationality as printed, and the listing date
  where the list gives one. Birth dates, identity documents, street addresses, statements of reasons, aliases and
  contact details are not carried. OFAC's countries come from its own address file (`add.csv`); Canada's list prints
  no address or nationality.
- **The EU's name for an entry.** Most EU entries carry several names marked strong, and the file prints them in an
  order that moves between generations. Headwind shows the strong name with the lowest alias id (each EU name keeps
  its id from file to file), and keeps a 12-digit digest of the entry's distinct names, not the names. A name added,
  removed or edited is a change ("its other names changed", or "was" with the name before when the name shown
  moved); the same names in another order are none. Before 27 Nov 2026 Headwind showed the first strong name, and two
  reorders were counted as renames: 1,167 entries on 20 Nov and 3,493 on 26 Nov 2026, every new name one the entry
  already had. Both changes stay in the record, tagged HW-IND-7 (more than half of the change renamed).
- **Why these lists and not the UN's.** Tom, 15 Nov 2026: publish what the licences allow. OFAC's and trade.gov's
  lists are US government works. Canada allows non-commercial reproduction. Australia's DFAT site is CC BY 4.0; Japan's MOF site is under PDL1.0, compatible with CC BY 4.0. France's Licence Ouverte 2.0 and the EU's
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

## HW-WP-1: list changes, HW-IND-1 and HW-IND-7 (register 1.4, 18 Nov 2026)
Tom's yes to the reworded HW-WP-1 (18 Nov 2026). The hypotheses now say what can be seen, not why: HW-H-1A "OFAC
designates ships or a procurement network in one action", HW-H-1B "BIS or USTR extend stays or suspensions before a
scheduled date", HW-H-1C an artefact (publication lag or an identifier correction). HW-IND-1 lost its dual-use network
half, which is a judgment Headwind cannot measure, and HW-H-1C gained an emerging indicator, HW-IND-7.
- **HW-IND-1** is met by an OFAC SDN list change that adds 3 or more ships with IMO numbers (re-keyed ships are not
  additions). Every OFAC change item carries it: `indicator_state` present and `direction` supports, or absent and
  neutral; the measure `vessels_added_with_imo` gives the count.
- **HW-IND-7** is met by a sanctions or screening list change made mostly of renames or re-keyed entries: the entries
  renamed (people, organizations and ships whose name changed), re-keyed (back under a new id with the same IMO
  number, or the same name and type on trade.gov's lists) or renumbered (Canada) are more than half of the entries the
  change touches (added, removed, changed, ships whose details alone changed, re-keyed and renumbered). The item then
  carries HW-IND-7, HW-H-1C, supports and present; otherwise it carries nothing for it. Every list change has the
  measures `renamed_or_rekeyed` and `rename_share`. An OFAC change that meets HW-IND-1 carries HW-IND-1 even when it
  also meets HW-IND-7 (an item has one indicator).
- Both are measurements. The tier stays `routine` (a designation batch can still make it `anomaly`), and which
  hypothesis holds is not judged in the feed.

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
(75 and 135), and since 18 Nov 2026 the EU's sanctions file by its own generation date (14 and 45 days,
provisional); `up` (read, no date to judge) for the rest.

- **Drift.** Each run keeps the size of what a source gave (rows, dates, entries) for its last ten good
  readings. Once there are three, a reading under half the median fails the lane for sources parsed from
  pages or files whose layout Headwind does not control, and the last good copy is kept; under four
  fifths, or for sizes that move on their own (the 60-day window of rules, WFP's countries, FAO's release
  dates, the screening file), it is a warning.
- **Quiet publishers.** A note, not a failure, when a list's own file date has not moved for 3 days
  (UN, which regenerates daily), 14 days (EU, since 18 Nov 2026) or 30 days (UK, France), or when Headwind has
  seen no change on OFAC's list, which carries no date, for 21 days.
- **EU against France** (18 Nov 2026). France restates EU listings in its own register. When France's register
  adds entries under EU programs ("UE ...") on a day after the EU file's own date, the EU entry carries a note with
  their count. Why: on 18 Nov 2026 every EU file was dated 23 Oct while France had restated 151 EU entries on 17
  and 18 Nov, none of them in the EU file, and health showed the EU list as up.
- **Months still under way.** A monthly reading for the current month (WFP posts some countries' months as they
  go) is dated by the publisher's last update of the file, not by the time of the run, so the reading keeps its
  date until WFP posts again (18 Nov 2026: before, each run logged it as changed).

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
