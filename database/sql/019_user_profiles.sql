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

-- Internal accounts all belong to the same Chi cục. Keep this authoritative on
-- the server instead of relying on a browser-submitted agency field.
UPDATE app.users
SET unit_name = 'Chi cục Phát triển nông thôn Thành phố Hồ Chí Minh'
WHERE role IN ('admin', 'staff');

INSERT INTO app.user_profiles(user_id, agency_name)
SELECT id, 'Chi cục Phát triển nông thôn Thành phố Hồ Chí Minh'
FROM app.users
WHERE role IN ('admin', 'staff')
ON CONFLICT (user_id) DO UPDATE SET
    agency_name = EXCLUDED.agency_name;

INSERT INTO app.schema_migrations(version)
VALUES ('app_019_user_profiles')
ON CONFLICT (version) DO NOTHING;

COMMIT;
