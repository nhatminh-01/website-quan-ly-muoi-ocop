-- Legacy commune/ward accounts remain permanent historical identities.
-- Never delete or remap their business rows, credentials, profiles or audit logs.
BEGIN;

CREATE OR REPLACE FUNCTION app.protect_archived_user()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        IF OLD.role IN ('unit', 'legacy') THEN
            RAISE EXCEPTION USING
                ERRCODE = '23514',
                MESSAGE = 'Legacy commune/ward accounts are retained for history and cannot be deleted.';
        END IF;
        RETURN OLD;
    END IF;

    IF TG_OP = 'UPDATE' THEN
        IF OLD.role IN ('unit', 'legacy') THEN
            IF ROW(NEW.id, NEW.username, NEW.role)
               IS DISTINCT FROM ROW(OLD.id, OLD.username, OLD.role) THEN
                RAISE EXCEPTION USING
                    ERRCODE = '23514',
                    MESSAGE = 'The identity and role of a historical account cannot be changed.';
            END IF;
            -- admin_units.update_unit synchronizes a renamed catalog label.
            -- Permit only the current official name for the EXISTING mapping;
            -- an arbitrary unit name or a different geography remains blocked.
            IF NEW.unit_name IS DISTINCT FROM OLD.unit_name AND NOT EXISTS (
                SELECT 1
                FROM app.user_admin_units AS mapping
                JOIN qd5277.DM_DonViHanhChinh AS unit
                  ON unit.Ma_DonViHanhChinh = mapping.ma_don_vi_hanh_chinh
                WHERE mapping.user_id = OLD.id
                  AND unit.TenDonVi = NEW.unit_name
            ) THEN
                RAISE EXCEPTION USING
                    ERRCODE = '23514',
                    MESSAGE = 'A historical account must retain its existing administrative unit.';
            END IF;
            IF NEW.active IS DISTINCT FROM FALSE THEN
                RAISE EXCEPTION USING
                    ERRCODE = '23514',
                    MESSAGE = 'Historical commune/ward accounts cannot be reactivated.';
            END IF;
        END IF;
    END IF;

    -- Keep compatibility with historical imports/fixtures without creating an
    -- account that can log in, even if an INSERT relies on active's old default.
    IF NEW.role IN ('unit', 'legacy') THEN
        NEW.active := FALSE;
    END IF;
    RETURN NEW;
END;
$$;

-- Replace only this migration's trigger; no application data is removed.
DROP TRIGGER IF EXISTS users_protect_archived_identity ON app.users;
CREATE TRIGGER users_protect_archived_identity
BEFORE INSERT OR UPDATE OR DELETE ON app.users
FOR EACH ROW EXECUTE FUNCTION app.protect_archived_user();

DO $$
DECLARE
    deactivated_count BIGINT;
BEGIN
    UPDATE app.users
       SET active = FALSE
     WHERE role IN ('unit', 'legacy')
       AND active IS DISTINCT FROM FALSE;
    GET DIAGNOSTICS deactivated_count = ROW_COUNT;
    RAISE NOTICE 'Legacy commune/ward accounts deactivated: %', deactivated_count;
END;
$$;

INSERT INTO app.schema_migrations(version)
VALUES ('app_022_archive_legacy_users')
ON CONFLICT (version) DO NOTHING;

COMMIT;
