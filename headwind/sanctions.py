"""Sanctions lists: what was added or removed since Headwind last looked.

Six official lists, all keyless: the US Treasury's SDN list (OFAC, sdn.csv, with its address file add.csv),
the UN Security Council consolidated list (XML), the EU's Financial Sanctions Files (XML), the UK Sanctions List
(FCDO, XML), France's Registre national des gels (JSON) and Canada's consolidated list (XML). Each run reduces a
list to an index of entry id -> [type, groups, details], compares it with the index kept from the run before, and
reports the difference by type and by sanctions program, naming what changed.

Names (`headwind-1.9`, Tom, 15-16 Nov 2026: publish what the licences allow): people and organizations on every
list but the UN's carry their name as the publisher prints it and the countries of their addresses and
nationality (`names.py`); vessels carry name, IMO number, MMSI, flag and type, as since 13 Nov 2026. Owners, birth
dates, identity documents, street addresses and reasons are never carried. The UN list stays [type, list type]:
its terms bar redistribution, so no UN text goes into the index, the state or the page.

What a delta means: the change between two of Headwind's own readings. The date on it is when
Headwind saw the change, not the date of the designation.
"""
from __future__ import annotations

import csv
import io
import json
import re
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timedelta

from . import batches, screening
from . import names as nm

OFAC_SDN_CSV = "https://www.treasury.gov/ofac/downloads/sdn.csv"
OFAC_ADD_CSV = "https://www.treasury.gov/ofac/downloads/add.csv"     # addresses: only the country is kept
UN_XML = "https://scsanctions.un.org/resources/xml/en/consolidated.xml"
OFAC_RECENT = "https://ofac.treasury.gov/recent-actions"
UN_PAGE = "https://main.un.org/securitycouncil/en/content/un-sc-consolidated-list"
# The EU's Financial Sanctions Files: the token is the public one the Commission's own RSS feed and the
# EU open data portal give for these files. About 26 MB; the Commission's server takes about 30 s.
EU_XML = "https://webgate.ec.europa.eu/fsd/fsf/public/files/xmlFullSanctionsList_1_1/content?token=dG9rZW4tMjAxNw"
EU_PAGE = ("https://data.europa.eu/data/datasets/"
           "consolidated-list-of-persons-groups-and-entities-subject-to-eu-financial-sanctions")
# The UK Sanctions List (FCDO), the only UK list since OFSI's Consolidated List closed on 28 Jan 2026.
UK_XML = "https://sanctionslist.fcdo.gov.uk/docs/UK-Sanctions-List.xml"
UK_PAGE = "https://www.gov.uk/government/publications/the-uk-sanctions-list"
# France's Registre national des gels (Direction générale du Trésor): the JSON its public API gives, about 15 MB.
# A HEAD request answers 405; GET works. Licence Ouverte 2.0 (the data.gouv.fr record, read 15 Nov 2026).
FR_JSON = "https://gels-avoirs.dgtresor.gouv.fr/ApiPublic/api/v1/publication/derniere-publication-fichier-json"
FR_PAGE = "https://gels-avoirs.dgtresor.gouv.fr/"
# Canada's Consolidated Canadian Autonomous Sanctions List (Global Affairs Canada), XML, about 2.9 MB. Canada.ca's
# terms (read 15 Nov 2026) allow reproduction for non-commercial purposes.
CA_XML = ("https://www.international.gc.ca/world-monde/assets/office_docs/international_relations-relations_internationales/"
          "sanctions/sema-lmes.xml")
CA_PAGE = ("https://www.international.gc.ca/world-monde/international_relations-relations_internationales/"
           "sanctions/consolidated-consolide.aspx?lang=eng")

LISTS = {
    "ofac-sdn": {"name": "OFAC SDN list", "publisher": "US Treasury (OFAC)", "url": OFAC_RECENT, "min_entries": 5000},
    "un-consolidated": {"name": "UN Security Council consolidated list", "publisher": "United Nations Security Council",
                        "url": UN_PAGE, "min_entries": 300},
    "eu-fsf": {"name": "EU financial sanctions list", "publisher": "European Commission (Financial Sanctions Files)",
               "url": EU_PAGE, "min_entries": 3000},
    "uk-sanctions": {"name": "UK Sanctions List", "publisher": "UK Foreign, Commonwealth and Development Office",
                     "url": UK_PAGE, "min_entries": 3000},
    "france-gels": {"name": "France's asset-freeze register (Registre national des gels)",
                "publisher": "French Treasury (Direction générale du Trésor)", "url": FR_PAGE, "min_entries": 3000},
    "canada-sema": {"name": "Consolidated Canadian Autonomous Sanctions List", "publisher": "Global Affairs Canada",
                    "url": CA_PAGE, "min_entries": 3000},
}

# EU programme codes, as the Financial Sanctions Files give them, that name a country. Read against the
# live file on 14 Nov 2026 (34 codes). "UKR" is the EU's regime on undermining Ukraine's territorial
# integrity; it is placed on Russia only (Tom, 14 Nov 2026): of its 2,962 entries, 1,609 give a Russian address
# or citizenship and 86 a Ukrainian one, so placing it on Ukraine too would mark Ukraine on nearly every EU
# change. "SDNZ" is placed on Sudan (Tom, 14 Nov 2026): its 25 entries carry Sudanese addresses (8) and UAE
# ones (3) and cite EU acts on Sudan such as 2024/384; "SDN" (9 entries) is the older Sudan regime. Left
# unplaced on purpose: TAQA and EUAQ (ISIL and Al-Qaida), TERR (terrorism), HAM (Hamas and Palestinian
# Islamic Jihad), HR (global human rights), CHEM (chemical weapons), CYB (cyber attacks) and UNLI (UN
# listings carried before an EU act).
EU_PROGRAMME_COUNTRY = {
    "UKR": "RU", "SDNZ": "SD", "RUS": "RU", "RUSDA": "RU", "BLR": "BY", "IRN": "IR", "SYR": "SY", "PRK": "KP", "AFG": "AF",
    "MMR": "MM", "COD": "CD", "IRQ": "IQ", "VEN": "VE", "LBY": "LY", "MDA": "MD", "TUN": "TN", "SDN": "SD", "SSD": "SS",
    "SOM": "SO", "NIC": "NI", "CAF": "CF", "HTI": "HT", "YEM": "YE", "GTM": "GT", "GIN": "GN", "MLI": "ML",
}
EU_UNPLACED = {"TAQA", "EUAQ", "TERR", "HAM", "HR", "CHEM", "CYB", "UNLI"}

