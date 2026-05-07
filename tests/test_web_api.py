"""
tests/test_web_api.py -- Tests for HOOK's FastAPI web server.

Tests endpoint structure and response formats.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
import pytest
from unittest.mock import AsyncMock, patch

# FastAPI test client
from fastapi.testclient import TestClient
from web.api.server import create_app


@pytest.fixture
def client():
    app = create_app()
    with TestClient(app) as c:
        yield c


class TestStatusEndpoint:
    def test_status_returns_ok(self, client):
        resp = client.get("/api/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "HOOK"
        assert "version" in data
        assert "agent_provider" in data
        assert "agent_count" in data

    def test_status_has_generated_at(self, client):
        resp = client.get("/api/status")
        data = resp.json()
        assert "generated_at" in data


class TestAgentsEndpoint:
    def test_agents_returns_list(self, client):
        resp = client.get("/api/agents")
        assert resp.status_code == 200
        data = resp.json()
        assert "agents" in data
        agents = data["agents"]
        assert len(agents) >= 6
        agent_ids = [a["id"] for a in agents]
        assert "coordinator" in agent_ids
        assert "triage-analyst" in agent_ids
        assert "osint-researcher" in agent_ids


class TestInvestigationsEndpoint:
    def test_investigations_returns_empty(self, client):
        resp = client.get("/api/investigations")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data

    def test_investigation_not_found(self, client):
        resp = client.get("/api/investigations/INV-NONEXISTENT")
        assert resp.status_code == 404

    def test_investigation_invalid_id(self, client):
        resp = client.get("/api/investigations/..%2Fetc%2Fpasswd")
        assert resp.status_code in (400, 404, 422)


class TestFeedsEndpoint:
    def test_feeds_returns_structure(self, client):
        resp = client.get("/api/feeds")
        assert resp.status_code == 200
        data = resp.json()
        assert "feeds" in data
        assert "watchlist_count" in data


class TestConversationsEndpoint:
    def test_conversations_requires_auth(self, client):
        # Unauthenticated callers must be rejected — this endpoint exposes
        # per-user conversation history.
        resp = client.get("/api/conversations")
        assert resp.status_code == 401


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
