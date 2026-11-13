# Headwind

**Headwind** is The Intelligence Company's economic-stress monitor. It compares currencies, energy prices and
food prices with their own past changes and marks a series unusual only when a move is far outside that range.
It also collects the dates of coming economic decisions and data releases for Verdict's calendar.

Headwind reports measurements. It states no probability and gives no investment advice.

## Sources
1. **European Central Bank** euro reference rates, restated per US dollar (about 30 currencies).
2. **US Energy Information Administration** spot prices for Brent, WTI and Henry Hub, read through FRED.
3. **FAO** Food Price Index and its five sub-indices.
4. **World Food Programme** food prices by market, from the Humanitarian Data Exchange.
5. **World Bank** World Development Indicators, as a slow baseline per country.
6. **Federal Reserve, ECB and FAO** schedule pages, for the calendar.

Sanctions (OFAC) and export-control rule dates (Federal Register) are planned lanes with no collector yet.

## Commands

```bash
python tools/headwind.py collect              # fetch every live lane into data/snapshot.json
python tools/headwind.py build                # build site/, the feed, the calendar and the baseline file
python tools/headwind.py check                # validate the doctrine registers and lint the feed
python -m unittest discover -s tests -v       # offline test suite
```

Method: `doctrine/method.md`.