# UK regimes by short name (uk_regime()), read against the live list on 14 Nov 2026 (31 regimes).
UK_REGIME_COUNTRY = {
    "Russia": "RU", "Syria": "SY", "Iran": "IR", "Iran (Nuclear)": "IR", "Democratic People's Republic of Korea": "KP",
    "Republic of Belarus": "BY", "Afghanistan": "AF", "Myanmar": "MM", "Iraq": "IQ",
    "Democratic Republic of the Congo": "CD", "Libya": "LY", "Sudan": "SD", "Venezuela": "VE",
    "Central African Republic": "CF", "Somalia": "SO", "Yemen": "YE", "Nicaragua": "NI",
    "Republic of Guinea-Bissau": "GW", "South Sudan": "SS", "Haiti": "HT", "Guinea": "GN",
    "Bosnia and Herzegovina": "BA", "Mali": "ML",
}
UK_UNPLACED = {"Isil (Da'esh) and Al-Qaeda (United Nations Sanctions)", "Global Human Rights", "Cyber",
               "Global Anti-Corruption", "Counter-Terrorism (International Sanctions)", "Counter-Terrorism",
               "Global Irregular Migration and Trafficking in Persons", "Chemical Weapons"}

# Canada's regimes, by the English half of the list's Country field (canada_regime()), read against the live list
# on 16 Nov 2026 (19 regimes). "Ukraine" is Canada's Special Economic Measures (Ukraine) Regulations; it is placed on
# Russia only, as Tom placed the EU's UKR on 14 Nov 2026 (kept
# on his yes to item 3, 16 Nov 2026). Left unplaced on purpose:
# JVCFOR (corrupt foreign officials), Hamas Terrorist Attacks, Extremist Settler Violence (conduct regimes).
CA_REGIME_COUNTRY = {
    "Russia": "RU", "Ukraine": "RU", "Iran": "IR", "Belarus": "BY", "Syria": "SY", "Myanmar (Burma)": "MM",
    "Venezuela": "VE", "Zimbabwe": "ZW", "Moldova": "MD", "Nicaragua": "NI", "Haiti": "HT", "Sudan": "SD",
    "China": "CN", "Guatemala": "GT", "Sri Lanka": "LK", "South Sudan": "SS",
}
CA_UNPLACED = {"Justice for Victims of Corrupt Foreign Officials Regulations (JVCFOR)", "Hamas Terrorist Attacks",
               "Extremist Settler Violence"}

LIST_COUNTRY = {"eu-fsf": (EU_PROGRAMME_COUNTRY, EU_UNPLACED), "uk-sanctions": (UK_REGIME_COUNTRY, UK_UNPLACED),
                "canada-sema": (CA_REGIME_COUNTRY, CA_UNPLACED)}
KEEP_DAYS = 30          # how long a delta stays in the snapshot
SHRINK_LIMIT = 0.5      # a list that loses more than half its entries is a broken download, not a delisting

# Sanctions programs that name a country (a tuple where a program is about two). Programs aimed at
# conduct (terrorism, narcotics, cyber, Global Magnitsky) are left out on purpose: their targets sit
# in many countries and the list does not say which. Tags were read against OFAC's program tag
# definitions page on 13 Nov 2026.
PROGRAM_COUNTRY = {
    "RUSSIA": "RU", "UKRAINE": "RU", "IRAN": "IR", "IFSR": "IR", "IFCA": "IR", "IRGC": "IR", "HRIT": "IR", "NPWMD": None,
    "DPRK": "KP", "CUBA": "CU", "SYRIA": "SY", "VENEZUELA": "VE", "BELARUS": "BY", "BURMA": "MM", "LIBYA": "LY",
    "IRAQ": "IQ", "SUDAN": "SD", "DARFUR": "SD", "SOUTH SUDAN": "SS", "SOMALIA": "SO", "YEMEN": "YE", "CAR": "CF",
    "DRCONGO": "CD", "MALI": "ML", "NICARAGUA": "NI", "ETHIOPIA": "ET", "LEBANON": "LB", "ZIMBABWE": "ZW",
    "HONG KONG": "HK", "BALKANS": None, "AFGHANISTAN": "AF", "HAITI": "HT",
    # Tags the prefix rule misplaced or missed, found against the live list on 13 Nov 2026
    "HRIT-SY": "SY", "CAATSA - RUSSIA": "RU", "CAATSA - IRAN": "IR", "MAGNIT": "RU", "PEESA": "RU",
    "SSIDES": "RU",          # the 2014 Ukraine support act, in OFAC's Ukraine/Russia program (not South Sudan)
    "UHRPA": "CN",
    "PAARSSR": "SY",         # EO 13894 as amended: accountability for Assad and regional stabilization
    # OFAC's Ukraine/Russia program. EO 13661 and 13662 name Russian officials and sectors; EO 13660
    # (undermining Ukraine) and EO 13685 (Crimea) are about both countries (Tom, 13 Nov 2026).
    "UKRAINE-EO13660": ("RU", "UA"), "UKRAINE-EO13685": ("RU", "UA"),
    # UN list types
    "Iran": "IR", "Iraq": "IQ", "DRC": "CD", "Libya": "LY", "Somalia": "SO", "Sudan": "SD", "Haiti": "HT",
    "Yemen": "YE", "GB": "GW", "SouthSudan": "SS", "Taliban": "AF",
}


