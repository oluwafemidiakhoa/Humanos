import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from humanos.api import app


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {
            "HUMANOS_API_KEY": "local-test-api-key-long-enough",
            "HUMANOS_DB_PATH": str(Path(self.tmp.name) / "api.db"),
        })
        self.env.start()
        self.client = TestClient(app)
        self.headers = {"Authorization": "Bearer local-test-api-key-long-enough"}

    def tearDown(self):
        self.client.close()
        self.env.stop()
        self.tmp.cleanup()

    def test_denies_unauthorized_access(self):
        self.assertEqual(self.client.get("/v1/goals").status_code, 401)
        self.assertEqual(self.client.post("/v1/workers/run-once").status_code, 401)

    def test_missing_api_key_fails_closed(self):
        with patch.dict(os.environ, {"HUMANOS_API_KEY": ""}):
            self.assertEqual(self.client.get("/v1/goals", headers=self.headers).status_code, 503)

    def test_goal_and_candidate_workflow(self):
        goal = self.client.post(
            "/v1/goals", headers=self.headers,
            json={"title": "Education", "keywords": ["scholarship"]}
        )
        self.assertEqual(goal.status_code, 201)
        candidate = self.client.post(
            "/v1/candidates", headers=self.headers,
            json={"goal_id": goal.json()["id"], "title": "Scholarship",
                  "description": "Opportunity", "source_url": "https://example.org"}
        )
        self.assertEqual(candidate.status_code, 201)
        cid = candidate.json()["id"]
        result = self.client.post("/v1/workers/run-once", headers=self.headers)
        self.assertEqual(result.json()["evaluated"], 1)
        self.assertEqual(self.client.post(
            f"/v1/candidates/{cid}/decision", headers=self.headers,
            json={"decision": "approved"}).status_code, 200)

    def test_cannot_approve_queued_candidate(self):
        goal = self.client.post("/v1/goals", headers=self.headers,
                                json={"title": "Education", "keywords": ["course"]}).json()
        c = self.client.post("/v1/candidates", headers=self.headers,
                             json={"goal_id": goal["id"], "title": "Course",
                                   "description": "Learning",
                                   "source_url": "https://example.org"}).json()
        response = self.client.post(
            f"/v1/candidates/{c['id']}/decision", headers=self.headers,
            json={"decision": "approved"})
        self.assertEqual(response.status_code, 409)


if __name__ == "__main__":
    unittest.main()
