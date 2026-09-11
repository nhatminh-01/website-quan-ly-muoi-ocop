-- Run once as PostgreSQL administrator inside ptnt_qd5277_dev.
-- The password is intentionally not stored here; set it with \password ptnt_team.
\set ON_ERROR_STOP on

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ptnt_team') THEN
        CREATE ROLE ptnt_team LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
    END IF;
END $$;

ALTER DATABASE ptnt_qd5277_dev OWNER TO ptnt_team;
ALTER SCHEMA app OWNER TO ptnt_team;
ALTER SCHEMA qd5277 OWNER TO ptnt_team;
ALTER SCHEMA staging OWNER TO ptnt_team;

DO $$
DECLARE
    item RECORD;
    object_type TEXT;
BEGIN
    FOR item IN
        SELECT n.nspname, c.relname, c.relkind
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname IN ('app', 'qd5277', 'staging')
          AND c.relkind IN ('r', 'p', 'S', 'v', 'm')
        ORDER BY CASE WHEN c.relkind = 'S' THEN 2 ELSE 1 END, n.nspname, c.relname
    LOOP
        object_type := CASE item.relkind
            WHEN 'S' THEN 'SEQUENCE'
            WHEN 'v' THEN 'VIEW'
            WHEN 'm' THEN 'MATERIALIZED VIEW'
            ELSE 'TABLE'
        END;
        EXECUTE format('ALTER %s %I.%I OWNER TO ptnt_team', object_type, item.nspname, item.relname);
    END LOOP;
END $$;

GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA app, qd5277, staging TO ptnt_team;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA app, qd5277, staging TO ptnt_team;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA app, qd5277, staging TO ptnt_team;

ALTER DEFAULT PRIVILEGES FOR ROLE ptnt_team IN SCHEMA app
    GRANT ALL PRIVILEGES ON TABLES TO ptnt_team;
ALTER DEFAULT PRIVILEGES FOR ROLE ptnt_team IN SCHEMA qd5277
    GRANT ALL PRIVILEGES ON TABLES TO ptnt_team;
ALTER DEFAULT PRIVILEGES FOR ROLE ptnt_team IN SCHEMA staging
    GRANT ALL PRIVILEGES ON TABLES TO ptnt_team;
ALTER DEFAULT PRIVILEGES FOR ROLE ptnt_team IN SCHEMA app
    GRANT ALL PRIVILEGES ON SEQUENCES TO ptnt_team;
ALTER DEFAULT PRIVILEGES FOR ROLE ptnt_team IN SCHEMA qd5277
    GRANT ALL PRIVILEGES ON SEQUENCES TO ptnt_team;
ALTER DEFAULT PRIVILEGES FOR ROLE ptnt_team IN SCHEMA staging
    GRANT ALL PRIVILEGES ON SEQUENCES TO ptnt_team;
