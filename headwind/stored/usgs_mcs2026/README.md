# Stored copy: USGS Mineral Commodity Summaries 2026 data release

Two tables from the USGS data release that goes with the Mineral Commodity Summaries 2026
(National Minerals Information Center, 2026, doi:10.5066/P1WKQ63T), as USGS publishes them on ScienceBase:

- `MCS2026_Fig2_Net_Import_Reliance.csv`
- `MCS2026_Fig3_Major_Import_Sources.csv`
- `item.json`: the release's title, dates, and these two files' names, ScienceBase links and MD5 checksums,
  cut from the ScienceBase item record.

The files are byte for byte as downloaded from ScienceBase in November 2026; each matches the MD5 checksum USGS lists for it.
USGS data are in the public domain (CC0 1.0).

Headwind reads the release from ScienceBase on every run. When ScienceBase does not answer, it reads this
copy instead and says so on the site and in its source health. The copy is checked against the USGS checksums
each time. It stands for the 2026 edition only; a new edition needs a new copy, made when `EDITION` in
`headwind/minerals.py` changes.
