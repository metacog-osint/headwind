"""The FollowTheMoney entity export (headwind/ftm.py) and its check against FtM's published model.

The stdlib tests run everywhere. `FollowTheMoneyLibrary` runs the same export through the followthemoney package
itself (its model, `Schema.validate` and an uncleaned `get_proxy`), when it is installed: the ci workflow installs
the pinned version; elsewhere the class is skipped."""
from __future__ import annotations

import copy
import gzip
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from headwind import ftm, sanctions, screening  # noqa: E402

MODEL = ftm.load_model()
CHECKED = "2026-11-27T05:45:11Z"


def _state():
    """A run state in the shapes the sanctions and screening lanes keep (tools/headwind.py, screening.compare)."""
    s = {
        "ofac-sdn": {"checked_at": CHECKED, "index": {
            "10001": ["entity", ["SDNT"], {"name": "INVERSIONES MACARNIC PATINO Y CIA S.C.S.", "countries": ["Colombia"]}],
            "10007": ["individual", ["SDGT"], {"name": "AHMAD, Najmuddin Faraj", "countries": ["Norway", "Region: Gaza"]}],
            "15036": ["vessel", ["IRAN-EO13846"], {"name": "ARTAVIL", "imo": "9187629", "mmsi": "572469210",
                                                   "flag": "Iran", "vessel_type": "Crude/Oil Products Tanker"}],
            "15432": ["aircraft", ["SDGT"], {"name": "EP-GOL", "countries": []}]},
            "vessel_dates": {"15036": "2019-09-04"}},
        "un-consolidated": {"checked_at": CHECKED, "index": {"6907993": ["individual", ["DRC"]]}},
        "eu-fsf": {"checked_at": CHECKED, "index": {
            "13": ["individual", ["IRQ"], {"name": "Saddam Hussein Al-Tikriti", "countries": ["IQ"], "aliases": "ed24"}]}},
        "uk-sanctions": {"checked_at": CHECKED, "index": {
            "AFG0001": ["entity", ["Afghanistan"], {"name": "ROSHAN MONEY EXCHANGE", "countries": ["Afghanistan"]}],
            "RUS0001": ["individual", ["Russia"], {"name": "SOMEONE, Named", "countries": ["Russia"]}],
            "DPR0075": ["vessel", ["Democratic People's Republic of Korea"],
                        {"name": "Petrel 8", "imo": "9562233", "mmsi": None, "flag": "Comoros",
                         "vessel_type": "Bulk Carrier"}]}},
        "france-gels": {"checked_at": CHECKED, "index": {
            "4240": ["individual", ["UE Ukraine"], {"name": "SHILKIN, Grigory Vladimirovich", "countries": []}]}},
        "canada-sema": {"checked_at": CHECKED, "index": {
            "Belarus|1, Part 1|1": ["individual", ["Belarus"], {"name": "Atabekov, Khazalbek", "countries": []}],
            "Russia|1.1|1": ["vessel", ["Russia"], {"name": "Balitiyskiy III", "imo": "7612448", "mmsi": None,
                                                    "flag": None, "vessel_type": "General Cargo/Multi Purpose"}]}},
        "australia-dfat": {"checked_at": CHECKED, "index": {
            "2": ["individual", ["1988 (Taliban)"]],
            "1280": ["individual", ["1373 (2001)"], {"name": "Manssor Arbabsiar", "countries": ["Iran", "United States"]}]}},
        "japan-mof": {"checked_at": CHECKED, "index": {
            "001-000001": ["individual", ["FRY (Milosevic and associates)"], {"name": "Milosevic Slobodan", "countries": []}],
            "ship-001-000001": ["vessel", ["Designated vessels (services ban)"],
                                {"name": None, "imo": "9179842", "mmsi": None, "flag": None, "vessel_type": None}]}},
    }
    c = {"checked_at": "2026-11-27T05:46:26Z", "baseline_set_at": "2026-11-13T16:43:27Z", "name_format": 1, "lists": {
        "EL": {"name": "Entity List", "publisher": "US Bureau of Industry and Security",
               "url": "https://www.trade.gov/consolidated-screening-list", "index": {
                   "b6e959b5": ["not stated", [], ["AF", "PK"], "f7c4d78aae8d", "Abdul Satar Ghoura"],
                   "c0ffee": ["not stated", [], [], None, None]}},
        "PLC": {"name": "Non-SDN Palestinian Legislative Council List", "publisher": "US Department of the Treasury",
                "url": "https://www.trade.gov/consolidated-screening-list", "index": {
                    "9641": ["individual", ["NS-PLC"], ["PS"], "351726a4b135", "Jamileh Abdullah AL-SHANTI"]}},
        "DTC": {"name": "ITAR Debarred", "publisher": "US State Department",
                "url": "https://www.trade.gov/consolidated-screening-list", "index": {
                    "1d0250ee": ["not stated", [], [], "133af806e4f8", "A & C International Trade, Inc."]}},
        "DPL": {"name": "Denied Persons List", "publisher": "US Bureau of Industry and Security",
                "url": "https://www.bis.gov/licensing/end-user-guidance/denied-persons-list-dpl", "index": {
                    "2815dd93": ["not stated", [], ["DK"], "5d1f0e0c9c1a", "SEMICONDUCTOR SYSTEMS INTL., INC. (SSI)"]},
                "entry_dates": {"2815dd93": ["1992-03-20", "2000-10-04"]}}}}
    return s, c


