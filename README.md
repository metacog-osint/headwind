# Headwind

**Headwind** is The Intelligence Company's economic-stress monitor. It compares currencies, energy prices and
food prices with their own past changes and marks a series unusual only when a move is far outside that range.
It counts what was added to or removed from official sanctions lists, lists new export-control and sanctions
rules, and collects the dates of coming economic decisions and data releases for Verdict's calendar.

Headwind reports measurements. It states no probability and gives no investment advice.

## Sources
1. **European Central Bank** euro reference rates, restated per US dollar (about 30 currencies).
2. **US Energy Information Administration** spot prices for Brent, WTI and Henry Hub, from EIA's own API (needs a free EIA key).
3. **FAO** Food Price Index and its five sub-indices.
4. **World Food Programme** food prices by market, from the Humanitarian Data Exchange.
5. **World Bank** World Development Indicators, as a slow baseline per country.
6. **Federal Reserve, ECB and FAO** schedule pages, for the calendar.
7. **US Treasury (OFAC)** SDN list, the **UN Security Council** consolidated list, the **EU**'s financial sanctions
   list and the **UK Sanctions List**: changes between readings, as counts. Vessels are named.
8. **US Federal Register**: rules and proposed rules from BIS and OFAC, with the future dates they name.
9. **trade.gov** Consolidated Screening List (every list but the SDN list): changes between readings, as counts.
10. **US Geological Survey** Mineral Commodity Summaries: net import reliance and import sources by commodity,
    marked against the Final 2025 List of Critical Minerals.

## Commands

```bash
python tools/headwind.py collect              # fetch every live lane into data/snapshot.json
python tools/headwind.py build                # build site/, the feed, the calendar and the baseline file
python tools/headwind.py check                # validate the doctrine registers and lint the feed
python -m unittest discover -s tests -v       # offline test suite
```

Method: `doctrine/method.md`.

## Licence

Copyright © 2026 Thomas Brummer, The Intelligence Company. Headwind's code is licensed under the GNU Affero General Public License
v3.0 (`LICENSE`). Third-party and shared files keep their own licences, and data keeps its sources'
terms; both are listed in `NOTICE`.
