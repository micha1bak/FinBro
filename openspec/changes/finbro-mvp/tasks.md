# Zadania

## 1. Szkielet projektu

- [x] 1.1 Utworzyć `pyproject.toml` z zależnościami (FastAPI, Uvicorn, SQLAlchemy 2.0, psycopg 3, Alembic, SQLAdmin, Jinja2, httpx, pytest), sprawdzając aktualne wersje, stan utrzymania SQLAdmin i aktualną stabilną wersję główną PostgreSQL do przypięcia w compose. Weryfikacja: `pip install -e .[dev]` w istniejącym `.venv` kończy się bez błędów.
- [x] 1.2 Utworzyć strukturę pakietów `finbro/{domain,importers,classification,llm,services,db,db/repositories,web}` i katalog `tests/`. Weryfikacja: `pytest` uruchamia się i zbiera 0 testów bez błędów importu.
- [x] 1.3 Dodać `.dockerignore` (`.venv`, `.git`, `.idea`, `.claude`, `openspec`, `backups/`, `.env`, `*.xml`, `*.csv`, `*.dump`, z wyjątkiem `tests/fixtures/`) i uzupełnić istniejący `.gitignore`, jeśli szkielet projektu wprowadzi nowe pliki lokalne. `.gitignore` wyklucza już dane finansowe (`*.xml`, `*.csv`, `*.xls*`, `*.dump`, `backups/`), sekrety (`.env*` poza `.env.example`) i artefakty Pythona, a dopuszcza `tests/fixtures/` i XML-e konfiguracji `.idea`. Weryfikacja: `git check-ignore` potwierdza, że `wyciag.xml`, `backups/a.dump` i `.env` są ignorowane, a `tests/fixtures/x.xml` i `.env.example` nie, oraz `docker build` nie kopiuje do obrazu plików `.env` ani wyciągów.
- [x] 1.4 Dodać konfigurację aplikacji ze zmiennych środowiskowych (`DATABASE_URL`, `OLLAMA_URL`, nazwa modelu), minimalną aplikację FastAPI ze stroną główną i endpointem `/health` sprawdzającym połączenie z bazą. Weryfikacja: testy z `TestClient` dostają 200 dla `/` i `/health` przy działającej bazie i 503 dla `/health` przy nieosiągalnej, a test konfiguracji sprawdza odczyt zmiennych i błąd przy braku `DATABASE_URL`.
- [x] 1.5 Dodać `docker-compose.yml` z usługą `db` według D13 (przypięta wersja główna `postgres`, port `127.0.0.1:5432:5432`, wolumen `finbro-pgdata`, healthcheck `pg_isready`, skrypt init tworzący bazę `finbro_test`) oraz `.env.example` z miejscem na hasło. Weryfikacja: po `docker compose up -d db` usługa jest healthy, z `.venv` da się połączyć z bazami `finbro` i `finbro_test`, a `docker compose port db 5432` zwraca `127.0.0.1:5432`.
- [x] 1.6 Dodać `Dockerfile` według D13 (`python:3.13-slim`, warstwa zależności, użytkownik bez roota, `HEALTHCHECK` na `/health`, start: `alembic upgrade head` + Uvicorn z `--host 0.0.0.0 --workers 1`) i usługę `app` w compose (port `127.0.0.1:8000:8000`, `DATABASE_URL`, `depends_on: db` z `service_healthy`). Weryfikacja: po `docker compose up -d --build` `curl http://127.0.0.1:8000/health` zwraca 200, obie usługi są healthy, a `docker compose port app 8000` zwraca `127.0.0.1:8000`.
- [x] 1.7 Umożliwić uruchamianie testów w kontenerze (zależności deweloperskie w osobnym etapie obrazu lub targetcie, `TEST_DATABASE_URL` wskazujący `finbro_test`). Weryfikacja: `docker compose run --rm app pytest` przechodzi z tym samym wynikiem co `pytest` w `.venv`.

## 2. Domena podstawowa: kwoty i tygodnie

