-- Bootstrap script mounted into the PostgreSQL container's
-- /docker-entrypoint-initdb.d/ directory. Runs once, on first container
-- startup, against a fresh data volume.
--
-- The application itself creates/manages the `incidents` table via
-- SQLAlchemy (see src/db/session.py:init_db), so this script is
-- intentionally limited to extensions / housekeeping that should exist
-- ahead of time.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
