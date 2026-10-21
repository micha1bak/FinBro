#!/bin/sh
# Tworzy na tym samym serwerze osobne bazy: finbro_dev dla aplikacji uruchamianej z .venv
# i finbro_test dla testów integracyjnych, żeby nie dotykały danych z bazy finbro.
# Obraz postgres uruchamia go sam tylko przy inicjalizacji pustego wolumenu, a na istniejącym
# wolumenie robi to `poe db`. Bazy, które już istnieją, zostają bez zmian.
set -eu

for db in finbro_dev finbro_test; do
	psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -v db="$db" <<-'EOSQL'
		SELECT format('CREATE DATABASE %I OWNER %I', :'db', current_user)
		WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = :'db')\gexec
	EOSQL
done