class Export(unittest.TestCase):
    def setUp(self):
        self.stream, self.about = ftm.entities(*_state(), MODEL)
        self.by_id = {e["id"]: e for e in self.stream}

    def test_valid_against_the_ftm_model(self):
        ftm.validate(self.stream, MODEL)

    def test_party_and_sanction_per_named_entry(self):
        e = self.by_id["hw-ofac-sdn-15036"]
        self.assertEqual(e["schema"], "Vessel")
        self.assertEqual(e["properties"], {"name": ["ARTAVIL"], "imoNumber": ["IMO9187629"], "mmsi": ["572469210"],
                                           "flag": ["ir"], "type": ["Crude/Oil Products Tanker"],
                                           "topics": ["sanction"]})
        s = self.by_id["hw-ofac-sdn-15036-sanction"]["properties"]
        self.assertEqual(s["entity"], ["hw-ofac-sdn-15036"])
        self.assertEqual(s["authorityId"], ["15036"])
        self.assertEqual(s["recordId"], ["15036"])
        self.assertEqual(s["country"], ["us"])
        self.assertEqual(s["listingDate"], ["2019-09-04"])
        self.assertEqual(s["retrievedAt"], ["2026-11-27T05:45:11"])
        self.assertEqual(s["authority"], ["US Treasury (OFAC)"])
        self.assertEqual(self.by_id["hw-ofac-sdn-15432"]["schema"], "Airplane")
        self.assertEqual(self.by_id["hw-ofac-sdn-10007"]["schema"], "Person")
        self.assertEqual(self.by_id["hw-ofac-sdn-10001"]["schema"], "Organization")
        self.assertEqual(self.by_id["hw-csl-el-b6e959b5"]["schema"], "LegalEntity")

    def test_countries_are_ftm_codes_and_regions_are_counted_not_guessed(self):
        self.assertEqual(self.by_id["hw-ofac-sdn-10007"]["properties"]["country"], ["no"])
        self.assertEqual(self.by_id["hw-australia-dfat-1280"]["properties"]["country"], ["ir", "us"])
        self.assertEqual(self.by_id["hw-eu-fsf-13"]["properties"]["country"], ["iq"])
        self.assertEqual(self.by_id["hw-uk-sanctions-DPR0075"]["properties"]["flag"], ["km"])
        self.assertIn({"list": "ofac-sdn", "value": "Region: Gaza", "times": 1}, self.about["countries_not_placed"])

    def test_lists_left_out_by_their_terms(self):
        ids = set(self.by_id)
        self.assertFalse([i for i in ids if i.startswith(("hw-un-", "hw-france-"))])
        self.assertNotIn("hw-uk-sanctions-RUS0001", ids)          # OGL v3.0 does not cover personal data
        self.assertIn("hw-uk-sanctions-AFG0001", ids)
        self.assertIn("hw-uk-sanctions-DPR0075", ids)
        self.assertNotIn("hw-australia-dfat-2", ids)              # restates a UN listing: counted only, no name
        self.assertFalse([i for i in ids if "ship-001" in i])     # Japan's ship file gives no names
        why = {(x["list"], x["why"]): x["entries"] for x in self.about["not_written"]}
        self.assertEqual(why[("uk-sanctions", "type not exported")], 1)
        self.assertEqual(why[("australia-dfat", "no name in the state")], 1)
        self.assertEqual(why[("japan-mof", "no name in the state")], 1)
        self.assertEqual(why[("csl-el", "no name in the state")], 1)
        self.assertEqual(set(self.about["left_out"]), {"un-consolidated", "france-gels", "uk-sanctions individuals"})

    def test_every_list_is_exported_or_left_out_with_a_reason(self):
        for list_id in sanctions.LISTS:
            self.assertTrue(list_id in ftm.LISTS or list_id in ftm.LEFT_OUT, list_id)
        self.assertFalse(set(ftm.LISTS) & {"un-consolidated", "france-gels"})
        self.assertTrue(set(ftm.LISTS) <= set(sanctions.NAMED_LISTS))
        for spec in ftm.LISTS.values():
            self.assertTrue(spec["statement"])

    def test_canada_key_is_a_record_id_not_an_authority_id(self):
        eid = ftm.entity_id("canada-sema", "Belarus|1, Part 1|1")
        self.assertRegex(eid, ftm.ENTITY_ID)
        s = self.by_id[eid + "-sanction"]["properties"]
        self.assertEqual(s["recordId"], ["Belarus|1, Part 1|1"])
        self.assertNotIn("authorityId", s)
        self.assertNotIn("authorityId", self.by_id["hw-csl-plc-9641-sanction"]["properties"])

    def test_screening_topics_and_programs(self):
        self.assertEqual(self.by_id["hw-csl-el-b6e959b5"]["properties"]["topics"], ["export.control"])
        self.assertEqual(self.by_id["hw-csl-dtc-1d0250ee"]["properties"]["topics"], ["debarment"])
        self.assertEqual(self.by_id["hw-csl-plc-9641"]["properties"]["topics"], ["sanction"])
        el = self.by_id["hw-csl-el-b6e959b5-sanction"]["properties"]
        self.assertEqual(el["program"], ["Entity List"])         # no program given: the list is the measure
        self.assertEqual(el["country"], ["us"])
        self.assertEqual(self.by_id["hw-csl-plc-9641-sanction"]["properties"]["program"], ["NS-PLC"])

    def test_imo_numbers_in_ftm_form_and_checked(self):
        self.assertEqual(ftm.imo_number("9187629"), "IMO9187629")
        self.assertEqual(ftm.imo_number("IMO 9562233"), "IMO9562233")
        self.assertIsNone(ftm.imo_number("9187628"))               # check digit fails both schemes
        self.assertIsNone(ftm.imo_number("0000000"))
        self.assertIsNone(ftm.imo_number(None))
        s, c = _state()
        s["uk-sanctions"]["index"]["DPR0075"][2]["imo"] = "9562234"
        stream, about = ftm.entities(s, c, MODEL)
        ship = next(e for e in stream if e["id"] == "hw-uk-sanctions-DPR0075")
        self.assertNotIn("imoNumber", ship["properties"])
        self.assertEqual(about["imo_numbers_not_valid"]["by_list"], {"uk-sanctions": 1})

    def test_ids_follow_ftm_rule_and_never_meet(self):
        for raw in ("Belarus|1, Part 1|1", "Belarus-1--Part-1-1", "a_b", "x.", "-y", "|"):
            self.assertRegex(ftm.entity_id("l", raw), ftm.ENTITY_ID)
        self.assertNotEqual(ftm.entity_id("l", "a|b"), ftm.entity_id("l", "a b"))
        self.assertEqual(ftm.entity_id("ofac-sdn", "10001"), "hw-ofac-sdn-10001")

    def test_written_file_is_one_entity_a_line_and_the_same_bytes_each_time(self):
        with tempfile.TemporaryDirectory() as d:
            a, b = Path(d) / "a.ftm.gz", Path(d) / "b.ftm.gz"
            ftm.write(self.stream, a)
            ftm.write(copy.deepcopy(self.stream), b)
            self.assertEqual(a.read_bytes(), b.read_bytes())
            self.assertEqual(ftm.read(a), self.stream)
            with gzip.open(a, "rt", encoding="utf-8") as fh:
                lines = fh.read().splitlines()
            self.assertEqual(len(lines), len(self.stream))
            self.assertTrue(all(line.startswith("{") and "\n" not in line for line in lines))

    def test_main_writes_export_and_about(self):
        s, c = _state()
        with tempfile.TemporaryDirectory() as d:
            st = Path(d) / "state"
            st.mkdir()
            (st / "sanctions_index.json").write_text(json.dumps(s), encoding="utf-8")
            (st / "screening_index.json").write_text(json.dumps(c), encoding="utf-8")
            out, about = Path(d) / ftm.OUT_NAME, Path(d) / ftm.ABOUT_NAME
            self.assertEqual(ftm.main(["--state", str(st), "--out", str(out), "--about", str(about)]), 0)
            self.assertEqual(len(ftm.read(out)), len(self.stream))
            a = json.loads(about.read_text(encoding="utf-8"))
            self.assertEqual(a["followthemoney"]["model_version"], "4.11.3")
            self.assertEqual(a["entities"], len(self.stream))