def countries_for(groups, list_id: str | None = None) -> list[str]:
    if list_id == "france-gels":
        # France's national freezes are conduct measures (the Code monétaire et financier's articles L. 562-2 and
        # following), and its EU and UN entries restate measures Headwind reads on those lists (Tom, 15 Nov 2026:
        # no countries from restatements). So a change on the French register places no country.
        return []
    out = set()
    for g in groups:
        if list_id in LIST_COUNTRY:
            cc = LIST_COUNTRY[list_id][0].get(g)
        else:
            cc = PROGRAM_COUNTRY.get(g) or PROGRAM_COUNTRY.get(re.split(r"[-\d]", g, maxsplit=1)[0].strip())
        if cc:
            out.update((cc,) if isinstance(cc, str) else cc)
    return sorted(out)


def unknown_programs(list_id: str, index: dict) -> list[str]:
    """Programs on an EU or UK list that are neither placed on a country nor left unplaced on purpose:
    a new regime, to be read and added to the maps above."""
    if list_id == "france-gels":
        return sorted({g for e in index.values() for g in e[1] if fr_origin(g) == "unknown"})
    if list_id not in LIST_COUNTRY:
        return []
    placed, unplaced = LIST_COUNTRY[list_id]
    return sorted({g for e in index.values() for g in e[1]} - set(placed) - unplaced)


def uk_regime(name: str) -> str:
    """'The Iran (Sanctions) (Nuclear) (EU Exit) Regulations 2019' -> 'Iran (Nuclear)'."""
    s = re.sub(r"^The\s+", "", (name or "").strip())
    s = re.sub(r"\s*\((?:Sanctions|EU Exit)\)", "", s)
    s = re.sub(r"\s*(?:Sanctions\s+)?Regulations\s+\d{4}$", "", s)
    return " ".join(s.split()) or "none stated"


EU_NS = {"e": "http://eu.europa.ec/fpi/fsd/export"}
EU_TYPE = {"person": "individual", "enterprise": "entity"}


def parse_eu_xml(body: bytes, dates: dict | None = None) -> tuple[str | None, dict[str, list]]:
    """The EU Financial Sanctions Files, XML v1.1: one sanctionEntity per entry, keyed on its logicalId.
    The EU file lists people and organizations only; vessels under EU measures are in regulation
    annexes, not in this file. `dates`, when given, is filled with each entry's designation date (or None):
    kept for the batch measure only, never in the index or the state."""
    root = ET.fromstring(body)
    index = {}
    for e in root.findall("e:sanctionEntity", EU_NS):
        lid = (e.get("logicalId") or "").strip()
        if not lid:
            continue
        st = e.find("e:subjectType", EU_NS)
        code = st.get("code") if st is not None else None
        programmes = sorted({r.get("programme") for r in e.findall("e:regulation", EU_NS) if r.get("programme")})
        index[lid] = [EU_TYPE.get(code, code or "unknown"), programmes, _eu_details(e)]
        if dates is not None:
            dates[lid] = _iso_day(e.get("designationDate"))
    return root.get("generationDate"), index


def _eu_details(e) -> dict:
    """The name the EU marks strong (else the first given) and the country codes of the entry's citizenships and
    addresses. Birth dates, functions, identity documents and remarks are not carried."""
    aliases = [a for a in e.findall("e:nameAlias", EU_NS) if nm.clean(a.get("wholeName"))]
    pick = next((a for a in aliases if a.get("strong") == "true"), aliases[0] if aliases else None)
    cs = [x.get("countryIso2Code") for tag in ("e:citizenship", "e:address") for x in e.findall(tag, EU_NS)]
    return nm.details(pick.get("wholeName") if pick is not None else None, [c for c in cs if c and c != "00"])


def _iso_day(text: str | None) -> str | None:
    t = (text or "").strip()[:10]
    return t if re.fullmatch(r"\d{4}-\d{2}-\d{2}", t) else None


def _uk_date(text: str | None) -> str | None:
    m = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", (text or "").strip())
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else None


UK_TYPE = {"Individual": "individual", "Entity": "entity", "Ship": "vessel"}
_QUOTES = "\"'\u201c\u201d\u2018\u2019"
_IMO_NAME = re.compile(r"IMO\s*\d{7}\s*(?:\((.*)\))?")


def uk_ship_name(primary: str | None, aliases: list[str]) -> tuple[str | None, bool]:
    """The ship's name in an FCDO entry, and whether it came from an alias.

    FCDO names many of the ships it specifies by IMO number: 'IMO 9344411 ("GALLE ENERGY")', with or without
    the quotes, or 'IMO 9958303' alone with the ship's name given only as an alias (the 12 Nov 2026 notice
    lists all eleven of that day's ships so). The name is the part in brackets, else the first alias that is
    not itself an IMO number. A primary name in any other form is kept as printed."""
    m = _IMO_NAME.fullmatch(" ".join((primary or "").split()))
    if not m:
        return primary or None, False
    inner = (m.group(1) or "").strip().strip(_QUOTES).strip()
    if inner:
        return inner, False
    for a in aliases:
        a = " ".join((a or "").split()).strip(_QUOTES).strip()
        if a and not _IMO_NAME.fullmatch(a):
            return a, True
    return None, False


def _uk_names(d) -> tuple[str | None, list[str]]:
    """The primary name (Name1 to Name6 joined, as FCDO prints them) and the aliases of a UK designation."""
    primary, aliases = None, []
    for n in d.findall("Names/Name"):
        kind = (n.findtext("NameType") or "").strip().lower()                    # the file has both cases
        text = " ".join(filter(None, ((n.findtext(f"Name{i}") or "").strip() for i in (1, 2, 3, 4, 5, 6))))
        if kind == "primary name" and primary is None:
            primary = text or None
        elif kind == "alias" and text:
            aliases.append(text)
    return primary, aliases


