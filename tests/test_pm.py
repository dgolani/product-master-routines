import os, sys, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pm


class TestDispatch(unittest.TestCase):
    def test_unknown_use_case_exits_nonzero(self):
        out, code = pm.dispatch(["not-a-real-use-case"])
        self.assertNotEqual(code, 0)

    def test_no_args_exits_nonzero(self):
        out, code = pm.dispatch([])
        self.assertNotEqual(code, 0)

    def test_known_use_case_query_succeeds(self):
        out, code = pm.dispatch(["design-completed", "query"])
        self.assertEqual(code, 0)
        self.assertIn("jql", out)

    def test_design_completed_is_registered(self):
        self.assertIn("design-completed", pm.USE_CASES)


if __name__ == "__main__":
    unittest.main()