CREDIT_FIELDS = ("publisher", "title", "source", "licence", "licence_url", "statement", "changes")


class Attribution(unittest.TestCase):
    """Every exported list is credited, from one table, in about.json, the release notes and the site."""

    def setUp(self):
        self.stream, self.about = ftm.entities(*_state(), MODEL)

    def test_every_exported_list_has_a_licence_link_and_a_statement_of_changes(self):
        self.assertEqual(len(self.about["lists"]), len(ftm.LISTS) + 4)       # six lists and four CSL lists
        for item in self.about["lists"]:
            a = item["attribution"]
            self.assertEqual(a["list"], item["list"])
            for field in CREDIT_FIELDS:
                self.assertTrue(a.get(field), f"{item['list']}: no {field}")
            self.assertRegex(a["licence_url"], r"^https?://", item["list"])
            self.assertTrue(all(s.startswith(("https://", "http://")) for s in a["source"]), item["list"])
            self.assertTrue(a["changes"].startswith("Modified by Headwind"), item["list"])
            self.assertGreater(len(a["changes"]), len(ftm.CHANGES_ALL) + 20, item["list"])  # and its own changes
            self.assertEqual(item["terms"], a["statement"])

    def test_the_table_covers_every_list(self):
        for list_id, spec in ftm.LISTS.items():
            for field in CREDIT_FIELDS:
                self.assertTrue(spec.get(field), f"{list_id}: no {field}")
        for field in ("publisher", "source", "licence", "licence_url", "statement", "changes"):
            self.assertTrue(ftm.SCREENING.get(field), field)

    def test_cc_by_and_ogl_ask_for_their_licence_link_and_cc_by_for_the_changes(self):
        au = ftm.attribution("australia-dfat")
        self.assertEqual(au["licence_url"], "https://creativecommons.org/licenses/by/4.0/")
        self.assertIn("Department of Foreign Affairs and Trade website – www.dfat.gov.au", au["statement"])
        self.assertIn(ftm.CC_BY_4_URL, au["statement"])
        self.assertIn("modified", au["statement"])
        self.assertIn("left out", au["changes"])
        uk = ftm.attribution("uk-sanctions")
        self.assertEqual(uk["licence_url"], "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/")
        self.assertIn("Contains public sector information licensed under the Open Government Licence v3.0",
                      uk["statement"])
        self.assertIn("加工して作成", ftm.attribution("japan-mof")["statement"])

    def test_left_out_counts_per_list(self):
        by = {x["list"]: x["attribution"]["left_out"] for x in self.about["lists"]}
        self.assertEqual(by["uk-sanctions"], {"type not exported": 1})
        self.assertEqual(by["australia-dfat"], {"no name in the state": 1})
        self.assertEqual(by["ofac-sdn"], {})

    def test_release_notes_carry_every_credit(self):
        notes = ftm.release_notes(self.about)
        for item in self.about["lists"]:
            a = item["attribution"]
            self.assertIn(f"[{a['licence']}]({a['licence_url']})", notes)
            self.assertIn(a["title"], notes)
            self.assertIn(a["statement"], notes)
            self.assertIn(a["changes"][len(ftm.CHANGES_ALL):].strip(), notes)
        self.assertIn(ftm.CHANGES_ALL, notes)
        self.assertIn("SHA256SUMS", notes)

    def test_site_sources_from_the_same_table(self):
        _, c = _state()
        page = ftm.sources_html(c["lists"])
        statuses = [{"id": k, **v} for k, v in c["lists"].items()]
        self.assertEqual(page, ftm.sources_html(statuses))
        for a in ftm.all_attributions(c["lists"]):
            self.assertIn(f'href="{a["licence_url"]}"', page)
        self.assertEqual(page.count("<li>"), len(ftm.LISTS) + 4)

    def test_main_writes_notes(self):
        s, c = _state()
        with tempfile.TemporaryDirectory() as d:
            st = Path(d) / "state"
            st.mkdir()
            (st / "sanctions_index.json").write_text(json.dumps(s), encoding="utf-8")
            (st / "screening_index.json").write_text(json.dumps(c), encoding="utf-8")
            notes = Path(d) / "notes.md"
            ftm.main(["--state", str(st), "--out", str(Path(d) / "x.ftm.gz"), "--about", str(Path(d) / "a.json"),
                      "--notes", str(notes)])
            self.assertIn(ftm.CC_BY_4_URL, notes.read_text(encoding="utf-8"))


