CREATE TABLE IF NOT EXISTS products (
    id BIGSERIAL PRIMARY KEY,
    product_code VARCHAR(64) NOT NULL UNIQUE,
    product_name VARCHAR(255) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS customers (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    company VARCHAR(255) NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS license_keys (
    id BIGSERIAL PRIMARY KEY,
    product_code VARCHAR(64) NOT NULL REFERENCES products(product_code),
    customer_id BIGINT REFERENCES customers(id),
    license_key VARCHAR(128) NOT NULL UNIQUE,
    plan_name VARCHAR(64) NOT NULL DEFAULT 'single-device',
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    max_activations INTEGER NOT NULL DEFAULT 1,
    validity_seconds INTEGER NOT NULL DEFAULT 0,
    expires_at TIMESTAMPTZ,
    issued_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_validated_at TIMESTAMPTZ,
    notes TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS license_activations (
    id BIGSERIAL PRIMARY KEY,
    license_key_id BIGINT NOT NULL REFERENCES license_keys(id),
    product_code VARCHAR(64) NOT NULL REFERENCES products(product_code),
    machine_id VARCHAR(255) NOT NULL,
    machine_name VARCHAR(255) NOT NULL DEFAULT '',
    device_label VARCHAR(255) NOT NULL DEFAULT '',
    os_name VARCHAR(64) NOT NULL DEFAULT '',
    os_version TEXT NOT NULL DEFAULT '',
    app_version VARCHAR(64) NOT NULL DEFAULT '',
    activation_token VARCHAR(255) NOT NULL UNIQUE,
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    released_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS license_events (
    id BIGSERIAL PRIMARY KEY,
    license_key_id BIGINT REFERENCES license_keys(id),
    activation_id BIGINT REFERENCES license_activations(id),
    product_code VARCHAR(64) NOT NULL,
    event_type VARCHAR(64) NOT NULL,
    operator_id BIGINT,
    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS admin_users (
    id BIGSERIAL PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role VARCHAR(64) NOT NULL DEFAULT 'admin',
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
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
