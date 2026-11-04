# Headwind (`D:\Projects\headwind`)

Sanctions deltas, export-control rule deadlines, and strategic commodity benchmark monitor for The Intelligence Company (`tic-feed/2`, program id: `headwind`, prefix: `HW`).

## Architecture
- **Standard library only** (Python 3.11+).
- **`doctrine/`**: Full `tic-doctrine 0.4.1` registers (`HW-REQ-*`, `HW-PIR-*`, `HW-EEI-*`, `HW-WP-*`, `HW-H-*`, `HW-IND-*`, `HW-ASM-*`, `HW-INT-*`).
- **`headwind/sanctions.py`**: Normalizes OFAC SDN delta batches, extracting newly designated shadow-fleet tankers (`imo`, `mmsi`) and dual-use transshipment networks.
- **`headwind/controls.py`**: Normalizes Federal Register (`federalregister.gov/api/v1`) BIS/USTR/OFAC filings and builds `site/data/events.json` for `Verdict`'s `sync_calendar()`.
- **`headwind/commodities.py`**: Tracks FAO Food Price Index (`FFPI`) and International Grains Council (`IGC GOI`) sub-indices.
- **`headwind/feed.py`**: Emits `site/data/feed.geojson` (`tic-feed/2`) with `ncf` mappings (`maintain_supply_chains`, `transport_by_vessel`, `provide_food_products`, `manufacture_equipment`).