- [ ] 2.1 Zaimplementować typ `Money` na groszach (`int`) z parsowaniem `"-645.00"`, `"+2753,36"` i `"1 234,56"` oraz formatowaniem po polsku. Weryfikacja: testy jednostkowe parsowania, formatowania, znaku i braku utraty dokładności.
- [ ] 2.2 Zaimplementować tygodnie ISO 8601 (tydzień dla daty, zakres pon–nd, poprzedni i następny, etykieta `2026-T41`), miesiące i lata jako okresy. Weryfikacja: testy dla 2026-10-10 → T41, 2026-10-31 → T44 i przełomu roku.
- [ ] 2.3 Zaimplementować podział sumy na koperty według udziałów w punktach bazowych, z zaokrągleniem w dół i resztą dla Życia. Weryfikacja: test 4950,03 zł → 618,75 / 618,75 / 1237,50 / 2475,03 oraz test własności "suma kopert = suma wejściowa" dla losowych kwot.

## 3. Baza danych i konfiguracja

- [ ] 3.1 Zdefiniować modele SQLAlchemy według D6 i konwencji z D11 (`BIGINT` dla kwot, `DATE`/`TIMESTAMPTZ`, `JSONB` dla warunków reguł, typy wyliczeniowe jako `VARCHAR` + `CHECK`, `naming_convention` dla ograniczeń, unikalne ograniczenie odcisku importu z `occurrence`). Weryfikacja: `alembic upgrade head` tworzy schemat na pustej bazie PostgreSQL, `alembic downgrade base` go usuwa, a `alembic check` nie wykrywa rozbieżności między modelami a migracjami.
- [ ] 3.2 Dodać fixture'y testowe pytest dla bazy według D11: schemat w `finbro_test` tworzony migracjami raz na sesję, każdy test w transakcji wycofywanej na końcu i czytelny błąd z instrukcją `docker compose up -d db`, gdy baza jest nieosiągalna. Weryfikacja: dwa testy zapisujące ten sam wiersz przechodzą niezależnie od kolejności (izolacja), a uruchomienie bez bazy kończy się komunikatem z instrukcją.
- [ ] 3.3 Dodać warstwę repozytoriów (`db/repositories`) i serwisów (`services/`) według D2. Repozytoria zwracają dataclassy domenowe, a routery nie wykonują zapytań. Weryfikacja: testy integracyjne repozytoriów (zapis i odczyt transakcji, klasyfikacji, rozliczenia) oraz test architektury sprawdzający, że moduły `finbro.web` (poza konfiguracją SQLAdmin) i `finbro.domain` nie importują `sqlalchemy`.
- [ ] 3.4 Dodać migrację danych początkowych: konta (PKO, Portfel), 13 kategorii + systemowa "Gotówka (bez kategorii)", koperty z planem 50/12,5/12,5/25 i reguły startowe z D14. Weryfikacja: test po migracji sprawdza obecność kategorii, planu sumującego się do 100% i reguł.
- [ ] 3.5 Podłączyć SQLAdmin dla kategorii, reguł, dłużników, kopert (rachunki docelowe), planów podziału (z walidacją sumy 100%) i ustawień (data startu, numer konta głównego, model LLM). Kategoria systemowa ma być nieedytowalna. Weryfikacja: testy zapisu planu 95% (odrzucony) i 100% (przyjęty) oraz próby edycji kategorii systemowej (odrzucona).
- [ ] 3.6 Opisać w `README.md` uruchomienie przez `docker compose` (z `.env`), pracę deweloperską w `.venv` z bazą z compose (instalacja, migracje, testy), konfigurację pierwszego startu, kopię zapasową i przywracanie (`pg_dump -Fc` w kontenerze + `docker compose cp`, `pg_restore --clean`) oraz procedurę zmiany wersji głównej PostgreSQL. Weryfikacja: kroki z README wykonane na czystym klonie uruchamiają aplikację w Dockerze, a kopia odtworzona na pustym wolumenie zawiera te same dane.

## 4. Import wyciągów XML z iPKO

