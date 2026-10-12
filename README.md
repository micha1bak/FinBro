# FinBro

Lokalna, jednoużytkownikowa aplikacja do podziału nieregularnych dochodów na koperty
(Życie, XTB, Obligacje, Wakacje), cotygodniowych rozliczeń z listą przelewów, ewidencji
należności i analizy przychodów oraz wydatków. Dane bankowe pochodzą z wyciągów XML
eksportowanych z iPKO.

Aplikacja działa wyłącznie na Twoim komputerze. Baza i aplikacja są osiągalne tylko
z `127.0.0.1`, a wyciągi bankowe nie są zapisywane na dysku ani w repozytorium.

## Wymagania

- Docker Desktop (z WSL2) z Docker Compose v2 lub nowszym.
- Do pracy deweloperskiej: Python 3.13.

## Uruchomienie w Dockerze

1. Skopiuj plik z ustawieniami i ustaw hasło bazy (tylko litery i cyfry) we wszystkich
   miejscach oznaczonych `WPISZ_HASLO`:

   ```bash
   cp .env.example .env
   ```

   W PowerShellu: `Copy-Item .env.example .env`. Plik `.env` nie trafia do repozytorium.

2. Zbuduj obraz i uruchom bazę oraz aplikację:

   ```bash
   docker compose up -d --build
   ```

   Najpierw startuje PostgreSQL. Gdy baza jest gotowa, aplikacja wykonuje migracje
   (`alembic upgrade head`): tworzy schemat, kategorie, reguły startowe i plan podziału
   50 / 12,5 / 12,5 / 25.

3. Otwórz <http://127.0.0.1:8000>. Stan usług sprawdzisz poleceniem `docker compose ps`
   (obie powinny być `healthy`), a połączenie z bazą adresem <http://127.0.0.1:8000/health>.

Dane są w nazwanym wolumenie Dockera `finbro-pgdata`. Polecenia `docker compose down`
i `docker compose up -d` ich nie usuwają.

> **Uwaga:** `docker compose down -v` oraz czyszczenie danych w Docker Desktop
> usuwają wolumen z bazą. Przed takimi operacjami zrób kopię zapasową (niżej).

### Aktualizacja aplikacji

```bash
git pull
docker compose up -d --build
```

Migracje wykonują się przy starcie, dane zostają w wolumenie.

## Pierwsza konfiguracja

