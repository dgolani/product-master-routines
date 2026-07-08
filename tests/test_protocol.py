import os, sys, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import protocol


class TestRenderBlocks(unittest.TestCase):
    def test_no_blocks_returns_empty_string(self):
        self.assertEqual(protocol.render_blocks([]), "")

    def test_single_block_is_header_then_body(self):
        out = protocol.render_blocks([("C123", "hello world")])
        self.assertEqual(out, "==channel=C123==\nhello world")

    def test_blocks_separated_by_blank_line(self):
        out = protocol.render_blocks([("C1", "a"), ("C2", "b\nb2")])
        self.assertEqual(out, "==channel=C1==\na\n\n==channel=C2==\nb\nb2")


if __name__ == "__main__":
    unittest.main()
