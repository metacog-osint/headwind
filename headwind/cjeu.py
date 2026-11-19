"""The Court of Justice of the European Union: every judgment of the Court of Justice and the General Court in the
last 60 days, as the EU's Publications Office records them for EUR-Lex.

Source: the Publications Office's SPARQL endpoint on its CELLAR repository (keyless), the metadata behind EUR-Lex.
EUR-Lex's copyright notice (legal notice page, read 19 Nov 2026): "EUR-Lex metadata is dedicated to the public domain
in accordance with the Creative Commons CC0 1.0 Universal Public Domain Dedication deed", and the Commission's reuse
policy (Decision 2011/833/EU) lets "the legal documents published in EUR-Lex" be reused "for commercial or
non-commercial purposes". Headwind reads metadata only (no judgment text), one query a run. EUR-Lex's robots.txt
(19 Nov 2026) asks a crawl delay of 10 seconds and disallows its webservice (/smartapi) and document downloads; the
endpoint is on publications.europa.eu, and the links Headwind gives go to EUR-Lex's document pages, which robots.txt
allows. The EUR-Lex webservice (registration) and CURIA's own pages are not used.

What is kept, per judgment: CELEX number, ECLI, the date of the judgment, which court and formation gave it (the
Court's own heading, "Judgment of the Court (Grand Chamber) of ..."), the case numbers, the parties as the Court
names them, whether the Court's own subject words name restrictive measures, and the language the heading was read
in (English; French, the Court's working language, while the English version is not yet out; some judgments of the
General Court are never put into English). The subject words themselves, and any text, are not kept.

Measured 19 Nov 2026: a judgment delivered that morning is on the endpoint the same day (created 10:38 CET, the
English heading by 14:34); 60 days to 19 Nov held 221 judgments (110 of the Court of Justice, 111 of the General
Court), 3 of the Grand Chamber, 14 naming restrictive measures, 8 not yet in English.

What goes in the feed (the legal events strand's rule, doctrine/method.md: at a court that decides many cases, the
court's own selection, never a reading of importance or of subject): a Court of Justice judgment given by the Grand
Chamber or the full Court, the formations the Court keeps for its weightiest cases. Every judgment is on the page,
and a judgment whose own subject words name restrictive measures (sanctions) is marked there. Putting those in the
feed too would be a selection by subject, so it waits on Tom (FEED_RESTRICTIVE_MEASURES).
"""
from __future__ import annotations

import json
import re
import urllib.parse
from datetime import date, timedelta

from headwind import scotus, uksc

ENDPOINT = "https://publications.europa.eu/webapi/rdf/sparql"
LEGAL_NOTICE = "https://eur-lex.europa.eu/content/legal-notice/legal-notice.html"
CASE_LAW_PAGE = "https://eur-lex.europa.eu/collection/eu-law/eu-case-law.html"
EURLEX_DOC = "https://eur-lex.europa.eu/legal-content/{lang}/TXT/?uri=CELEX:{celex}"
DAYS = 60               # judgments kept and shown, from the judgment date
FEED_DAYS = 14          # judgments in the feed
# Restrictive-measures judgments in the feed as well: a selection by the Court's own subject words, which the
# strand's rule (never by subject) does not allow yet. Tom's call (asked 19 Nov 2026).
FEED_RESTRICTIVE_MEASURES = False

_CDM = "http://publications.europa.eu/ontology/cdm#"
_AUTH = "http://publications.europa.eu/resource/authority/"
COURTS = {"CJ": "Court of Justice", "GCEU": "General Court"}

QUERY = """PREFIX cdm: <%(cdm)s>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
SELECT ?celex ?ecli ?date ?court (SAMPLE(?en_h) AS ?en_heading) (SAMPLE(?en_p) AS ?en_parties)
 (GROUP_CONCAT(DISTINCT ?en_c; separator="|") AS ?en_cases) (SAMPLE(?en_i) AS ?en_subject)
 (SAMPLE(?fr_h) AS ?fr_heading) (SAMPLE(?fr_p) AS ?fr_parties)
 (GROUP_CONCAT(DISTINCT ?fr_c; separator="|") AS ?fr_cases) (SAMPLE(?fr_i) AS ?fr_subject) WHERE {
 ?work cdm:work_has_resource-type <%(auth)sresource-type/JUDG> ;
       cdm:resource_legal_id_celex ?celex ; cdm:work_date_document ?date ; cdm:case-law_ecli ?ecli ;
       cdm:work_created_by_agent ?court .
 FILTER NOT EXISTS { ?work cdm:do_not_index ?x }
 FILTER(?date >= "%(start)s"^^xsd:date)
 FILTER(?court IN (<%(auth)scorporate-body/CJ>, <%(auth)scorporate-body/GCEU>))
 OPTIONAL { ?e cdm:expression_belongs_to_work ?work ; cdm:expression_uses_language <%(auth)slanguage/ENG> .
   OPTIONAL { ?e cdm:expression_title_information_additional ?en_h }
   OPTIONAL { ?e cdm:expression_case-law_parties ?en_p }
   OPTIONAL { ?e cdm:expression_case-law_identifier_case ?en_c }
   OPTIONAL { ?e cdm:expression_case-law_indicator_decision ?en_i } }
 OPTIONAL { ?f cdm:expression_belongs_to_work ?work ; cdm:expression_uses_language <%(auth)slanguage/FRA> .
   OPTIONAL { ?f cdm:expression_title_information_additional ?fr_h }
   OPTIONAL { ?f cdm:expression_case-law_parties ?fr_p }
   OPTIONAL { ?f cdm:expression_case-law_identifier_case ?fr_c }
   OPTIONAL { ?f cdm:expression_case-law_indicator_decision ?fr_i } }
} GROUP BY ?celex ?ecli ?date ?court ORDER BY DESC(?date) ?celex"""


