import struct
import unittest
from pathlib import Path

from api.app.problems import parse_problem_markdown
from runner.executors.base import ExecutorError
from runner.executors.typed import encode_case, function_signature


ROOT = Path(__file__).resolve().parents[1]


class TypedExecutorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        path = ROOT / "problems" / "0001_two-sum.md"
        problem, _, _ = parse_problem_markdown(path.read_text(encoding="utf-8"), path)
        cls.invocation = problem["invocation"]

    def test_two_sum_case_has_a_language_neutral_binary_encoding(self) -> None:
        expected = (
            struct.pack(">I", 4)
            + struct.pack(">iiii", 2, 7, 11, 15)
            + struct.pack(">i", 9)
        )
        for language in ("cpp", "javascript", "typescript", "go", "rust"):
            with self.subTest(language=language):
                self.assertEqual(
                    expected,
                    encode_case(self.invocation, [[2, 7, 11, 15], 9], language),
                )

    def test_language_entrypoints_share_one_value_signature(self) -> None:
        methods = {}
        for language in ("cpp", "javascript", "typescript", "go", "rust"):
            parameters, result, methods[language] = function_signature(
                self.invocation, language
            )
            self.assertEqual(["array", "integer"], [item["kind"] for item in parameters])
            self.assertEqual("array", result["kind"])
        self.assertEqual(
            {
                "cpp": "twoSum",
                "javascript": "twoSum",
                "typescript": "twoSum",
                "go": "twoSum",
                "rust": "two_sum",
            },
            methods,
        )

    def test_out_of_range_integer_is_rejected_before_runner_dispatch(self) -> None:
        with self.assertRaisesRegex(ExecutorError, "signed 32-bit range"):
            encode_case(self.invocation, [[2, 7], 2**40], "cpp")


if __name__ == "__main__":
    unittest.main()
