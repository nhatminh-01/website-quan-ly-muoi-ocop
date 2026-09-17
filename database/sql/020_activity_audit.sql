BEGIN;

ALTER TABLE app.audit_logs ADD COLUMN IF NOT EXISTS username_snapshot VARCHAR(255);
ALTER TABLE app.audit_logs ADD COLUMN IF NOT EXISTS full_name_snapshot VARCHAR(255);
ALTER TABLE app.audit_logs ADD COLUMN IF NOT EXISTS role_snapshot VARCHAR(20);
ALTER TABLE app.audit_logs ADD COLUMN IF NOT EXISTS department_snapshot VARCHAR(255);
ALTER TABLE app.audit_logs ADD COLUMN IF NOT EXISTS success BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE app.audit_logs ADD COLUMN IF NOT EXISTS ip_address VARCHAR(64);
ALTER TABLE app.audit_logs ADD COLUMN IF NOT EXISTS user_agent TEXT;

CREATE INDEX IF NOT EXISTS IX_App_AuditUserCreated
    ON app.audit_logs(user_id, created_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS IX_App_AuditModuleCreated
    ON app.audit_logs(module, created_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS IX_App_AuditSuccessCreated
    ON app.audit_logs(success, created_at DESC, id DESC);

INSERT INTO app.schema_migrations(version)
VALUES ('app_020_activity_audit')
ON CONFLICT (version) DO NOTHING;

COMMIT;