def _uk_details(d) -> dict:
    """A UK person or organization: primary name, and the countries of its addresses and nationalities as
    printed. Birth details, identifiers, statements of reasons, phones, emails and street addresses are not carried."""
    cs = [x.text for x in d.findall("Addresses/Address/AddressCountry")] + \
        [x.text for x in d.findall("IndividualDetails/Individual/Nationalities/Nationality")]
    return nm.details(_uk_names(d)[0], cs)


def _uk_ship(d) -> dict:
    """The public fields of a UK ship designation: name, IMO number, flag and type. Owners and operators
    are left out, as for OFAC. `name_is_alias` marks a name FCDO gives only as an alias, the entry itself being
    named by IMO number."""
    primary, aliases = _uk_names(d)
    name, from_alias = uk_ship_name(primary, aliases)
    imo = (d.findtext("ShipDetails/Ship/IMONumbers/IMONumber") or "").strip()
    imo = re.sub(r"^IMO\s*", "", imo)
    out = {"name": name, "imo": imo if re.fullmatch(r"\d{7}", imo) else None, "mmsi": None,
           "flag": (d.findtext("ShipDetails/Ship/CurrentBelievedFlagOfShips/CurrentBelievedFlagOfShip") or "").strip() or None,
           "vessel_type": (d.findtext("ShipDetails/Ship/TypeOfShipDetails/TypeOfShip") or "").strip() or None}
    if from_alias:
        out["name_is_alias"] = True
    return out


def parse_uk_xml(body: bytes, dates: dict | None = None) -> tuple[str | None, dict[str, list]]:
    """The UK Sanctions List XML: one Designation per entry, keyed on its UniqueID, grouped by regime. `dates`, when
    given, is filled with each entry's DateDesignated."""
    root = ET.fromstring(body)
    index = {}
    for d in root.findall("Designation"):
        uid = (d.findtext("UniqueID") or "").strip()
        if not uid:
            continue
        kind = UK_TYPE.get((d.findtext("IndividualEntityShip") or "").strip(), "unknown")
        entry = [kind, [uk_regime(d.findtext("RegimeName"))]]
        entry.append(_uk_ship(d) if kind == "vessel" else _uk_details(d))
        index[uid] = entry
        if dates is not None:
            dates[uid] = _uk_date(d.findtext("DateDesignated"))
    return _uk_date(root.findtext("DateGenerated")), index


def parse_add_csv(text: str) -> dict[str, list[str]]:
    """OFAC's address file (add.csv, no header: uid, address number, street, city, country, remarks): the
    countries of each entry's addresses. Only the country is kept."""
    out: dict[str, set] = {}
    for row in csv.reader(io.StringIO(text)):
        if len(row) > 4 and row[0].strip().isdigit() and _blank(row[4]):
            out.setdefault(row[0].strip(), set()).add(row[4].strip())
    return {k: sorted(v) for k, v in out.items()}


def parse_sdn_csv(text: str, addresses: dict | None = None) -> dict[str, list]:
    """sdn.csv has no header: uid, name, type, programs, ... A blank type ("-0-") is an entity. A person or
    organization carries its name as printed ("LAST, First" for people) and, from `addresses` (parse_add_csv),
    the countries of its addresses."""
    index = {}
    for row in csv.reader(io.StringIO(text)):
        if len(row) < 4 or not row[0].strip().isdigit():
            continue
        kind = row[2].strip()
        programs = [p.strip() for p in re.split(r"\]\s*\[", row[3].strip().strip("[]")) if p.strip() and p.strip() != "-0-"]
        entry = ["entity" if kind in ("", "-0-") else kind, sorted(programs)]
        uid = row[0].strip()
        entry.append(_vessel(row) if kind == "vessel" else nm.details(_blank(row[1]), (addresses or {}).get(uid)))
        index[uid] = entry
    return index


def _blank(s: str) -> str | None:
    s = (s or "").strip()
    return None if s in ("", "-0-") else s


def _vessel(row: list[str]) -> dict:
    """The public vessel fields of an sdn.csv row. The owner column is left out: it can name a person."""
    remarks = row[11] if len(row) > 11 else ""
    imo = re.search(r"\bIMO\s+(\d{7})\b", remarks)
    mmsi = re.search(r"\bMMSI\s+(\d{9})\b", remarks)
    return {"name": _blank(row[1]), "imo": imo.group(1) if imo else None, "mmsi": mmsi.group(1) if mmsi else None,
            "flag": _blank(row[9]) if len(row) > 9 else None, "vessel_type": _blank(row[6]) if len(row) > 6 else None}


def _vessels(index: dict, ids) -> list[dict]:
    """Vessels among these entry ids, with their identifiers. An index written before 13 Nov 2026
    holds no vessel details; those vessels are counted but cannot be named. A vessel with an IMO number
    and no name is listed by its number."""
    out = []
    for i in ids:
        e = index[i]
        if e[0] == "vessel" and len(e) > 2 and (e[2].get("name") or e[2].get("imo")):
            out.append({"list_id": i, **e[2], "programs": e[1]})
    return sorted(out, key=lambda v: (v["name"] or "", v["imo"] or ""))


def parse_un_xml(body: bytes, dates: dict | None = None) -> tuple[str | None, dict[str, list]]:
    """`dates`, when given, is filled with each entry's LISTED_ON date."""
    root = ET.fromstring(body)
    index = {}
    for section, kind in (("INDIVIDUALS", "individual"), ("ENTITIES", "entity")):
        sec = root.find(section)
        for e in (sec if sec is not None else []):
            dataid = (e.findtext("DATAID") or "").strip()
            if dataid:
                index[dataid] = [kind, [(e.findtext("UN_LIST_TYPE") or "unknown").strip()]]
                if dates is not None:
                    dates[dataid] = _iso_day(e.findtext("LISTED_ON"))
    return root.get("dateGenerated"), index


