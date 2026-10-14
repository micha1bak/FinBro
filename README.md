# FinBro

Lokalna, jednoużytkownikowa aplikacja zastępująca arkusz finansów osobistych:

- **Dochody**: wpisujesz datę, źródło i kwotę, a aplikacja dzieli każdy dochód na koperty
  PKO (Życie) 50%, Wakacje 25%, XTB 12,5% i Obligacje 12,5%. Wakacje, XTB i Obligacje są
  zaokrąglane do pełnych złotych, a resztę dostaje PKO.
- **Rozliczenie**: jedna lista przelewów (kwota, rachunek, tytuł do skopiowania) dla
  wszystkich nierozliczonych dochodów. Przycisk „Rozliczone” oznacza je wszystkie naraz,
  a najnowsze rozliczenie da się cofnąć.
- **Majątek**: salda PKO, XTB i Obligacji, ich suma i wykres w czasie. Salda XTB i Obligacji
  rosną same o rozliczone przelewy, a wpisane saldo faktyczne pokazuje zysk albo stratę.
  Saldo PKO wpisujesz ręcznie.
- **Ustawienia**: rachunki docelowe kopert i zmiana planu podziału od wybranej daty.

Aplikacja działa wyłącznie na Twoim komputerze. Baza i aplikacja są osiągalne tylko
z `127.0.0.1`.

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
   (`alembic upgrade head`): tworzy schemat i plan podziału 50 / 25 / 12,5 / 12,5.

3. Otwórz <http://127.0.0.1:8000>. Stan usług sprawdzisz poleceniem `docker compose ps`
   (obie powinny być `healthy`), a połączenie z bazą adresem <http://127.0.0.1:8000/health>.

Dane są w nazwanym wolumenie Dockera `finbro-pgdata`. Polecenia `docker compose down`
i `docker compose up -d` ich nie usuwają.

> **Uwaga:** `docker compose down -v` oraz czyszczenie danych w Docker Desktop
> usuwają wolumen z bazą. Przed takimi operacjami zrób kopię zapasową (niżej).

### Aktualizacja aplikacji

```bash
git pull
```

```bash
docker compose up -d --build
```

Migracje wykonują się przy starcie, dane zostają w wolumenie.

### Przejście z pierwszej wersji (jednorazowo)

Pierwsza wersja FinBro (import wyciągów, klasyfikacja wydatków) miała inny schemat bazy,
którego nowe migracje nie przejmują. Jeśli wolumen `finbro-pgdata` pochodzi z tamtej wersji,
aplikacja nie wystartuje (Alembic nie zna zapisanej rewizji). Wtedy usuń stary wolumen.
**To kasuje wszystkie dane z pierwszej wersji.**

```bash
docker compose down
```

```bash
docker volume rm finbro-pgdata
```

```bash
docker compose up -d --build
```

## Pierwsza konfiguracja

1. **Ustawienia**: wpisz rachunki docelowe Wakacji, XTB i Obligacji. Bez nich lista
   przelewów pokazuje kwoty z ostrzeżeniem o brakującym rachunku.
2. **Majątek**: wpisz salda początkowe PKO, XTB i Obligacji (stan po ostatnich wykonanych
   przelewach). Rozliczenie z tego samego dnia co saldo nie jest do niego doliczane.
3. **Dochody**: wpisuj kolejne dochody. Gdy wykonasz przelewy z widoku **Rozliczenie**,
   kliknij „Rozliczone”.

Zmiana proporcji to nowy plan z datą obowiązywania (w **Ustawieniach**). Zmienia podział
nierozliczonych dochodów od tej daty. Rozliczone dochody zachowują swój podział.

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

Testy domeny (podział, przelewy, salda) nie potrzebują bazy. Testy integracyjne korzystają z bazy `finbro_test`
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
docker compose cp db:/tmp/finbro.dump backups/finbro-2026-10-14.dump
```

```bash
docker compose exec db sh -c 'rm /tmp/finbro.dump'
```

Przywrócenie (zastępuje bieżące dane zawartością kopii):

```bash
docker compose stop app
```

```bash
docker compose cp backups/finbro-2026-10-14.dump db:/tmp/finbro.dump
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

- Dane (dochody, rachunki, salda) są tylko w bazie w wolumenie Dockera na Twoim komputerze.
- `.gitignore` i `.dockerignore` wykluczają wyciągi i arkusze (`*.xml`, `*.csv`, `*.xls*`),
  kopie bazy (`*.dump`, `backups/`) i plik `.env`. Testy używają wyłącznie zmyślonych kwot.
- Porty bazy i aplikacji są publikowane wyłącznie na `127.0.0.1`.
