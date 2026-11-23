import tempfile
import unittest
from pathlib import Path

from humanos.core import Store, verify_source


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(str(Path(self.tmp.name) / "test.db"))
        self.goal = self.store.create_goal("Training opportunities", ["scholarship", "python"])

    def tearDown(self):
        self.tmp.cleanup()

    def test_source_requires_https(self):
        self.assertFalse(verify_source("http://example.org"))
        self.assertFalse(verify_source("file:///etc/passwd"))
        self.assertFalse(verify_source("https://user:pass@example.org"))
        self.assertTrue(verify_source("https://example.org/path"))

    def test_queued_candidate_is_screened_and_audited(self):
        candidate = self.store.add_candidate(
            self.goal["id"], "Python scholarship", "Learn Python", "https://example.org/program")
        self.assertEqual(candidate["state"], "queued")
        evaluated = self.store.evaluate_candidate(candidate["id"])
        self.assertEqual(evaluated["state"], "review")
        self.assertIn("python", evaluated["evaluation"]["matched_keywords"])
        self.assertEqual(len(self.store.events(candidate["id"])), 2)

    def test_no_match_cannot_be_approved(self):
        candidate = self.store.add_candidate(
            self.goal["id"], "Cooking class", "Kitchen tips", "https://example.org")
        self.store.evaluate_candidate(candidate["id"])
        self.assertEqual(self.store.get_candidate(candidate["id"])["state"], "insufficient_evidence")
        with self.assertRaises(ValueError):
            self.store.review(candidate["id"], "approved")

    def test_approval_has_no_external_execution(self):
        candidate = self.store.add_candidate(
            self.goal["id"], "Scholarship", "Description", "https://example.org")
        self.store.run_queued()
        reviewed = self.store.review(candidate["id"], "approved")
        self.assertEqual(reviewed["state"], "approved")
        self.assertEqual(len(self.store.events(candidate["id"])), 3)
        self.assertEqual(self.store.run_queued()["evaluated"], 0)

    def test_persistence_and_idempotence(self):
        candidate = self.store.add_candidate(
            self.goal["id"], "Python", "Course", "https://example.org")
        self.assertEqual(self.store.run_queued()["evaluated"], 1)
        self.assertEqual(self.store.run_queued()["evaluated"], 0)
        reopened = Store(self.store.path)
        self.assertEqual(reopened.get_candidate(candidate["id"])["state"], "review")

    def test_nonexistent_goal_rejected(self):
        with self.assertRaises(LookupError):
            self.store.add_candidate("missing", "Name", "Desc", "https://example.org")


if __name__ == "__main__":
    unittest.main()