FR_TYPE = {"Personne physique": "individual", "Personne morale": "entity", "Navire": "vessel"}
FR_NATIONAL = "FR national"
# A legal basis reads "<act> du <date> (<regime>)", the regime in the last brackets, which may hold brackets of its
# own: "(UE) 2022/332 du 25/02/2022 (UE Ukraine intégrité territoriale - R (UE) 269/2014)".
_FR_REGIME = re.compile(r"\(([^()]*(?:\([^()]*\)[^()]*)*)\)\s*$")
_FR_ARTICLE = re.compile(r"art\.?\s*(L\.?\s*\d[\d-]*)")


def fr_regime(label: str | None) -> str:
    """The group a French legal basis counts under: the regime as printed, up to its first " - ", so
    'UE Ukraine intégrité territoriale' or 'ONU Corée du Nord'; a French national freeze is 'FR national, art
    L. 562-2' (the regime 'Dispositif national de gel des avoirs - art L. 562-2 du code monétaire et financier')."""
    m = _FR_REGIME.search((label or "").strip())
    reg = " ".join(m.group(1).split()) if m else ""
    if reg.startswith("Dispositif national"):
        art = _FR_ARTICLE.search(reg)
        return f"{FR_NATIONAL}, art {' '.join(art.group(1).split())}" if art else FR_NATIONAL
    return re.split(r"\s+-\s+", reg, maxsplit=1)[0].strip() or "none stated"


def fr_origin(group: str) -> str:
    """national, EU or UN: who took the measure a French group stands for. Checked 15 Nov 2026 on the 6 Nov file:
    every one of its 1,107 legal bases is one of the three."""
    if group.startswith(FR_NATIONAL):
        return "national"
    if group.startswith("UE ") or group == "UE":
        return "EU"
    if group.startswith("ONU ") or group == "ONU":
        return "UN"
    return "unknown"


def is_fr_national(entry: list) -> bool:
    return any(fr_origin(g) == "national" for g in entry[1])


def fr_ship_name(nom: str | None) -> str | None:
    """A ship's name on the French register. Copies to Aug 2026 named North Korea's ships after their owner,
    '<company> - navire HUI CHON'; the owner is cut (owners are never carried) and the ship's name kept."""
    n = " ".join((nom or "").split())
    m = re.search(r"\s-\s+navire\s+(.+)$", n, re.IGNORECASE)
    return (m.group(1).strip() if m else n) or None


def parse_fr_json(body: bytes) -> tuple[str | None, dict[str, list]]:
    """France's register, keyed on IdRegistre: [type, groups] with the groups from each legal basis (fr_regime).
    Ships carry their name and IMO number (NUMERO_OMI); the register gives no flag, type or MMSI. People and
    organizations carry their name ("Nom, Prénom" for people) and the countries of their nationality and addresses
    as printed; birth dates, passports, identification, reasons and contact details are not carried. The file
    carries no designation date (only the date of each act in its label)."""
    pub = json.loads(body.decode("utf-8-sig"))["Publications"]
    index = {}
    for r in pub.get("PublicationDetail") or []:
        rid = str(r.get("IdRegistre") or "").strip()
        if not rid:
            continue
        kind = FR_TYPE.get((r.get("Nature") or "").strip(), "unknown")
        fields = {c.get("TypeChamp"): c.get("Valeur") or [] for c in r.get("RegistreDetail") or []}
        groups = sorted({fr_regime(v.get("FondementJuridiqueLabel")) for v in fields.get("FONDEMENT_JURIDIQUE", [])})
        entry = [kind, groups or ["none stated"]]
        if kind == "vessel":
            imo = next((str(v.get("NumeroOMI") or "").strip() for v in fields.get("NUMERO_OMI", [])), "")
            entry.append({"name": fr_ship_name(r.get("Nom")), "imo": imo if re.fullmatch(r"\d{7}", imo) else None,
                          "mmsi": None, "flag": None, "vessel_type": None})
        else:
            first = nm.clean(next((v.get("Prenom") for v in fields.get("PRENOM", []) if v.get("Prenom")), None))
            nom = nm.clean(r.get("Nom"))
            cs = [v.get("Pays") for t in ("NATIONALITE", "ADRESSE_PP", "ADRESSE_PM") for v in fields.get(t, [])]
            entry.append(nm.details(f"{nom}, {first}" if nom and first else nom or first, cs))
        index[rid] = entry
    return pub.get("DatePublication"), index


def canada_regime(country: str | None) -> str:
    """'Belarus / Bélarus' -> 'Belarus'; 'Moldova ' -> 'Moldova'. The English half of Canada's bilingual field."""
    return " ".join((country or "").split(" / ", 1)[0].split()) or "none stated"


def _ca_schedule(text: str | None) -> str:
    """'1,Part 3' and '1, Part 1 ' -> '1, Part 3' and '1, Part 1': the same schedule written two ways."""
    return " ".join(re.sub(r",\s*", ", ", (text or "").strip()).split())


def canada_key(rec) -> str:
    """Canada's list gives no entry id. A record is its regime, schedule and item number, which are unique on the
    16 Nov 2026 file (5,781 of 5,781; schedule and item alone are not: 792 clashes). Item numbers could be reused or
    renumbered; that is checked against a second copy before removals are trusted (see method.md)."""
    return "|".join((canada_regime(rec.findtext("Country-Pays")), _ca_schedule(rec.findtext("Schedule-Annexe")),
                     (rec.findtext("Item-NumeroDarticle") or "").strip()))


