import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runner"))

from leetcode_types import decode, encode  # noqa: E402


class LeetCodeCodecTests(unittest.TestCase):
    def test_linked_list_round_trip(self) -> None:
        for sample in ([], [1], [1, 2, 3], [-4, 0, 8]):
            with self.subTest(sample=sample):
                self.assertEqual(sample, encode(decode(sample, "list_node"), "list_node"))

    def test_binary_tree_round_trip(self) -> None:
        samples = ([], [1], [1, 2, 3], [1, None, 2, None, 3], [1, 2, 3, None, None, 4, 5])
        for sample in samples:
            with self.subTest(sample=sample):
                self.assertEqual(sample, encode(decode(sample, "tree_node"), "tree_node"))

    def test_nary_tree_round_trip(self) -> None:
        samples = ([], [1], [1, None, 3, 2, 4, None, 5, 6])
        for sample in samples:
            with self.subTest(sample=sample):
                self.assertEqual(sample, encode(decode(sample, "nary_tree"), "nary_tree"))

    def test_nested_integer_top_level(self) -> None:
        values = decode([[1, 2], 3, [], [4, [5]]], "nested_integer_list")
        self.assertFalse(values[0].isInteger())
        self.assertEqual(3, values[1].getInteger())
        self.assertEqual([], values[2].getList())
        self.assertEqual(5, values[3].getList()[1].getList()[0].getInteger())


if __name__ == "__main__":
    unittest.main()

