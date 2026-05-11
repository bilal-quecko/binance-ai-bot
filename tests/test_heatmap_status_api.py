from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import app


def test_heatmap_status_api_exposes_mock_quality_by_default() -> None:
    app.dependency_overrides[get_settings] = lambda: Settings()
    try:
        with TestClient(app) as client:
            response = client.get("/heatmap/status", params={"symbol": "BTCUSDT"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["configured_provider"] == "mock"
    assert payload["latest_snapshot"]["data_quality"] == "mock"
    assert payload["latest_snapshot"]["is_real_data"] is False


def test_heatmap_snapshot_api_exposes_data_quality_and_real_flag() -> None:
    app.dependency_overrides[get_settings] = lambda: Settings()
    try:
        with TestClient(app) as client:
            response = client.get("/heatmap/snapshot/BTCUSDT")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["symbol"] == "BTCUSDT"
    assert payload["data_quality"] == "mock"
    assert payload["is_real_data"] is False