def parse_canada_xml(body: bytes, dates: dict | None = None,
                     names: dict | None = None) -> tuple[str | None, dict[str, list]]:
    """Canada's consolidated list: [type, [regime]] per record, keyed by canada_key. A ship (one with an IMO number)
    carries its name, IMO number and type; the list gives no flag. A record with a person's name is an individual
    ("Last, Given"), any other an entity, with its name. The list prints no address or nationality. `dates`, when
    given, is filled with each DateOfListing; `names` with a 12-character hash of each record's name
    (screening.name_key), for the renumbering guard."""
    root = ET.fromstring(body)
    recs = root.findall("record")
    if recs and not any(r.find("Country-Pays") is not None for r in recs):
        # Canada renamed every tag between its June and August 2026 files (Country to Country-Pays, and so on).
        raise ValueError("canada-sema: no record has a Country-Pays field; the file's layout has changed")
    index = {}
    for r in recs:
        key = canada_key(r)
        imo = (r.findtext("ShipIMONumber-NumeroOMIDuNavire") or "").strip()
        named = (r.findtext("LastName-NomDeFamille") or r.findtext("GivenName-Prenom") or "").strip()
        if imo:
            kind = "vessel"
        elif named and not (r.findtext("EntityOrShip-EntiteOuNavire") or "").strip():
            kind = "individual"
        else:
            kind = "entity"
        entry = [kind, [canada_regime(r.findtext("Country-Pays"))]]
        if kind == "vessel":
            vtype = (r.findtext("TitleOrShipType-TitreOuTypeDeNavire") or "").split(" | ", 1)[0].strip()
            entry.append({"name": " ".join((r.findtext("EntityOrShip-EntiteOuNavire") or "").split()) or None,
                          "imo": imo if re.fullmatch(r"\d{7}", imo) else None, "mmsi": None, "flag": None,
                          "vessel_type": vtype or None})
        elif kind == "individual":
            last, given = nm.clean(r.findtext("LastName-NomDeFamille")), nm.clean(r.findtext("GivenName-Prenom"))
            entry.append(nm.details(f"{last}, {given}" if last and given else last or given))
        else:
            entry.append(nm.details(r.findtext("EntityOrShip-EntiteOuNavire")))
        if key in index:
            raise ValueError(f"canada-sema: two records share the key {key}")
        index[key] = entry
        if dates is not None:
            dates[key] = _iso_day(r.findtext("DateOfListing-DateDinscription"))
        if names is not None:
            whole = " ".join(filter(None, ((r.findtext(t) or "").strip() for t in (
                "LastName-NomDeFamille", "GivenName-Prenom", "EntityOrShip-EntiteOuNavire"))))
            names[key] = screening.name_key(whole)
    return None, index


def canada_renumbered(prev_index: dict, index: dict, prev_names: dict | None, names: dict | None) -> list[tuple]:
    """(old key, new key) pairs for a record that only changed its item number: a key that went and a key that came
    in the same regime and schedule, with the same type and the same name hash, that hash on no other record going
    or coming there. Canada's list gives no entry id, so a renumbered schedule would otherwise read as removals and
    additions. Without name hashes from the reading before (a first reading under this code), nothing is paired."""
    if not prev_names or not names:
        return []
    gone, came = sorted(set(prev_index) - set(index)), sorted(set(index) - set(prev_index))

    def groups(keys, idx, hashes):
        out: dict = {}
        for k in keys:
            h = hashes.get(k)
            if h:
                out.setdefault((k.rsplit("|", 1)[0], idx[k][0], h), []).append(k)
        return {g: v[0] for g, v in out.items() if len(v) == 1}
    a, b = groups(gone, prev_index, prev_names), groups(came, index, names)
    return sorted((a[g], b[g]) for g in set(a) & set(b))


def apply_renumbering(prev_index: dict, pairs: list[tuple]) -> dict:
    """The earlier reading with each renumbered record moved to its new key, so the two compare as one entry."""
    out = dict(prev_index)
    for old, new in pairs:
        out[new] = out.pop(old)
    return out


def check_size(list_id: str, index: dict, prev_index: dict | None) -> None:
    if len(index) < LISTS[list_id]["min_entries"]:
        raise ValueError(f"{list_id}: only {len(index)} entries parsed; the download looks cut short")
    if prev_index and len(index) < len(prev_index) * SHRINK_LIMIT:
        raise ValueError(f"{list_id}: {len(index)} entries against {len(prev_index)} before; not reported as delistings")


def _tally(index: dict, ids) -> tuple[dict, dict]:
    by_type, by_group = Counter(), Counter()
    for i in ids:
        kind, groups = index[i][0], index[i][1]
        by_type[kind] += 1
        for g in groups or ["none stated"]:
            by_group[g] += 1
    return dict(sorted(by_type.items())), dict(by_group.most_common())


def status(list_id: str, index: dict, checked_at: str, baseline_set_at: str, source_generated: str | None = None,
           last_change_at: str | None = None) -> dict:
    by_type, _ = _tally(index, index)
    out = {"id": list_id, "name": LISTS[list_id]["name"], "publisher": LISTS[list_id]["publisher"],
           "url": LISTS[list_id]["url"], "total": len(index), "by_type": by_type, "checked_at": checked_at,
           "baseline_set_at": baseline_set_at, "source_generated": source_generated, "last_change_at": last_change_at}
    unknown = unknown_programs(list_id, index)
    if unknown:
        out["unknown_programs"] = unknown
    return out


VESSEL_FIELDS = ("name", "imo", "mmsi", "flag", "vessel_type")

# The form of the vessel details kept in each list's index (`vessel_format` in the state). A reading kept in an
# older form is not compared field by field with a new one, so a change of form is never reported as ships
# renamed. 2: UK ship names taken out of FCDO's "IMO n (NAME)" form (14 Nov 2026).
VESSEL_FORMAT = {"uk-sanctions": 2}


