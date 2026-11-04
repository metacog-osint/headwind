# Headwind Method (`headwind-1.0`)

## Purpose
Headwind monitors sanctions list deltas (OFAC SDN entities and shadow-fleet vessels), export-control rule deadlines (BIS / USTR Federal Register filings), and global food/commodity benchmarks (FAO FFPI, IGC GOI).

## Key Analytic Streams
1. **OFAC SDN & Maritime Shadow-Fleet Deltas (`ofac_sdn_deltas`)**:
   - Tracks batch additions of entities and crude/product tankers (`IMO`, `MMSI`, flag state), cross-referencing vessel MMSIs against `Wake`'s Baltic and Red Sea AIS tracks.
2. **Export Controls & Rule-Stay Deadlines (`federal_register_bis_ustr`)**:
   - Monitors BIS and USTR dockets (including the BIS Affiliates 50% rule `90 FR 47201` / `90 FR 50857` and USTR Section 301 maritime port-fee action `2026-21755`) and exports dated deadlines to `site/data/events.json` for `Verdict`'s `sync_calendar()`.
3. **Strategic Commodity Benchmarks (`fao_ffpi_igc`)**:
   - Compares high-frequency IGC Grains and Oilseeds Index (`GOI`) movements against the monthly FAO Food Price Index (`FFPI`) release calendar.