W zakładce **Ustawienia** (<http://127.0.0.1:8000/admin>):

1. **Ustawienia**: data startu rozliczeń (dochody sprzed tej daty nie są dzielone, ale
   są widoczne w raportach) i numer konta głównego PKO (import sprawdza, czy wyciąg
   pochodzi z tego rachunku).
2. **Koperty**: numery rachunków docelowych dla XTB, Obligacji (rachunek rejestrowy)
   i Wakacji (Revolut).
3. **Plany podziału**: zmiana proporcji to nowy plan z datą obowiązywania. Starsze
   dochody są dzielone według planu obowiązującego w ich dniu.
4. **Reguły** i **Kategorie**: reguły startowe można edytować, a własne dodawać
   (np. refundacje budżetu rodzinnego od konkretnego nadawcy).

Stan początkowy gotówki ustawisz w widoku **Portfel**.

## Praca deweloperska w `.venv`

Aplikację i testy można uruchamiać lokalnie (np. w PyCharmie), korzystając z bazy
z `docker compose`. Zmienne `DATABASE_URL` i `TEST_DATABASE_URL` są wczytywane z `.env`.

```bash
python -m venv .venv
```

```bash
.venv/Scripts/python -m pip install -e ".[dev]"
```

```bash
docker compose up -d db
```

```bash
.venv/Scripts/alembic upgrade head
```

```bash
.venv/Scripts/uvicorn finbro.web.app:create_app --factory --reload --host 127.0.0.1 --port 8000
```

Jeśli aplikacja działa też w kontenerze, zatrzymaj ją wcześniej (`docker compose stop app`),
bo obie używają portu 8000.

### Testy

```bash
.venv/Scripts/python -m pytest
```

Testy domeny nie potrzebują bazy. Testy integracyjne korzystają z bazy `finbro_test`
na serwerze z `docker compose` (tworzy ją skrypt `docker/db-init` przy pierwszym
uruchomieniu wolumenu). Schemat powstaje migracjami na początku każdej sesji testów,
a każdy test działa w transakcji wycofywanej na końcu. Gdy baza nie działa, testy
kończą się komunikatem z poleceniem `docker compose up -d db`.

Testy w kontenerze (obraz z zależnościami deweloperskimi, usługa `tests`):

```bash
docker compose run --rm tests pytest
```

### Nowa migracja

```bash
.venv/Scripts/alembic revision --autogenerate -m "opis zmiany"
```

Sprawdź wygenerowany plik w `finbro/db/migrations/versions/`, a potem uruchom
`alembic check` (brak rozbieżności między modelami a migracjami).

## Kopia zapasowa i przywracanie

Kopię robimy narzędziem `pg_dump` wewnątrz kontenera i kopiujemy plik na hosta.
Nie przekierowuj wyjścia `pg_dump` operatorem `>` w PowerShellu: zmienia on kodowanie
strumienia i psuje binarny plik kopii. Katalog `backups/` jest wykluczony z repozytorium.

Kopia (polecenia działają w PowerShellu i w bashu):

```bash
docker compose exec db sh -c 'pg_dump -U $POSTGRES_USER -d $POSTGRES_DB -Fc -f /tmp/finbro.dump'
```

```bash
mkdir backups
```

```bash
docker compose cp db:/tmp/finbro.dump backups/finbro-2026-10-12.dump
```

```bash
docker compose exec db sh -c 'rm /tmp/finbro.dump'
```

Przywrócenie (zastępuje bieżące dane zawartością kopii):

```bash
docker compose stop app
```

```bash
docker compose cp backups/finbro-2026-10-12.dump db:/tmp/finbro.dump
```

```bash
docker compose exec db sh -c 'pg_restore -U $POSTGRES_USER -d $POSTGRES_DB --clean --if-exists --no-owner /tmp/finbro.dump'
```

```bash
docker compose exec db sh -c 'rm /tmp/finbro.dump'
```

```bash
docker compose start app
```

Przywrócenie na pustym wolumenie (np. na innym komputerze albo po utracie wolumenu)
przebiega tak samo: najpierw `docker compose up -d db` (utworzy pustą bazę), potem
kroki przywracania powyżej, na koniec `docker compose up -d`.

## Zmiana wersji głównej PostgreSQL

Wersja główna jest przypięta w `docker-compose.yml` (`image: postgres:18`). Nowa wersja
główna nie odczyta katalogu danych starej, dlatego zmiana przebiega przez kopię:

1. Zrób kopię zapasową (sekcja wyżej) i sprawdź, że plik ma niezerowy rozmiar.
2. Zatrzymaj usługi: `docker compose down` (bez `-v`).
3. W `docker-compose.yml` zmień obraz na nową wersję (np. `postgres:19`) oraz nazwę
   wolumenu w sekcji `volumes:` na nową (np. `name: finbro-pgdata-19`). Stary wolumen
   zostaje nietknięty i pozwala wrócić do poprzedniej wersji.
4. Uruchom bazę na nowym, pustym wolumenie: `docker compose up -d db`.
5. Przywróć kopię (kroki przywracania wyżej), potem uruchom wszystko: `docker compose up -d`.
6. Po sprawdzeniu danych w aplikacji możesz usunąć stary wolumen:
   `docker volume rm finbro-pgdata`.

Od PostgreSQL 18 obraz trzyma dane w `/var/lib/postgresql/<wersja>/docker`, dlatego
wolumen jest montowany w `/var/lib/postgresql`.

## Prywatność

- Wyciągi XML są przetwarzane z żądania HTTP i nie są zapisywane na dysku.
- `.gitignore` i `.dockerignore` wykluczają wyciągi (`*.xml`, `*.csv`, `*.xls*`),
  kopie bazy (`*.dump`, `backups/`) i plik `.env`. Fixture'y testowe w `tests/fixtures/`
  są syntetyczne.
- Porty bazy i aplikacji są publikowane wyłącznie na `127.0.0.1`.
