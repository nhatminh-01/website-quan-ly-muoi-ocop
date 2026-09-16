BEGIN;

CREATE TABLE IF NOT EXISTS app.user_profiles (
    user_id INTEGER PRIMARY KEY REFERENCES app.users(id) ON DELETE CASCADE,
    full_name VARCHAR(255) NOT NULL DEFAULT '',
    job_title VARCHAR(255) NOT NULL DEFAULT '',
    department VARCHAR(255) NOT NULL DEFAULT '',
    phone VARCHAR(50) NOT NULL DEFAULT '',
    official_email VARCHAR(255) NOT NULL DEFAULT '',
    agency_name VARCHAR(255) NOT NULL DEFAULT 'Chi cục Phát triển nông thôn Thành phố Hồ Chí Minh',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO app.user_profiles(user_id, agency_name)
SELECT id, 'Chi cục Phát triển nông thôn Thành phố Hồ Chí Minh'
FROM app.users
WHERE role IN ('admin', 'staff')
ON CONFLICT (user_id) DO NOTHING;

INSERT INTO app.schema_migrations(version)
VALUES ('app_019_user_profiles')
ON CONFLICT (version) DO NOTHING;

COMMIT;