- [ ] 4.1 Przygotować syntetyczne fixture'y XML odwzorowujące strukturę iPKO: przelew przychodzący, płatność kartą zaksięgowana później, BLIK wychodzący o mylącym typie, bankomat, "Przelew z karty" Revolut, dwie identyczne płatności tego samego dnia, operacja bez `exec-date`, nieznana etykieta. Wszystkie dane zmyślone. Weryfikacja: pliki są w `tests/fixtures/` i nie zawierają danych z prawdziwego wyciągu.
- [ ] 4.2 Zaimplementować parser `importers/pko_xml.py`: daty, kwota i saldo, numer rachunku z `search`, rozbicie opisu po znanych etykietach (D4), zachowanie surowego opisu, kierunek ze znaku kwoty. Weryfikacja: testy jednostkowe na fixture'ach dla każdego scenariusza ze spec `transaction-import`.
- [ ] 4.3 Zaimplementować zapis importu: weryfikację rachunku, pomijanie blokad, deduplikację po odcisku z numerem wystąpienia w obrębie pliku (`INSERT ... ON CONFLICT DO NOTHING`), atomowość i `ImportBatch` z licznikami. Weryfikacja: testy integracyjne na bazie testowej dla nakładających się importów, identycznych płatności, złego rachunku i uszkodzonego pliku (zero zapisanych transakcji).
- [ ] 4.4 Zaimplementować wyliczanie pokrycia okresów importami i luk od daty startu. Weryfikacja: test dla importów 05–11.10 i 19–25.10 wskazuje lukę 12–18.10.
- [ ] 4.5 Dodać widok importu (upload pliku, podsumowanie, lista luk w pokryciu). Weryfikacja: test `TestClient` przesyła fixture i otrzymuje stronę z liczbami nowych, istniejących i pominiętych operacji.

## 5. Klasyfikacja: typy, kategorie, reguły, historia, skrzynka

- [ ] 5.1 Zaimplementować w domenie typy transakcji z dozwolonymi kierunkami i wymaganiami (kategoria dla WYDATEK/ZWROT/ROZLICZENIE, dłużnik dla POŻYCZKA/SPŁATA). Weryfikacja: testy odrzucenia DOCHODU dla wydatku i braku kategorii dla WYDATKU.
- [ ] 5.2 Zaimplementować silnik reguł (warunki: kierunek, typ banku, kontrahent, rachunek, tytuł, sprzedawca, zakres kwot; priorytet; pierwsza pasująca wygrywa). Weryfikacja: testy jednostkowe reguł startowych na operacjach z fixture'ów (bankomat → TRANSFER Portfela, Revolut kartą → TRANSFER budżet, tytuł FinBro → ODKŁADANIE).
- [ ] 5.3 Zaimplementować podpowiedź z historii kontrahenta (D9, krok 2). Weryfikacja: test, w którym druga płatność u tego samego sprzedawcy dostaje kategorię z pierwszej zatwierdzonej.
- [ ] 5.4 Zaimplementować potok po imporcie: reguły → historia → `LlmJob`, z regułami akceptacji z D9 (DOCHÓD zawsze niezatwierdzony, wydatki przyjmowane automatycznie, neutralne wpływy z reguł przyjmowane automatycznie). Weryfikacja: test integracyjny importu fixture'a sprawdza statusy `confirmed` i źródła propozycji dla każdej transakcji oraz to, że żadna transakcja z reguł nie trafiła do kolejki LLM.
- [ ] 5.5 Zbudować skrzynkę (HTMX): lista pozycji z propozycją, źródłem i uzasadnieniem, przyjęcie jednym kliknięciem, zmiana typu, kategorii lub dłużnika, opcja "zapamiętaj jako regułę", zbiorcze zatwierdzenie dochodów z reguł. Weryfikacja: testy `TestClient` dla przyjęcia, zmiany i utworzenia reguły, po których kolejny import tego kontrahenta dostaje propozycję z reguły.
- [ ] 5.6 Dodać listę transakcji z filtrem i możliwością zmiany klasyfikacji dowolnej transakcji. Weryfikacja: test zmiany kategorii wydatku widocznej w odpowiedzi listy.

## 6. Portfel gotówkowy

- [ ] 6.1 Zaimplementować wyliczanie oczekiwanego stanu Portfela (stan początkowy, dochody i wydatki gotówkowe, transfery z bankomatu i do wpłatomatu, pożyczki i spłaty gotówkowe, inwentaryzacje). Weryfikacja: testy jednostkowe dla każdego rodzaju zdarzenia.
- [ ] 6.2 Dodać formularze: stan początkowy, dochód gotówkowy (od razu zatwierdzony DOCHÓD), wydatek gotówkowy z kategorią. Weryfikacja: testy `TestClient` sprawdzają zmianę stanu oczekiwanego i obecność dochodu jako zatwierdzonego.
- [ ] 6.3 Zaimplementować inwentaryzację: niedobór → wydatek "Gotówka (bez kategorii)" na dzień inwentaryzacji, nadwyżka → pozycja w skrzynce (dochód gotówkowy albo korekta), stan zgodny → brak wpisu. Weryfikacja: testy trzech przypadków ze spec `cash-wallet` (900 → 340 daje wydatek 560,00 zł).

