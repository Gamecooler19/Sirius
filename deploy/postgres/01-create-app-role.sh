#!/bin/sh
# Runs automatically on first container init (docker-entrypoint-initdb.d),
# connected as the bootstrap superuser (POSTGRES_USER=postgres) against the
# univadmissions database. A .sh wrapper so the app role's password comes
# from UNIVADMISSIONS_DB_PASSWORD at container start (injected by Compose
# from deploy/.env), never baked into the image.
#
# ADR-02: the application connects as a dedicated NOSUPERUSER NOBYPASSRLS
# role that owns the public schema, never as the bootstrap superuser. This
# is the exact gap that silently defeated row-level security on a prior
# project (GeM/vrip7): connecting as superuser bypasses every RLS policy
# regardless of FORCE, with no error and no warning. POSTGRES_USER stays
# "postgres" specifically so it can never accidentally become the role the
# application itself connects as.
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
CREATE ROLE univadmissions LOGIN PASSWORD '$UNIVADMISSIONS_DB_PASSWORD' NOSUPERUSER NOBYPASSRLS;
ALTER SCHEMA public OWNER TO univadmissions;
GRANT ALL PRIVILEGES ON DATABASE $POSTGRES_DB TO univadmissions;
EOSQL