def window_start(today: date) -> str:
    return (today - timedelta(days=DAYS)).isoformat()


def query_url(today: date) -> str:
    q = QUERY % {"cdm": _CDM, "auth": _AUTH, "start": window_start(today)}
    return ENDPOINT + "?" + urllib.parse.urlencode({"query": q, "format": "application/sparql-results+json"})


_CELEX = re.compile(r"^6(?P<year>\d{4})(?P<type>CJ|TJ)(?P<number>\d{4})(?:_\d+)?$")
_CASE = re.compile(r"\b([CT]-\d+/\d{2}(?:\s?(?:P|RENV|PPU|REV|DEP|INT|OP|AJ|R)\b)*)")
_FORMATION = re.compile(r"\((?P<f>[^()]+)\)\s+(?:of|du)\s+\d")
_GRAND = re.compile(r"^(?:Grand Chamber|grande chambre|Full Court|assemblée plénière)$", re.IGNORECASE)
_RESTRICTIVE = re.compile(r"\bRestrictive measures\b|\bMesures restrictives\b", re.IGNORECASE)


def _value(b: dict, k: str) -> str:
    return " ".join(((b.get(k) or {}).get("value") or "").split())


def parse(body: bytes) -> list[dict]:
    """The judgments in one reply, newest first. A reply that is not SPARQL JSON, or a row whose CELEX number or
    court is not one Headwind knows, fails the lane (the query or the Office's model has changed)."""
    data = json.loads(body.decode("utf-8"))
    rows = data["results"]["bindings"]
    out: dict[str, dict] = {}
    for b in rows:
        celex, court = _value(b, "celex"), _value(b, "court").rsplit("/", 1)[-1]
        m = _CELEX.match(celex)
        if not m or court not in COURTS:
            raise ValueError(f"judgment {celex!r} of {court!r} not understood")
        lang = "en" if _value(b, "en_heading") or _value(b, "en_parties") else \
            "fr" if _value(b, "fr_heading") or _value(b, "fr_parties") else None
        heading = _value(b, f"{lang}_heading") if lang else ""
        cases = sorted({c for v in _value(b, f"{lang}_cases").split("|") for c in _CASE.findall(v)}) if lang else []
        if not cases:       # the CELEX number gives the first case: 62025CJ0029 is C-29/25
            cases = [f"{'C' if m.group('type') == 'CJ' else 'T'}-{int(m.group('number'))}/{m.group('year')[2:]}"]
        f = _FORMATION.search(heading) if "__[" not in heading else None    # "__[unreferenced:arret-c-iii-ext]__"
        formation = f.group("f").strip() if f else None
        subject = " ".join(_value(b, k) for k in ("en_subject", "fr_subject"))
        j = {"celex": celex, "ecli": _value(b, "ecli"), "date": _value(b, "date")[:10], "court": COURTS[court],
             "formation": formation, "cases": cases,
             "parties": _value(b, f"{lang}_parties") if lang else None, "language": lang,
             "grand": bool(formation and _GRAND.match(formation) and court == "CJ"),
             "restrictive_measures": bool(_RESTRICTIVE.search(subject)),
             "url": EURLEX_DOC.format(lang=(lang or "en").upper(), celex=celex)}
        j["selected"] = ("Grand Chamber" if j["grand"] and formation.lower() in ("grand chamber", "grande chambre")
                         else "full Court" if j["grand"] else
                         "restrictive measures" if j["restrictive_measures"] and FEED_RESTRICTIVE_MEASURES else None)
        j["us_person_data"] = us_person_data(j["parties"] or "")
        out[celex] = j
    return sorted(out.values(), key=lambda j: (j["date"], j["celex"]), reverse=True)