## 7. Należności

- [ ] 7.1 Zaimplementować w domenie saldo dłużnika, spłaty częściowe, odrzucenie spłaty większej niż saldo, darowanie (generujące WYDATEK w wybranej kategorii) i datę najstarszej niespłaconej pożyczki (spłaty rozliczane od najstarszych). Weryfikacja: testy jednostkowe scenariuszy ze spec `receivables`.
- [ ] 7.2 Połączyć należności z klasyfikacją (POŻYCZKA/SPŁATA z dłużnikiem, podpowiedź spłaty dla wpływu od dłużnika) i z Portfelem (pożyczki i spłaty gotówkowe). Weryfikacja: test integracyjny, w którym wpływ od osoby z saldem 1290,00 zł pokazuje w skrzynce propozycję SPŁATY z saldem.
- [ ] 7.3 Dodać widok należności (lista dłużników z saldem i datą najstarszej pożyczki, suma, historia dłużnika, akcja "daruj"). Weryfikacja: test `TestClient` dla sumy 1440,00 zł i darowania zmieniającego saldo na 0,00 zł.

## 8. Lokalny model językowy

- [ ] 8.0 Dodać do `docker-compose.yml` usługę `ollama` (obraz `ollama/ollama`, profil `llm`, wolumen `ollama-models`, bez publikowania portu na hoście). Weryfikacja: `docker compose --profile llm up -d` uruchamia obie usługi, z kontenera `app` odpowiada `http://ollama:11434/api/tags`, a `docker compose up -d` bez profilu uruchamia tylko bazę i aplikację.
- [ ] 8.1 Spike: uruchomić Ollamę z profilu `llm`, wybrać 2–4 modele (m.in. Bielik i mały model ogólny), przygotować syntetyczny zestaw ~30 transakcji z oczekiwaną klasyfikacją, zmierzyć czas na transakcję, zużycie pamięci (limit WSL2 ~8 GB) i trafność typu oraz kategorii na sprzęcie użytkownika. Weryfikacja: wyniki i rekomendacja modelu zapisane w `docs/llm-spike.md`, a nazwa modelu ustawiona jako domyślna w konfiguracji.
- [ ] 8.2 Zaimplementować budowanie widoku transakcji dla modelu z minimalizacją danych (D10): bez numerów rachunków, telefonów, kart i sald, z wycięciem takich ciągów z tytułu. Weryfikacja: test jednostkowy na opisie z numerem rachunku i telefonu sprawdza ich brak w wyniku.
- [ ] 8.3 Zaimplementować klasyfikator Ollama z odpowiedzią według schematu JSON (enumy typów, aktywnych kategorii i dłużników) i odrzucaniem wartości spoza schematu. Weryfikacja: testy z atrapą HTTP dla odpowiedzi poprawnej, spoza enumów i błędu serwera (wynik: brak propozycji).
- [ ] 8.4 Zaimplementować worker w tle przetwarzający `LlmJob` sekwencyjnie, z ponawianiem i odpornością na restart, oraz odświeżanie skrzynki przez HTMX, gdy kolejka nie jest pusta. Weryfikacja: test integracyjny z atrapą klasyfikatora, w którym import kończy się od razu, a propozycje pojawiają się po przetworzeniu kolejki. Test z wyłączoną Ollamą: pozycje w skrzynce bez propozycji, brak błędów aplikacji.
- [ ] 8.5 Opisać w README uruchomienie profilu `llm`, pobranie modelu (`docker compose exec ollama ollama pull ...`), działanie bez LLM i alternatywę z natywną Ollamą (`OLLAMA_URL=http://host.docker.internal:11434`). Weryfikacja: kroki z README dają działającą klasyfikację na fixture'ach.

## 9. Rozliczenie tygodniowe