class EndedListings(unittest.TestCase):
    """Denied Persons List orders whose end date has passed stay in the CSL file; the export marks them ended.
    Fixture: three real DPL entries from the CSL of 27 Nov 2026 (ended 2000, ends 2027, no end date)."""
    ENDED, LATER, OPEN = ("2815dd9334befab373278b903a412b353b292cc8d09cf8d06af746db",
                          "e8e62a20de26fe327462978a684d3d1c7868333511985d62d61c2539",
                          "2a3f1ab0ea11c63a96bf46133e98e1464f46880717a20affef268393")

    def setUp(self):
        body = (Path(__file__).resolve().parent / "fixtures" / "trade_gov_csl_dpl.json").read_bytes()
        self.lists = screening.parse(body)
        screening.MIN_ENTRIES, self._min = 0, screening.MIN_ENTRIES
        _, _, self.state = screening.compare(self.lists, {}, "2026-11-27T07:40:00Z")

    def tearDown(self):
        screening.MIN_ENTRIES = self._min

    def test_the_state_keeps_start_and_end_dates_beside_the_index(self):
        dpl = self.state["lists"]["DPL"]
        self.assertEqual(dpl["entry_dates"][self.ENDED], ["1992-03-20", "2000-10-04"])
        self.assertEqual(dpl["entry_dates"][self.LATER], ["2002-01-24", "2027-01-24"])
        self.assertEqual(dpl["entry_dates"][self.OPEN], ["1984-12-14", None])
        self.assertEqual(len(dpl["index"][self.ENDED]), 5)                   # the index keeps its form

    def test_an_older_state_without_dates_compares_as_before(self):
        old = copy.deepcopy(self.state)
        for lst in old["lists"].values():
            lst.pop("entry_dates")
        deltas, _, new = screening.compare(screening.parse(
            (Path(__file__).resolve().parent / "fixtures" / "trade_gov_csl_dpl.json").read_bytes()), old,
            "2026-11-27T13:40:00Z")
        self.assertEqual(deltas, [])
        self.assertIn(self.ENDED, new["lists"]["DPL"]["entry_dates"])

    def test_ended_orders_carry_their_end_date_and_no_topic(self):
        stream, about = ftm.entities({}, self.state, MODEL)
        ftm.validate(stream, MODEL)
        by_id = {e["id"]: e for e in stream}
        ended = by_id[f"hw-csl-dpl-{self.ENDED}"]["properties"]
        self.assertNotIn("topics", ended)
        s = by_id[f"hw-csl-dpl-{self.ENDED}-sanction"]["properties"]
        self.assertEqual((s["startDate"], s["endDate"]), (["1992-03-20"], ["2000-10-04"]))
        self.assertEqual(by_id[f"hw-csl-dpl-{self.LATER}"]["properties"]["topics"], ["export.control"])
        self.assertEqual(by_id[f"hw-csl-dpl-{self.LATER}-sanction"]["properties"]["endDate"], ["2027-01-24"])
        self.assertEqual(by_id[f"hw-csl-dpl-{self.OPEN}"]["properties"]["topics"], ["export.control"])
        self.assertNotIn("endDate", by_id[f"hw-csl-dpl-{self.OPEN}-sanction"]["properties"])
        self.assertEqual(len(stream), 6)                                     # none left out
        dpl = next(x for x in about["lists"] if x["list"] == "csl-dpl")
        self.assertEqual((dpl["ended"], dpl["with_end_date"], dpl["with_start_date"]), (1, 2, 3))
        self.assertEqual(about["ended"]["entries"], 1)
        self.assertEqual(about["ended"]["by_list"], {"csl-dpl": 1})
        self.assertIn("Ended listings: 1 entry (csl-dpl 1)", ftm.release_notes(about))

    def test_has_ended_is_before_the_reading_day(self):
        self.assertTrue(ftm.has_ended("2026-11-26", "2026-11-27T07:40:00Z"))
        self.assertFalse(ftm.has_ended("2026-11-27", "2026-11-27T07:40:00Z"))   # in force on its last day
        self.assertFalse(ftm.has_ended(None, "2026-11-27T07:40:00Z"))
        self.assertFalse(ftm.has_ended("2026-11-26", None))


