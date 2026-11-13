# Headwind method (`headwind-1.2`)

## Purpose
Headwind measures economic stress: currencies, energy and food prices that move outside their own
normal range, changes to official sanctions lists, new export-control and sanctions rules, and the
scheduled dates on which economic decisions and figures are published.
It reports measurements. It states no probability and gives no investment advice.

## Live lanes (13 Nov 2026)

| Lane | Source | Cadence | Measure |
|---|---|---|---|
| Exchange rates | ECB euro reference rates, restated per US dollar | TARGET business days | 5-day change against the currency's own 250 prior 5-day changes |
| Energy | EIA spot prices for Brent, WTI and Henry Hub, read through FRED | Trading days, a day or two late | Same, with a 5% floor |
| Food indices | FAO Food Price Index and five sub-indices | Monthly | 1-month change against 120 prior monthly changes |
| Local food prices | WFP prices by market, from the Humanitarian Data Exchange | Monthly, one to three months late | Median 3-month change across a country's price series, against its own 60 prior medians |
| Country baseline | World Bank World Development Indicators | Annual | No anomaly test; context only, in `data/baseline.json` |
| Calendar | Federal Reserve, ECB and FAO schedule pages | As published | Dates for Verdict's calendar, in `data/events.json` |
| Sanctions lists | OFAC SDN list (`sdn.csv`); UN Security Council consolidated list (XML) | As the publishers update them | Entries added and removed since Headwind's last reading, by type and program |
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
  with a parallel market are understated or absent (assumption `HW-ASM-2`).
- **Nominal prices.** WFP prices are in local currency and not adjusted for inflation; the test
  against a country's own history is what makes them comparable.
- **Revisions.** FAO revises earlier months. Each snapshot keeps the last twelve months as issued.
  The other lanes keep only the raw files under `data/raw/` (git-ignored).
- **Stale local prices.** A country whose newest WFP month is more than four months old is listed
  on the page as having no recent data and is left out of the feed.

## Sanctions lists and rules
A list change is the difference between two of Headwind's own readings of an official list, matched on
the publisher's entry id. It is reported as counts by type (individual, entity, vessel, aircraft) and
by sanctions program. Headwind does not republish names; the item links to the official list.

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

## Not live
trade.gov Consolidated Screening List diffs (BIS Entity List and others), critical minerals, EU and UK
sanctions lists, USTR notices and Federal Register public-inspection filings.

## Verdict
`data/question_drafts.json` holds draft questions on the next FAO release with a climatology
baseline (the share of the last 120 months in which the index rose). They are drafts; nothing is
registered by Headwind.
