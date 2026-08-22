import tempfile
import unittest
from pathlib import Path
from unittest import mock

from api.app import database


class ProgressTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        path = Path(self.temporary.name) / "test.sqlite3"
        self.patcher = mock.patch.object(database, "DATABASE_PATH", path)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        database.initialize_database()

    def test_progress_marks_attempted_then_solved(self):
        database.save_submission(
            "demo-problem", "python3", "code", "wrong_answer", 2, 5, 10, [], "session-a"
        )
        self.assertEqual({"demo-problem": "attempted"}, database.list_progress("session-a"))
        # Solved means any one language passed — a later accepted cpp run flips it.
        database.save_submission(
            "demo-problem", "cpp", "code", "accepted", 5, 5, 8, [], "session-a"
        )
        self.assertEqual({"demo-problem": "solved"}, database.list_progress("session-a"))

    def test_progress_is_scoped_to_its_owner(self):
        database.save_submission(
            "demo-problem", "python3", "code", "accepted", 5, 5, 8, [], "user:1"
        )
        self.assertEqual({}, database.list_progress("session-a"))
        self.assertEqual({"demo-problem": "solved"}, database.list_progress("user:1"))

    def test_reference_runtime_is_stored_with_the_attempt(self):
        database.save_submission(
            "demo-problem", "python3", "code", "accepted", 5, 5, 8, [], "session-a", 123
        )
        rows = database.list_submissions("demo-problem", session_id="session-a")
        self.assertEqual(123, rows[0]["reference_runtime_ms"])


if __name__ == "__main__":
    unittest.main()
