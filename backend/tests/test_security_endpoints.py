import os
import sys
import unittest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.main import app
from app.models import User, Workout, BiomechanicsLog
from app.core.auth import get_current_user
from app.database import get_db


class SecurityEndpointsTests(unittest.TestCase):
    """Tests security boundaries: authentication, SSRF rejection, MIME filtering, and tenant isolation."""

    def setUp(self):
        self.client = TestClient(app)
        self.mock_user = User(
            id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
            email="athlete@example.com"
        )

    def test_upload_url_requires_auth(self):
        """Unauthenticated calls to /storage/upload-url must be rejected with 401."""
        app.dependency_overrides.clear()
        res = self.client.post("/api/v1/storage/upload-url", json={"filename": "test.mp4", "content_type": "video/mp4"})
        self.assertEqual(res.status_code, 401)

    def test_upload_url_rejects_unsupported_mime(self):
        """Authenticated calls with invalid MIME type must be rejected with 415."""
        app.dependency_overrides[get_current_user] = lambda: self.mock_user
        try:
            res = self.client.post(
                "/api/v1/storage/upload-url",
                json={"filename": "payload.exe", "content_type": "application/x-msdownload"}
            )
            self.assertEqual(res.status_code, 415)
            self.assertIn("Unsupported video type", res.json()["detail"])
        finally:
            app.dependency_overrides.clear()

    def test_analyze_requires_auth(self):
        """Unauthenticated calls to /analyze must be rejected with 401."""
        app.dependency_overrides.clear()
        res = self.client.post("/api/v1/analyze", json={"video_storage_path": "https://pub-r2.dev/video.mp4"})
        self.assertEqual(res.status_code, 401)

    def test_analyze_rejects_arbitrary_ssrf_host(self):
        """Calls with arbitrary untrusted URLs must be rejected with 422 (SSRF prevention)."""
        app.dependency_overrides[get_current_user] = lambda: self.mock_user
        try:
            res = self.client.post(
                "/api/v1/analyze",
                json={"video_storage_path": "https://attacker.evil.com/video.mp4"}
            )
            self.assertEqual(res.status_code, 422)
            self.assertIn("approved storage provider", res.json()["detail"])
        finally:
            app.dependency_overrides.clear()

    def test_history_requires_auth(self):
        """Unauthenticated calls to /history must be rejected with 401."""
        app.dependency_overrides.clear()
        res = self.client.get("/api/v1/history")
        self.assertEqual(res.status_code, 401)

    def test_results_requires_auth(self):
        """Unauthenticated calls to /results/{id} must be rejected with 401."""
        app.dependency_overrides.clear()
        res = self.client.get("/api/v1/results/1")
        self.assertEqual(res.status_code, 401)

    def test_cors_preflight_allows_vercel_domains(self):
        """CORS preflight requests from Vercel subdomains must be accepted."""
        for origin in ["https://gym-app.vercel.app", "https://preview-123.vercel.app"]:
            res = self.client.options(
                "/api/v1/status",
                headers={
                    "Origin": origin,
                    "Access-Control-Request-Method": "GET",
                    "Access-Control-Request-Headers": "Authorization,Content-Type",
                }
            )
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.headers.get("access-control-allow-origin"), origin)

    def test_cors_preflight_rejects_untrusted_origins(self):
        """CORS preflight requests from arbitrary origins must be rejected."""
        res = self.client.options(
            "/api/v1/status",
            headers={
                "Origin": "https://malicious-attacker.com",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "Authorization,Content-Type",
            }
        )
        self.assertEqual(res.status_code, 400)


if __name__ == "__main__":
    unittest.main()