- [ ] 9.1 Zaimplementować przypisanie `settlement_week` przy zatwierdzaniu dochodu i korekty przy zatwierdzeniu lub przeklasyfikowaniu dochodu z zamkniętego tygodnia, z pominięciem dochodów sprzed daty startu (D7). Weryfikacja: testy "późno zatwierdzony dochód 1000 zł → korekta w T42" i "wycofanie dochodu 400 zł → ujemna korekta".
- [ ] 9.2 Zaimplementować wyliczenie rozliczenia: suma dochodów tygodnia (bankowych i gotówkowych), plan obowiązujący w dniu dochodu, osobne zaokrąglanie grup, korekty, przeniesienia z poprzedniego tygodnia, kwoty ujemne przechodzące dalej. Weryfikacja: testy jednostkowe scenariuszy ze spec `weekly-settlement` (podział z zaokrągleniem, niedopłata +37,50 zł, nadpłata -81,25 zł, zmiana proporcji).
- [ ] 9.3 Zaimplementować zamknięcie rozliczenia (tylko po zakończeniu tygodnia, zamrożenie linii, jedna transakcja z blokadą `FOR UPDATE` według D7) i ostrzeżenia przed zamknięciem (pokrycie importów, niezatwierdzone wpływy z tygodnia, brak inwentaryzacji). Weryfikacja: testy blokady zamknięcia trwającego tygodnia i obecności każdego z trzech ostrzeżeń.
- [ ] 9.4 Zaimplementować dopasowanie przelewów: tytuł `FinBro <rok>-T<nr> <koperta>` (odporny na wielkość liter, spacje i polskie znaki) oraz fallback po rachunku docelowym do najstarszej niedopłaty. Klasyfikacja jako ODKŁADANIE, statusy zamknięte i rozliczone. Weryfikacja: testy dopasowania z tytułem, bez tytułu i z podwójnymi spacjami oraz test zmiany statusu na rozliczone.
- [ ] 9.5 Dodać widok rozliczenia: wybór tygodnia (domyślnie poprzedni), ostrzeżenia, zamknięcie, lista przelewów z rachunkiem, kwotą i tytułem do skopiowania, statusy linii. Weryfikacja: test `TestClient` zamknięcia T41 pokazuje trzy przelewy z tytułem "FinBro 2026-T41 Wakacje" dla Wakacji.

## 10. Raporty

- [ ] 10.1 Zaimplementować w domenie agregacje przychodów i wydatków według definicji ze spec `financial-reporting` (typy neutralne wykluczone, ZWROT i ROZLICZENIE pomniejszają kategorię, darowania i różnice inwentaryzacji wliczone, data transakcji jako wiążąca). Weryfikacja: testy jednostkowe scenariuszy "refundacja i spłata nie są przychodem", "odkładanie nie jest wydatkiem" i "rozliczenie wspólnego wydatku".
- [ ] 10.2 Zaimplementować podziały na kategorie (kwota i udział %) i ranking sprzedawców oraz kontrahentów, a także informację o pozycjach niezatwierdzonych lub nieskategoryzowanych w okresie. Weryfikacja: testy dla 150/50 zł → 75%/25% i dla komunikatu o 1 niezatwierdzonej pozycji na 477,08 zł.
- [ ] 10.3 Dodać widok raportów: przełącznik tydzień, miesiąc lub rok, nawigacja między okresami, podsumowanie (przychody, wydatki, bilans), wykres trendu (Chart.js), tabela kategorii i ranking sprzedawców. Weryfikacja: test `TestClient` zwraca poprawne sumy dla danych testowych, a ręczne sprawdzenie w przeglądarce pokazuje wykres.

## 11. Integracja end-to-end

- [ ] 11.1 Test end-to-end poniedziałkowego rozliczenia na danych syntetycznych: import → zatwierdzenie dochodów w skrzynce → dochód gotówkowy i inwentaryzacja → zamknięcie tygodnia → import kolejnego tygodnia z przelewami FinBro → status rozliczone. Weryfikacja: test przechodzi, a raport tygodniowy pokazuje oczekiwane przychody i wydatki.
- [ ] 11.2 Ręczna próba na prawdziwym eksporcie XML użytkownika (poza repozytorium) w aplikacji uruchomionej przez `docker compose`: import, sprawdzenie parsowania opisów i deduplikacji przy ponownym imporcie. Weryfikacja: użytkownik potwierdza poprawność transakcji, a drugi import tego samego pliku daje 0 nowych.
- [ ] 11.3 Sprawdzić trwałość danych w Dockerze: import i zamknięcie rozliczenia, potem `docker compose down` i `docker compose up -d`, potem przebudowa obrazu (`--build`), na koniec kopia `pg_dump` odtworzona na nowym wolumenie. Weryfikacja: po każdym kroku transakcje i rozliczenie są na miejscu, a migracje przy starcie nie zgłaszają błędów.

## Workflow follow-up

- Po wdrożeniu i akceptacji użytkownika zarchiwizować zmianę (`/opsx:archive`), co utworzy główne specyfikacje w `openspec/specs/`.