class Validator(unittest.TestCase):
    def setUp(self):
        self.stream, _ = ftm.entities(*_state(), MODEL)

    def broken(self, change):
        s = copy.deepcopy(self.stream)
        change(s)
        with self.assertRaises(ftm.InvalidEntity):
            ftm.validate(s, MODEL)

    def test_rejects_what_ftm_would_not_take(self):
        self.broken(lambda s: s[0]["properties"].update(colour=["red"]))                 # no such property
        self.broken(lambda s: s[0].update(schema="Thing"))                               # abstract
        self.broken(lambda s: s[0].update(schema="Ship"))                                # no such schema
        self.broken(lambda s: s[0]["properties"].update(country=["Colombia"]))           # a name, not a code
        self.broken(lambda s: s[0]["properties"].update(topics=["sanctioned"]))          # not an FtM topic
        self.broken(lambda s: s[0]["properties"].pop("name"))                            # required
        self.broken(lambda s: s[0]["properties"].update(name="one"))                     # not a list
        self.broken(lambda s: s[0]["properties"].update(name=[" padded"]))
        self.broken(lambda s: s[1]["properties"].update(entity=["hw-nowhere-1"]))        # dangling link
        self.broken(lambda s: s[1]["properties"].update(listingDate=["4 Sept 2019"]))
        self.broken(lambda s: s[1]["properties"].update(authorityId=["x" * 65]))         # identifier maxLength
        self.broken(lambda s: s.append(copy.deepcopy(s[0])))                             # id twice
        self.broken(lambda s: s[0].update(id="hw_bad_id"))                               # FtM id rule
        self.broken(lambda s: s[0].update(extra=1))
        self.broken(lambda s: next(e for e in s if e["schema"] == "Vessel")["properties"].update(imoNumber=["9187629"]))


