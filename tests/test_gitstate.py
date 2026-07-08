import os, sys, json, subprocess, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import gitstate


class TestLoadSent(unittest.TestCase):
    def test_missing_file_is_empty_set(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(gitstate.load_sent(os.path.join(d, "s.json")), set())

    def test_reads_keys(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "s.json")
            with open(p, "w") as f:
                json.dump({"sent": ["OPD-1", "OPD-2"]}, f)
            self.assertEqual(gitstate.load_sent(p), {"OPD-1", "OPD-2"})

    def test_corrupt_file_is_empty_set(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "s.json")
            with open(p, "w") as f:
                f.write("{ not json")
            self.assertEqual(gitstate.load_sent(p), set())


class TestSaveSent(unittest.TestCase):
    def test_writes_state_to_working_tree_in_git_repo(self):
        cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as d:
            try:
                os.chdir(d)
                subprocess.run(["git", "init"], capture_output=True)
                gitstate.save_sent("s.json", {"OPD-2", "OPD-1"}, "chore: test")
                with open("s.json") as f:
                    data = json.load(f)
                self.assertEqual(set(data["sent"]), {"OPD-1", "OPD-2"})
            finally:
                os.chdir(cwd)

    def test_state_exists_reflects_file_presence(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "s.json")
            self.assertFalse(gitstate.state_exists(p))
            with open(p, "w") as f:
                json.dump({"sent": []}, f)
            self.assertTrue(gitstate.state_exists(p))


if __name__ == "__main__":
    unittest.main()
