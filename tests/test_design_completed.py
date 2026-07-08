import os, sys, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from usecases import design_completed as dc


# A realistic OPD issue as returned by jira-rest (verified against OPD-3).
def make_issue(**overrides):
    fields = {
        "summary": "Search-Integrated Dynamic Edit Pages",
        "customfield_12707": [{"displayName": "Dawid Tomczyk"}],   # Product Owner = designer
        "customfield_13434": ["pod_vm"],                            # Pod (not used for routing now)
        "customfield_12714": [{                                     # Design (Figma)
            "displayName": "VM platform - Phase 4 - Automated edit pages",
            "url": "https://www.figma.com/file/ZMG8YzYW96PCzvwZSZHoMp?node-id=4185%3A18730",
        }],
        "customfield_13239": None,                                  # Actual Design/Research Finish Date
        "statuscategorychangedate": "2026-07-07T09:24:00.363+0400",  # went Done
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

    def test_fields_include_all_sources(self):
        fields = dc.build_query()["fields"]
        for fid in ("summary", "customfield_12707", "customfield_12714",
                    "customfield_13239", "statuscategorychangedate"):
            self.assertIn(fid, fields)


class TestExtractTicket(unittest.TestCase):
    def test_basic_fields(self):
        t = dc.extract_ticket(make_issue())
        self.assertEqual(t["key"], "OPD-3")
        self.assertEqual(t["summary"], "Search-Integrated Dynamic Edit Pages")
        self.assertEqual(t["designer"], "Dawid Tomczyk")

    def test_figma_links_extracted(self):
        t = dc.extract_ticket(make_issue())
        self.assertEqual(t["figma"], [(
            "VM platform - Phase 4 - Automated edit pages",
            "https://www.figma.com/file/ZMG8YzYW96PCzvwZSZHoMp?node-id=4185%3A18730",
        )])

    def test_completed_on_falls_back_to_done_timestamp(self):
        # customfield_13239 is null -> use statuscategorychangedate
        t = dc.extract_ticket(make_issue())
        self.assertEqual(t["completed_on"], "07 Jul 2026")

    def test_completed_on_prefers_design_finish_date(self):
        t = dc.extract_ticket(make_issue(fields={"customfield_13239": "2026-07-05"}))
        self.assertEqual(t["completed_on"], "05 Jul 2026")

    def test_multiple_designers_joined(self):
        t = dc.extract_ticket(make_issue(fields={"customfield_12707": [
            {"displayName": "Dawid Tomczyk"}, {"displayName": "Nihan Bektas"}]}))
        self.assertEqual(t["designer"], "Dawid Tomczyk, Nihan Bektas")

    def test_missing_designer_and_figma_are_empty(self):
        t = dc.extract_ticket(make_issue(fields={"customfield_12707": None, "customfield_12714": None}))
        self.assertEqual(t["designer"], "")
        self.assertEqual(t["figma"], [])


class TestFormatMessage(unittest.TestCase):
    def test_message_has_header_and_ticket_content(self):
        msg = dc.format_message([dc.extract_ticket(make_issue())])
        self.assertIn("Design completed", msg)
        self.assertIn("Search-Integrated Dynamic Edit Pages", msg)
        self.assertIn("Dawid Tomczyk", msg)
        self.assertIn("07 Jul 2026", msg)
        # Standard-markdown links (the Slack connector's format)
        self.assertIn("[OPD-3](https://altayerdigital.atlassian.net/browse/OPD-3)", msg)
        self.assertIn("[VM platform - Phase 4 - Automated edit pages]"
                      "(https://www.figma.com/file/ZMG8YzYW96PCzvwZSZHoMp?node-id=4185%3A18730)", msg)

    def test_multiple_tickets_share_one_message(self):
        msg = dc.format_message([dc.extract_ticket(make_issue(key="OPD-3")),
                                 dc.extract_ticket(make_issue(key="OPD-9"))])
        self.assertIn("OPD-3", msg)
        self.assertIn("OPD-9", msg)


class TestRender(unittest.TestCase):
    def test_new_ticket_emits_message_and_reports_key(self):
        out, new_keys = dc.render([make_issue()], set())
        self.assertIn("OPD-3", out)
        self.assertNotIn("==channel=", out)   # no channel tagging anymore
        self.assertEqual(new_keys, ["OPD-3"])

    def test_already_sent_ticket_is_skipped(self):
        out, new_keys = dc.render([make_issue()], {"OPD-3"})
        self.assertEqual(out, "")
        self.assertEqual(new_keys, [])

    def test_multiple_new_tickets_reported(self):
        out, new_keys = dc.render([make_issue(key="OPD-3"), make_issue(key="OPD-9")], set())
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

    def test_issues_list_wrapper(self):
        self.assertEqual(dc.coerce_issues({"issues": [{"key": "OPD-1"}]}), [{"key": "OPD-1"}])

    def test_issues_nodes_wrapper(self):
        payload = {"issues": {"nodes": [{"key": "OPD-1"}]}}
        self.assertEqual(dc.coerce_issues(payload), [{"key": "OPD-1"}])


class TestRun(unittest.TestCase):
    def test_query_returns_jql_json(self):
        import json
        self.assertIn("jql", json.loads(dc.run("query")))

    def test_render_cold_start_suppresses_output(self):
        import json, tempfile, os
        with tempfile.TemporaryDirectory() as d:
            state = os.path.join(d, "s.json")  # missing -> first run
            out = dc.run("render", json.dumps([make_issue()]), state_path=state)
            self.assertEqual(out, "")

    def test_render_normal_run_emits_message(self):
        import json, tempfile, os
        with tempfile.TemporaryDirectory() as d:
            state = os.path.join(d, "s.json")
            with open(state, "w") as f:
                json.dump({"sent": []}, f)  # exists -> not first run
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
