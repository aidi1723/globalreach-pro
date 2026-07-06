import sqlite3

from app.services.secret_store import EphemeralSecretStore
from app.storage.db import AppStorage


def test_smtp_passwords_are_not_persisted_in_sqlite(tmp_path):
    db_path = tmp_path / "secrets.db"
    storage = AppStorage(db_path, secret_store=EphemeralSecretStore())

    storage.save_smtp_account(
        {
            "label": "sales@example.com",
            "provider": "custom",
            "sender_email": "sales@example.com",
            "sender_name": "Sales",
            "username": "sales",
            "password": "smtp-secret",
            "host": "smtp.example.com",
            "port": "465",
            "security": "ssl",
            "dkim_selector": "",
        }
    )

    assert storage.get_smtp_account("sales@example.com")["password"] == "smtp-secret"

    with sqlite3.connect(db_path) as conn:
        raw_password = conn.execute(
            "SELECT password FROM smtp_accounts WHERE label = ?",
            ("sales@example.com",),
        ).fetchone()[0]

    assert raw_password != "smtp-secret"
    assert raw_password.startswith("secret://")


def test_sensitive_app_state_values_are_not_persisted_in_sqlite(tmp_path):
    db_path = tmp_path / "state-secrets.db"
    storage = AppStorage(db_path, secret_store=EphemeralSecretStore())

    storage.set_state("ai_api_key", "ai-secret")
    storage.set_state("license_key", "LICENSE-SECRET")
    storage.set_state("license_activation_token", "act_secret")
    storage.set_state("ai_model", "gpt-test")

    assert storage.get_state("ai_api_key") == "ai-secret"
    assert storage.get_state("license_key") == "LICENSE-SECRET"
    assert storage.get_state("license_activation_token") == "act_secret"
    assert storage.get_state("ai_model") == "gpt-test"

    with sqlite3.connect(db_path) as conn:
        rows = dict(conn.execute("SELECT key, value FROM app_state").fetchall())

    assert rows["ai_api_key"] != "ai-secret"
    assert rows["license_key"] != "LICENSE-SECRET"
    assert rows["license_activation_token"] != "act_secret"
    assert rows["ai_model"] == "gpt-test"


def test_legacy_plaintext_secrets_are_migrated_out_of_sqlite(tmp_path):
    db_path = tmp_path / "legacy-secrets.db"
    secret_store = EphemeralSecretStore()
    storage = AppStorage(db_path, secret_store=secret_store)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO smtp_accounts(
                label, provider, sender_email, sender_name, username, password,
                host, port, security, dkim_selector, created_at, updated_at
            )
            VALUES('legacy', 'custom', 'legacy@example.com', 'Legacy', 'legacy',
                   'legacy-password', 'smtp.example.com', 465, 'ssl', '', 'now', 'now')
            """
        )
        conn.execute(
            "INSERT INTO app_state(key, value, updated_at) VALUES('ai_api_key', 'legacy-ai-key', 'now')"
        )

    migrated = AppStorage(db_path, secret_store=secret_store)

    assert migrated.get_smtp_account("legacy")["password"] == "legacy-password"
    assert migrated.get_state("ai_api_key") == "legacy-ai-key"

    with sqlite3.connect(db_path) as conn:
        raw_password = conn.execute(
            "SELECT password FROM smtp_accounts WHERE label = 'legacy'"
        ).fetchone()[0]
        raw_ai_key = conn.execute(
            "SELECT value FROM app_state WHERE key = 'ai_api_key'"
        ).fetchone()[0]

    assert raw_password.startswith("secret://")
    assert raw_ai_key.startswith("secret://")
    assert raw_password != "legacy-password"
    assert raw_ai_key != "legacy-ai-key"
