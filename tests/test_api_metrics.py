"""Tests for cloud liveness, readiness, and Prometheus exposition metrics."""

from fastapi.testclient import TestClient
import pytest

from cloud_bean.api.app import create_app


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


def test_healthz_liveness(client):
    res = client.get("/healthz")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_readyz_readiness(client):
    res = client.get("/readyz")
    assert res.status_code == 200
    assert res.json() == {"status": "ready"}


def test_prometheus_metrics_format(client):
    res = client.get("/metrics")
    assert res.status_code == 200
    assert "text/plain" in res.headers["content-type"]
    text = res.text

    assert "# HELP cloud_bean_events_total" in text
    assert "# TYPE cloud_bean_events_total counter" in text
    assert "cloud_bean_events_total 0" in text

    assert "# HELP cloud_bean_budget_spent_usd" in text
    assert "# TYPE cloud_bean_budget_spent_usd gauge" in text
    assert "cloud_bean_budget_spent_usd 0.0000" in text

    assert "cloud_bean_budget_max_usd 10.0000" in text
    assert "# HELP cloud_bean_findings_total" in text
    assert "# TYPE cloud_bean_findings_total counter" in text
