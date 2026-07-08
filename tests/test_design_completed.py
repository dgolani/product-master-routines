import os, sys, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from usecases import design_completed as dc


# A realistic OPD issue as returned by jira-rest (verified against OPD-3 / VM-527).
def make_issue(**overrides):
    fields = {
        "summary": "Search-Integrated Dynamic Edit Pages",
        "description": "New feature will allow merchandisers to create trend edit pages from search queries.",
        "customfield_12707": [{"displayName": "Dawid Tomczyk"}],   # Product Owner = designer
        "customfield_12714": [{                                     # Design (Figma)
            "displayName": "VM platform - Phase 4 - Automated edit pages",
            "url": "https://www.figma.com/file/ZMG8YzYW96PCzvwZSZHoMp?node-id=4185%3A18730",
        }],
        "customfield_13239": None,
        "statuscategorychangedate": "2026-07-07T09:24:00.363+0400",
        "issuelinks": [{                                            # linked product epic
            "type": {"name": "Relates"},
            "outwardIssue": {"key": "VM-527", "fields": {
                "summary": "[pod_vm] Search-Integrated Dynamic Edit Pages",
                "issuetype": {"name": "Epic"}}},
        }],
    }
    fields.update(overrides.pop("fields", {}))
    issue = {"key": overrides.pop("key", "OPD-3"), "fields": fields}
    issue.update(overrides)
    return issue


class TestBuildQuery(unittest.TestCase):
    def test_jql_targets_done_opd_with_recency_guard(self):
        q = dc.build_query()
        self.assertIn("project = OPD", q["jql"])
        self.assertIn("status = Done", q["jql"])
        self.assertIn("-7d", q["jql"])

    def test_fields_include_summary_material_and_links(self):
        fields = dc.build_query()["fields"]
        for fid in ("summary", "description", "customfield_12707", "customfield_12714",
                    "customfield_13239", "statuscategorychangedate", "issuelinks"):
            self.assertIn(fid, fields)


class TestExtractTicket(unittest.TestCase):
    def test_basic_fields(self):
        t = dc.extract_ticket(make_issue())
        self.assertEqual(t["key"], "OPD-3")
        self.assertEqual(t["summary"], "Search-Integrated Dynamic Edit Pages")
        self.assertEqual(t["designer"], "Dawid Tomczyk")
        self.assertIn("trend edit pages", t["description"])

    def test_completed_on_falls_back_to_done_timestamp(self):
        self.assertEqual(dc.extract_ticket(make_issue())["completed_on"], "07 Jul 2026")

    def test_completed_on_prefers_design_finish_date(self):
        t = dc.extract_ticket(make_issue(fields={"customfield_13239": "2026-07-05"}))
        self.assertEqual(t["completed_on"], "05 Jul 2026")

    def test_product_epic_extracted_from_links(self):
        t = dc.extract_ticket(make_issue())
        self.assertEqual(t["product_epics"], [{
            "key": "VM-527",
            "summary": "[pod_vm] Search-Integrated Dynamic Edit Pages",
            "url": "https://altayerdigital.atlassian.net/browse/VM-527",
        }])

    def test_no_links_means_no_product_epic(self):
        t = dc.extract_ticket(make_issue(fields={"issuelinks": None}))
        self.assertEqual(t["product_epics"], [])

    def test_linked_non_epic_is_ignored(self):
        t = dc.extract_ticket(make_issue(fields={"issuelinks": [
            {"type": {"name": "Relates"}, "outwardIssue": {"key": "VM-600",
             "fields": {"summary": "a task", "issuetype": {"name": "Task"}}}}]}))
        self.assertEqual(t["product_epics"], [])

    def test_linked_opd_epic_is_ignored(self):
        # a link back to another OPD (design) epic is not a *product* epic
        t = dc.extract_ticket(make_issue(fields={"issuelinks": [
            {"type": {"name": "Relates"}, "inwardIssue": {"key": "OPD-9",
             "fields": {"summary": "another design epic", "issuetype": {"name": "Epic"}}}}]}))
        self.assertEqual(t["product_epics"], [])


