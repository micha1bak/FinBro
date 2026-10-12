#!/bin/sh
# Uruchamiany przez obraz postgres tylko przy inicjalizacji pustego wolumenu.
# Tworzy osobną bazę dla testów integracyjnych na tym samym serwerze.
set -eu

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
	CREATE DATABASE finbro_test OWNER "$POSTGRES_USER";
EOSQL