def rekeyed_vessels(prev_index: dict, index: dict, added: list, removed: list) -> list[tuple[str, str]]:
    """(old id, new id) pairs: a vessel that went and a vessel that came on the same list with the same IMO
    number, where that number is on no other vessel going or coming. FCDO revokes and remakes a specification
    under a new id: on 2 Oct 2026 RUS3739 and RUS3747 became RUS3752 and RUS3751, and the ships never left
    the list. A pair is one entry still listed, compared like an id on both readings."""
    def by_imo(idx, ids):
        groups: dict = {}
        for i in ids:
            e = idx[i]
            if e[0] == "vessel" and len(e) > 2 and e[2].get("imo"):
                groups.setdefault(e[2]["imo"], []).append(i)
        return {k: v[0] for k, v in groups.items() if len(v) == 1}
    gone, came = by_imo(prev_index, removed), by_imo(index, added)
    return sorted((gone[k], came[k]) for k in set(gone) & set(came))


def edits(prev_index: dict, index: dict, pairs=(), compare_vessels: bool = True, compare_names: bool = True) -> dict:
    """Entries on both readings whose type, programs or (people and organizations) name changed, and vessels
    whose public details changed.

    Counts: how many entries changed, and which programs were gained and lost across them. Named: each person or
    organization that changed (`named_changed`, with the programs it gained and lost and, when renamed, its name
    before), and each vessel, before and after for each field that moved. `pairs` are (old id, new id) for one entry
    under a new id, compared as one. An index written before vessel details or names were kept, or kept in an older
    form (`compare_vessels`, `compare_names` False), gives no such comparison."""
    changed, gained, lost, retyped, vessels, named_changed = [], Counter(), Counter(), Counter(), [], []
    for old_id, new_id in [(i, i) for i in sorted(set(index) & set(prev_index))] + list(pairs):
        old, new = prev_index[old_id], index[new_id]
        before, after = nm.entry(prev_index, old_id), nm.entry(index, new_id)
        renamed = bool(compare_names and before and after and before["name"] != after["name"])
        if old[0] != new[0] or sorted(old[1]) != sorted(new[1]) or renamed:
            changed.append(new_id)
            gained.update(set(new[1]) - set(old[1]))
            lost.update(set(old[1]) - set(new[1]))
            if old[0] != new[0]:
                retyped[f"{old[0]} to {new[0]}"] += 1
            if after:
                rec = {**after, "gained": sorted(set(new[1]) - set(old[1])), "lost": sorted(set(old[1]) - set(new[1]))}
                if renamed:
                    rec["name_before"] = before["name"]
                if old[0] != new[0]:
                    rec["type_before"] = old[0]
                named_changed.append(rec)
        if compare_vessels and new[0] == "vessel" and len(old) > 2 and len(new) > 2:
            moved = {f: [old[2].get(f), new[2].get(f)] for f in VESSEL_FIELDS if old[2].get(f) != new[2].get(f)}
            if moved:
                vessels.append({"list_id": new_id, "name": new[2].get("name"), "imo": new[2].get("imo"),
                                "changed": moved, "programs": new[1]})
    by_type = Counter(index[i][0] for i in changed)
    return {"changed": len(changed), "changed_by_type": dict(sorted(by_type.items())),
            "programs_gained": dict(gained.most_common()), "programs_lost": dict(lost.most_common()),
            "retyped": dict(retyped), "vessels_changed": sorted(vessels, key=lambda v: v["name"] or ""),
            "named_changed": sorted(named_changed, key=nm.sort_key),
            "renamed": sum(1 for r in named_changed if "name_before" in r)}


SPLIT_KEYS = ("added", "removed", "changed", "added_by_type", "added_by_program", "removed_by_type",
              "removed_by_program", "changed_by_type", "programs_gained", "programs_lost", "retyped")


def _fr_split(out: dict, prev_index: dict, index: dict, detected_at: str, prior_checked_at: str | None,
              compare_vessels: bool, added_history: list | None, compare_names: bool = True) -> dict:
    """France's register restates EU and UN measures that Headwind reads on those lists, beside France's own
    national freezes (Tom, 15 Nov 2026: count the national ones apart). `national` is the change among entries
    that carry a national legal basis on either reading, scored by the observed-batch rule; `restated` is the
    rest, counted only: never scored and placing no country, so an EU package is not counted twice."""
    nat = {i for idx in (prev_index, index) for i, e in idx.items() if is_fr_national(e)}
    sub = delta("france-gels", {k: v for k, v in prev_index.items() if k in nat}, {k: v for k, v in index.items() if k in nat},
                detected_at, prior_checked_at, compare_vessels, None, added_history, split=False,
                compare_names=compare_names) or {}
    out["national"] = {k: sub.get(k, {} if k not in ("added", "removed", "changed") else 0) for k in SPLIT_KEYS}
    out["restated"] = {k: out[k] - out["national"][k] for k in ("added", "removed", "changed")}
    out["batches"] = sub.get("batches") or []
    out["anomaly"] = bool(sub.get("anomaly"))
    return out