class TestFormatBlock(unittest.TestCase):
    def test_block_has_markers_summary_slot_and_material(self):
        block = dc.format_block(dc.extract_ticket(make_issue()))
        self.assertIn("===MESSAGE===", block)
        self.assertIn("{{SUMMARY}}", block)
        self.assertIn("===MATERIAL", block)
        self.assertIn("===END===", block)

    def test_postable_part_has_fields_and_product_epic_link(self):
        block = dc.format_block(dc.extract_ticket(make_issue()))
        postable = block.split("===MATERIAL")[0]
        self.assertIn("[OPD-3](https://altayerdigital.atlassian.net/browse/OPD-3)", postable)
        self.assertIn("Dawid Tomczyk", postable)
        self.assertIn("07 Jul 2026", postable)
        self.assertIn("[VM platform - Phase 4 - Automated edit pages]"
                      "(https://www.figma.com/file/ZMG8YzYW96PCzvwZSZHoMp?node-id=4185%3A18730)", postable)
        self.assertIn("[VM-527](https://altayerdigital.atlassian.net/browse/VM-527)", postable)

    def test_material_has_description_and_linked_epic(self):
        block = dc.format_block(dc.extract_ticket(make_issue()))
        material = block.split("===MATERIAL")[1]
        self.assertIn("trend edit pages", material)
        self.assertIn("VM-527", material)

    def test_no_product_epic_omits_link_and_notes_absence(self):
        block = dc.format_block(dc.extract_ticket(make_issue(fields={"issuelinks": None})))
        postable = block.split("===MATERIAL")[0]
        self.assertNotIn("Feature epic:", postable)
        self.assertIn("none", block.split("===MATERIAL")[1].lower())


class TestRender(unittest.TestCase):
    def test_new_ticket_emits_block_and_reports_key(self):
        out, new_keys = dc.render([make_issue()], set())
        self.assertIn("OPD-3", out)
        self.assertIn("===MESSAGE===", out)
        self.assertEqual(new_keys, ["OPD-3"])

    def test_already_sent_ticket_is_skipped(self):
        out, new_keys = dc.render([make_issue()], {"OPD-3"})
        self.assertEqual(out, "")
        self.assertEqual(new_keys, [])

    def test_two_new_epics_two_blocks(self):
        out, new_keys = dc.render([make_issue(key="OPD-3"), make_issue(key="OPD-9")], set())
        self.assertEqual(out.count("===MESSAGE==="), 2)
        self.assertEqual(new_keys, ["OPD-3", "OPD-9"])


class TestSelectOutput(unittest.TestCase):
    def test_first_run_suppresses_output_but_records_keys(self):
        out, record = dc.select_output("some message", ["OPD-3"], is_first_run=True)
        self.assertEqual(out, "")
        self.assertEqual(record, ["OPD-3"])

    def test_normal_run_emits_output_and_records(self):
        out, record = dc.select_output("some message", ["OPD-3"], is_first_run=False)
        self.assertEqual(out, "some message")
        self.assertEqual(record, ["OPD-3"])


class TestCoerceIssues(unittest.TestCase):
    def test_plain_list(self):
        self.assertEqual(dc.coerce_issues([{"key": "OPD-1"}]), [{"key": "OPD-1"}])

    def test_issues_nodes_wrapper(self):
        self.assertEqual(dc.coerce_issues({"issues": {"nodes": [{"key": "OPD-1"}]}}), [{"key": "OPD-1"}])


class TestRun(unittest.TestCase):
    def test_query_returns_jql_json(self):
        import json
        self.assertIn("jql", json.loads(dc.run("query")))

    def test_render_cold_start_suppresses_output(self):
        import json, tempfile, os
        with tempfile.TemporaryDirectory() as d:
            out = dc.run("render", json.dumps([make_issue()]), state_path=os.path.join(d, "s.json"))
            self.assertEqual(out, "")

    def test_render_normal_run_emits_message(self):
        import json, tempfile, os
        with tempfile.TemporaryDirectory() as d:
            state = os.path.join(d, "s.json")
            with open(state, "w") as f:
                json.dump({"sent": []}, f)
            out = dc.run("render", json.dumps([make_issue()]), state_path=state)
            self.assertIn("OPD-3", out)

    def test_render_skips_already_sent(self):
        import json, tempfile, os
        with tempfile.TemporaryDirectory() as d:
            state = os.path.join(d, "s.json")
            with open(state, "w") as f:
                json.dump({"sent": ["OPD-3"]}, f)
            out = dc.run("render", json.dumps([make_issue()]), state_path=state)
            self.assertEqual(out, "")


if __name__ == "__main__":
    unittest.main()
