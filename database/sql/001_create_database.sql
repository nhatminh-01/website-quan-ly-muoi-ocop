-- Run while connected to the maintenance database (normally postgres).
-- psql variables are used so this script remains rerunnable.
SELECT 'CREATE DATABASE ptnt_qd5277_dev WITH ENCODING ''UTF8'' TEMPLATE template0'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'ptnt_qd5277_dev')
\gexec