class Model(unittest.TestCase):
    def test_extract_is_ftm_4_11_3_with_the_schemata_used(self):
        self.assertEqual(MODEL["version"], "4.11.3")
        self.assertIn("MIT License", MODEL["licence"])
        for name in ("Person", "Organization", "LegalEntity", "Vessel", "Airplane", "Sanction", "Thing", "Interval"):
            self.assertIn(name, MODEL["schemata"])
        self.assertTrue(MODEL["schemata"]["Thing"]["abstract"])
        self.assertEqual(MODEL["schemata"]["Sanction"]["required"], ["entity"])
        self.assertIn("eu", MODEL["types"]["country"]["values"])
        self.assertIn("export.control", MODEL["types"]["topic"]["values"])

    def test_extract_reproduces_from_the_tool(self):
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
        import ftm_model
        self.assertEqual(ftm_model.TAG, "v" + MODEL["version"])
        self.assertEqual(MODEL["source"], f"https://github.com/opensanctions/followthemoney/blob/{ftm_model.TAG}/"
                                          "js/src/defaultModel.json")


try:
    import followthemoney  # noqa: F401
    HAVE_FTM = True
except Exception:  # noqa: BLE001 - absent or not importable: the class is skipped
    HAVE_FTM = False


@unittest.skipUnless(HAVE_FTM, "followthemoney is not installed (the ci workflow installs it)")
class FollowTheMoneyLibrary(unittest.TestCase):
    def test_export_passes_followthemoney_itself(self):
        import followthemoney
        from followthemoney import model
        self.assertEqual(followthemoney.__version__, MODEL["version"])
        stream, _ = ftm.entities(*_state(), MODEL)
        for ent in stream:
            schema = model.get(ent["schema"])
            self.assertIsNotNone(schema, ent["schema"])
            self.assertFalse(schema.abstract, ent["schema"])
            for prop in ent["properties"]:
                self.assertIn(prop, schema.properties, f"{ent['schema']}:{prop}")
            schema.validate(ent)                                   # raises InvalidData on a bad value
            proxy = model.get_proxy(ent, cleaned=False)            # every value parsed and cleaned again
            self.assertEqual(proxy.id, ent["id"])
            for prop, values in ent["properties"].items():
                self.assertEqual(sorted(proxy.get(prop)), sorted(values), f"{ent['id']} {prop}")
            for prop in schema.required:
                self.assertTrue(proxy.get(prop), f"{ent['id']} lacks {prop}")


if __name__ == "__main__":
    unittest.main()
