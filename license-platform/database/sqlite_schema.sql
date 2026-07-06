CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_code TEXT NOT NULL UNIQUE,
    product_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    company TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS license_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_code TEXT NOT NULL,
    customer_id INTEGER,
    license_key TEXT NOT NULL UNIQUE,
    plan_name TEXT NOT NULL DEFAULT 'single-device',
    status TEXT NOT NULL DEFAULT 'active',
    max_activations INTEGER NOT NULL DEFAULT 1,
    validity_seconds INTEGER NOT NULL DEFAULT 0,
    expires_at TEXT NOT NULL DEFAULT '',
    issued_at TEXT NOT NULL,
    last_validated_at TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS license_activations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    license_key_id INTEGER NOT NULL,
    product_code TEXT NOT NULL,
    machine_id TEXT NOT NULL,
    machine_name TEXT NOT NULL DEFAULT '',
    device_label TEXT NOT NULL DEFAULT '',
    os_name TEXT NOT NULL DEFAULT '',
    os_version TEXT NOT NULL DEFAULT '',
    app_version TEXT NOT NULL DEFAULT '',
    activation_token TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'active',
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    released_at TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS license_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    license_key_id INTEGER,
    activation_id INTEGER,
    product_code TEXT NOT NULL,
    event_type TEXT NOT NULL,
    operator_id INTEGER,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS admin_users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'admin',
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_license_keys_product_code
ON license_keys(product_code);

CREATE INDEX IF NOT EXISTS idx_license_keys_product_code_license_key
ON license_keys(product_code, license_key);

CREATE INDEX IF NOT EXISTS idx_license_activations_license_key_status
ON license_activations(license_key_id, status);

CREATE INDEX IF NOT EXISTS idx_license_activations_machine_lookup
ON license_activations(license_key_id, machine_id, status);

CREATE UNIQUE INDEX IF NOT EXISTS uq_license_activations_active_machine
ON license_activations(license_key_id, machine_id)
WHERE status = 'active';

CREATE INDEX IF NOT EXISTS idx_license_activations_token_lookup
ON license_activations(license_key_id, machine_id, activation_token);

CREATE INDEX IF NOT EXISTS idx_license_events_product_code_created_at
ON license_events(product_code, created_at);

CREATE INDEX IF NOT EXISTS idx_admin_users_email_status
ON admin_users(email, status);
