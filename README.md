# Headwind

**Headwind** (`headwind.theintelligence.company`) is The Intelligence Company's sanctions deltas, export controls, and strategic commodity benchmark monitor.

It ingests public, free-tier primary sources from:
1. **US Treasury OFAC SDN & Consolidated Sanctions Lists** — Entity and shadow-fleet vessel (IMO / MMSI) additions, deletions, and transshipment-hub designations.
2. **US Federal Register API (BIS, USTR, OFAC, DDTC)** — Public-inspection filings, rule stays, and effective-date deadlines (e.g., BIS Affiliates 50% rule, USTR Section 301 maritime port fees), exported as `site/data/events.json` for `Verdict`'s event calendar (`sync_calendar`).
3. **FAO Food Price Index & IGC Grains and Oilseeds Benchmarks** — Monthly/daily food and agricultural price indices with pre-registrable `tic-feed/2` forecasts.

## Commands

```bash
python tools/headwind.py collect              # build normalized sanctions + Federal Register + commodity snapshot
python tools/headwind.py build                # build site/, site/data/feed.geojson, and site/data/events.json
python tools/headwind.py check                # validate doctrine registers and lint contract-v2 feed
python -m unittest discover -s tests -v       # run offline test suite
```