def delta(list_id: str, prev_index: dict, index: dict, detected_at: str, prior_checked_at: str | None,
          compare_vessels: bool = True, dates: dict | None = None, added_history: list | None = None,
          split: bool = True, compare_names: bool = True) -> dict | None:
    """The difference between two readings of one list, or None when nothing changed.

    Additions and removals are ids that appear or go; a change is an id on both readings whose type, programs or
    name moved (or, for a vessel, its name, IMO, MMSI, flag or type). A vessel that went and came back under a new
    id with the same IMO number is counted once, as re-keyed, not as a removal and an addition. People and
    organizations added, removed and changed are named (`named_added`, `named_removed`, `named_changed`) on every
    list that carries names; a removal from an index kept before names were carried is counted only
    (`unnamed_removed`). France's register is split into its national freezes and its restatements (`_fr_split`)."""
    added = sorted(set(index) - set(prev_index))
    removed = sorted(set(prev_index) - set(index))
    pairs = rekeyed_vessels(prev_index, index, added, removed)
    added = sorted(set(added) - {n for _, n in pairs})
    removed = sorted(set(removed) - {o for o, _ in pairs})
    ed = edits(prev_index, index, pairs, compare_vessels, compare_names)
    if not added and not removed and not pairs and not ed["changed"] and not ed["vessels_changed"]:
        return None
    named_added = sorted(filter(None, (nm.entry(index, i, dates) for i in added)), key=nm.sort_key)
    named_removed = sorted(filter(None, (nm.entry(prev_index, i) for i in removed)), key=nm.sort_key)
    people_removed = sum(1 for i in removed if prev_index[i][0] != "vessel")
    rekeyed = sorted(({**v, "old_id": o} for o, n in pairs for v in _vessels(index, [n])),
                     key=lambda v: (v["name"] or "", v["imo"] or ""))
    batch = batches.measure(added, dates, added_history, detected_at)
    a_type, a_group = _tally(index, added)
    r_type, r_group = _tally(prev_index, removed)
    stamp = detected_at.replace("-", "").replace(":", "")[:13]
    out = {
        "id": f"{list_id}:{stamp}", "list": list_id, "list_name": LISTS[list_id]["name"],
        "publisher": LISTS[list_id]["publisher"], "url": LISTS[list_id]["url"],
        "detected_at": detected_at, "prior_checked_at": prior_checked_at,
        "added": len(added), "removed": len(removed), "total": len(index),
        "added_by_type": a_type, "added_by_program": a_group,
        "removed_by_type": r_type, "removed_by_program": r_group,
        "vessels_added": _vessels(index, added), "vessels_removed": _vessels(prev_index, removed),
        "rekeyed": len(pairs), "vessels_rekeyed": rekeyed,
        "batches": batch, "anomaly": any(b["anomaly"] for b in batch),
        **ed,
        "countries": countries_for(list(a_group) + list(r_group) + list(ed["programs_gained"])
                                   + list(ed["programs_lost"]), list_id),
    }
    if list_id in NAMED_LISTS:
        out.update({"named_added": named_added, "named_removed": named_removed,
                    "unnamed_removed": people_removed - len(named_removed),
                    "us_person_data": nm.person_data(named_added, named_removed, ed["named_changed"])})
    else:
        out.update({"named_changed": [], "renamed": 0, "us_person_data": "none"})
    if list_id == "france-gels" and split:
        return _fr_split(out, prev_index, index, detected_at, prior_checked_at, compare_vessels, added_history,
                         compare_names)
    return out


# The lists whose people and organizations are named. The UN's terms bar redistribution of its content.
NAMED_LISTS = ("ofac-sdn", "eu-fsf", "uk-sanctions", "france-gels", "canada-sema")


# The lists that carry ships. The UN file has none; EU vessel measures sit in regulation annexes, not in its file.
# France's register names 39 ships (North Korea, UN measures restated; 6 Nov 2026), each with an IMO number;
# Canada's list 731 (all under its Russia regulations, 16 Nov 2026).
VESSEL_LISTS = ("ofac-sdn", "uk-sanctions", "france-gels", "canada-sema")


def vessel_crosslist(indexes: dict[str, dict], stale: tuple = ()) -> tuple[dict, list[dict]]:
    """Ships by IMO number across the lists that carry them: (summary, one record per IMO number).

    A record gives, for each list the ship is on, the entry ids and the name and flag that list gives (the
    two lists often spell a name differently, and one ship can hold more than one entry on a list). Ships
    with no IMO number cannot be matched and are only counted. `stale` names lists whose index is the one
    kept from an earlier run because this run could not read them."""
    by_imo: dict[str, dict] = {}
    no_imo: Counter = Counter()
    for list_id in VESSEL_LISTS:
        for i, e in (indexes.get(list_id) or {}).items():
            if e[0] != "vessel":
                continue
            det = e[2] if len(e) > 2 else {}
            if not det.get("imo"):
                no_imo[list_id] += 1
                continue
            on = by_imo.setdefault(det["imo"], {"imo": det["imo"], "on": {}})["on"]
            rec = on.setdefault(list_id, {"ids": [], "name": det.get("name"), "flag": det.get("flag")})
            rec["ids"].append(i)
    combos: Counter = Counter("+".join(sorted(r["on"])) for r in by_imo.values())
    # on_both keeps its meaning from before France was added (Wake reads it): on the OFAC and UK lists, whatever else.
    summary = {"lists": list(VESSEL_LISTS), "imo_numbers": len(by_imo),
               "on_both": sum(1 for r in by_imo.values() if {"ofac-sdn", "uk-sanctions"} <= set(r["on"])),
               "on_two_or_more": sum(1 for r in by_imo.values() if len(r["on"]) > 1),
               "combos": dict(sorted(combos.items())),
               "only": {l: combos.get(l, 0) for l in VESSEL_LISTS},
               "without_imo": {l: no_imo.get(l, 0) for l in VESSEL_LISTS},
               "read": {l: bool(indexes.get(l)) for l in VESSEL_LISTS}, "from_earlier_run": sorted(stale)}
    table = sorted(by_imo.values(), key=lambda r: r["imo"])
    for r in table:
        for rec in r["on"].values():
            rec["ids"].sort()
    return summary, table


def mark_also_on(d: dict, table: list[dict]) -> dict:
    """Give each ship named in a change the other lists that carry its IMO number (after this run's reading)."""
    on = {r["imo"]: set(r["on"]) for r in table}
    for key in ("vessels_added", "vessels_removed", "vessels_rekeyed", "vessels_changed"):
        for v in d.get(key) or []:
            v["also_on"] = sorted(on.get(v.get("imo"), set()) - {d["list"]}) if v.get("imo") else []
    return d


def roll(previous: list[dict], new: list[dict], now_iso: str) -> list[dict]:
    """Keep deltas for KEEP_DAYS so a change does not vanish on the next run."""
    cutoff = (datetime.fromisoformat(now_iso.replace("Z", "+00:00")) - timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    seen, out = set(), []
    for d in new + (previous or []):
        if d.get("id") in seen or d.get("detected_at", "") < cutoff:
            continue
        seen.add(d["id"])
        out.append(d)
    return sorted(out, key=lambda d: d["detected_at"], reverse=True)