def merge(previous: list[dict], judgments: list[dict], now: str) -> list[dict]:
    """This run's judgments, each keeping the time Headwind first saw it. The query reads the whole window every
    run, so a judgment whose English heading arrives later is updated in place and one past the window drops out."""
    seen = {j["celex"]: j.get("first_seen") for j in previous or []}
    return [{**j, "first_seen": seen.get(j["celex"]) or now} for j in judgments]


# --- us_person_data -----------------------------------------------------------------------------------------
# The UK test (uksc.party_kind) with EU words: the EU's institutions, bodies and agencies and member states'
# governments are government; company forms used across the member states are organizations; anything else,
# including the initials the Court gives anonymised people ("O. A.", "LK", "EN"), reads as a person. A national
# authority named in its own language ("Maahanmuuttovirasto") also reads as a person, which errs towards
# "individuals".
_GOV_EU = re.compile(
    r"\b(?:European Union|European Commission|Commission|Council|European Parliament|Parliament|Court of Justice|"
    r"European Central Bank|European Investment Bank|Agency|Authority|Office|Ombudsman|Supervisor|Prosecutor|Board|Committee of the Regions|"
    r"Republic|Kingdom|Grand Duchy|Government|Ministry|Minister|State|Federal|Prefect|Préfet|Région|Land)\b",
    re.IGNORECASE)
_COMPANY_EU = re.compile(
    r"(?:\b(?:a\.\s?s|s\.\s?r\.\s?o|sp\. z o\.\s?o|S\.\s?p\.\s?A|S\.\s?r\.\s?l|S\.\s?L|S\.\s?A|SAS|SpA|Srl|GmbH|AG|KG|"
    r"BV|B\.V|NV|N\.V|Oy|Oyj|A/S|ApS|Kft|Zrt|d\.o\.o|d\.d|EOOD|OOD|AD|Lda|SE|plc|Ltd|Limited|LLC|Inc|Holding|"
    r"Shipping|Lines|Airlines|Register|Trading|Bank|Group|Insurance|poisťovňa)\b\.?)", re.IGNORECASE)
# Member states named alone, in English and French ("European Commission v Hungary", "Commission européenne contre
# Hongrie").
_MEMBER_STATE = re.compile(
    r"^(?:Austria|Autriche|Belgium|Belgique|Royaume de Belgique|Bulgaria|Bulgarie|Croatia|Croatie|Cyprus|Chypre|"
    r"Czechia|Tchéquie|Denmark|Danemark|Estonia|Estonie|Finland|Finlande|France|Germany|Allemagne|Greece|Grèce|"
    r"Hungary|Hongrie|Ireland|Irlande|Italy|Italie|Latvia|Lettonie|Lithuania|Lituanie|Luxembourg|Malta|Malte|"
    r"Netherlands|Pays-Bas|Poland|Pologne|Portugal|Romania|Roumanie|Slovakia|Slovaquie|Slovenia|Slovénie|Spain|"
    r"Espagne|Sweden|Suède)$", re.IGNORECASE)
_GOV_FR = re.compile(r"\b(?:Commission européenne|Conseil|Parlement européen|Union européenne|République|Royaume|"
                     r"État|Gouvernement|Ministère|Bundesrepublik)\b", re.IGNORECASE)
_OTHERS_EU = re.compile(r",?\s+and (?:another|others)\b|,?\s+et (?:autres|autre)\b", re.IGNORECASE)


def party_kind(side: str) -> str:
    """government, organization or person, from one side of the parties as the Court names them."""
    s = _OTHERS_EU.sub("", " ".join(side.split())).strip(" ,")
    if not s:
        return "person"
    if _COMPANY_EU.search(s):
        return "organization"
    if _MEMBER_STATE.match(s) or _GOV_EU.search(s) or _GOV_FR.search(s):
        return "government"
    return uksc.party_kind(s) if not scotus._ORG.search(s) else "organization"


def us_person_data(parties: str) -> str:
    """individuals when any party reads as a person (or the parties are not known yet), else organizations when a
    party is an organization that is not a government, else none."""
    # Each side is split on "and" too, so a person named beside a company ("Heinz Reinwald and HK Evolution LTD")
    # still reads as a person.
    sides = [p for s in re.split(r"\s+(?:v|contre)\.?\s+", _OTHERS_EU.sub("", " ".join(parties.split())))
             for p in re.split(r"\s+(?:and|et)\s+", s) if p.strip()]
    kinds = {party_kind(s) for s in sides} or {"person"}
    if "person" in kinds:
        return "individuals"
    return "organizations" if "organization" in kinds else "none"
