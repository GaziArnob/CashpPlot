#!/bin/sh
# Creates the application's database role. It must NOT be a superuser: superusers skip row-level security.
set -e
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<SQL
CREATE ROLE cashpilot LOGIN PASSWORD '${APP_DB_PASSWORD}';
CREATE DATABASE cashpilot OWNER cashpilot;
SQL
