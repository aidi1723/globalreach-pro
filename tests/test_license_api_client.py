import json
from urllib import error

import pytest

from app.services import license_api_client


class FakeStorage:
    def __init__(self, values=None):
        self.values = values or {}

    def get_state(self, key):
        return self.values.get(key)


def test_load_license_server_settings_prefers_storage(monkeypatch):
    monkeypatch.delenv("GLOBALREACH_LICENSE_API_BASE_URL", raising=False)
    monkeypatch.delenv("GLOBALREACH_LICENSE_PRODUCT_CODE", raising=False)
    storage = FakeStorage(
        {
            "license_api_base_url": "https://license.example.com",
            "license_product_code": "globalreach_pro",
        }
    )

    settings = license_api_client.load_license_server_settings(storage)

    assert settings.base_url == "https://license.example.com"
    assert settings.product_code == "globalreach_pro"
    assert settings.enabled is True


def test_load_license_server_settings_prefers_env(monkeypatch):
    monkeypatch.setenv("GLOBALREACH_LICENSE_API_BASE_URL", "https://env.example.com")
    monkeypatch.setenv("GLOBALREACH_LICENSE_PRODUCT_CODE", "env_product")
    storage = FakeStorage(
        {
            "license_api_base_url": "https://storage.example.com",
            "license_product_code": "storage_product",
        }
    )

    settings = license_api_client.load_license_server_settings(storage)

    assert settings.base_url == "https://env.example.com"
    assert settings.product_code == "env_product"


def test_activate_license_maps_response(monkeypatch):
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(
                {
                    "ok": True,
                    "message": "Activation successful.",
                    "license_status": "active",
                    "activation_status": "active",
                    "activation_token": "act_123",
                    "expires_at": "2027-01-01T00:00:00Z",
                    "plan_name": "single-device",
                    "max_activations": 1,
                }
            ).encode("utf-8")

    def fake_urlopen(req, timeout):
        captured["url"] = req.full_url
        captured["timeout"] = timeout
        captured["payload"] = json.loads(req.data.decode("utf-8"))
        return FakeResponse()

    monkeypatch.setattr(license_api_client.request, "urlopen", fake_urlopen)
    settings = license_api_client.LicenseServerSettings(
        base_url="https://license.example.com",
        product_code="globalreach_pro",
    )

    snapshot = license_api_client.activate_license(
        settings,
        "ABC-123",
        "CYFVK1G3PP",
        "2026.04.14",
    )

    assert captured["url"] == "https://license.example.com/api/v1/licenses/activate"
    assert captured["payload"]["product_code"] == "globalreach_pro"
    assert captured["payload"]["machine_id"] == "CYFVK1G3PP"
    assert snapshot.ok is True
    assert snapshot.activation_token == "act_123"


def test_release_license_sends_activation_token(monkeypatch):
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps({"ok": True, "message": "Activation released."}).encode("utf-8")

    def fake_urlopen(req, timeout):
        captured["url"] = req.full_url
        captured["payload"] = json.loads(req.data.decode("utf-8"))
        return FakeResponse()

    monkeypatch.setattr(license_api_client.request, "urlopen", fake_urlopen)
    settings = license_api_client.LicenseServerSettings(
        base_url="https://license.example.com",
        product_code="globalreach_pro",
    )

    snapshot = license_api_client.release_license(
        settings,
        "ABC-123",
        "act_123",
        "CYFVK1G3PP",
    )

    assert captured["url"] == "https://license.example.com/api/v1/licenses/release"
    assert captured["payload"]["activation_token"] == "act_123"
    assert snapshot.ok is True


def test_post_json_raises_readable_api_error(monkeypatch):
    def fake_urlopen(_req, timeout=None):
        raise error.URLError("offline")

    monkeypatch.setattr(license_api_client.request, "urlopen", fake_urlopen)

    with pytest.raises(license_api_client.LicenseAPIError, match="连接授权服务失败"):
        license_api_client._post_json("https://license.example.com/test", {}, 5)
