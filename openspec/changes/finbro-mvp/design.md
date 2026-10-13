# Design

## Kontekst

Projekt startuje od zera. W repozytorium są tylko puste `.venv` (Python 3.13.1) i konfiguracja OpenSpec. Motywację opisuje proposal.md, a wymagania specyfikacje w `specs/`.

Ograniczenia, które kształtują rozwiązanie:

- **Jeden użytkownik, lokalnie.** Aplikacja działa na laptopie użytkownika (Windows 11, 16 GB RAM, Ryzen 5 7520U, zintegrowane GPU bez wsparcia dla akceleracji modeli).
- **Brak API banków.** Jedynym źródłem danych bankowych jest ręczny eksport XML z iPKO. Analiza próbnego eksportu wykazała:
  - `order-date` to data transakcji, `exec-date` to data księgowania.
  - Eksport filtruje zakres po dacie transakcji.
  - Opis to jeden ciąg par `Etykieta : wartość`.
  - Brak ID transakcji, ale jest `ending-balance` (saldo po operacji).
  - Nazwa typu operacji bywa myląca co do kierunku.
  - Doładowania Revoluta mają postać "Przelew z karty" z lokalizacją "Revolut".
  - CSV z tego samego eksportu jest gorszy: mylące nazwy kolumn dat, brak numeru rachunku, problemy z kodowaniem po edycji.
- **Model językowy wyłącznie lokalny**, inferencja na CPU, więc wolno.
- **Uruchamianie w Dockerze.** Docker Desktop 29.8 z Compose v5.5 jest zainstalowany. Kontenery działają w maszynie WSL2, która bez pliku `.wslconfig` (brak u użytkownika) dostaje domyślnie około połowy RAM, czyli ~8 GB.
- **Baza danych: PostgreSQL.** To decyzja użytkownika. SQLite nie jest używany w żadnym trybie, także w testach.

## Cele / Poza zakresem

**Cele:**
- Logika domenowa (podział, przeniesienia, salda, klasyfikacja regułami, parser) w czystym Pythonie, testowalna bez serwera i bazy.
- Dostęp do danych zamknięty w jednej warstwie (repozytoria), tak żeby routery i domena nie zależały od szczegółów bazy.
- Poprawność kwot co do grosza w całym systemie.
- Odporność na ponowne importy i spóźnione dane: wynik zależy od zbioru transakcji, nie od kolejności importów.
- Aplikacja w pełni używalna bez modelu językowego.

**Poza zakresem (projektowo):**
- Logowanie i uwierzytelnianie aplikacji. Aplikacja jest osiągalna tylko z `127.0.0.1` hosta.
- Wielu użytkowników, synchronizacja między urządzeniami, praca na serwerze.
- Dzielenie jednej transakcji na kilka części o różnych typach.
- Obsługa innych baz niż PostgreSQL (w tym SQLite).

## Decyzje

### D1. Stos: FastAPI + SQLAlchemy 2.0 + Alembic + PostgreSQL + SQLAdmin + Jinja2/HTMX + Chart.js
Użytkownik najlepiej zna FastAPI. Główny argument za Django, czyli darmowy panel admina do CRUD-u reguł, kategorii, proporcji, dłużników i rachunków, zastępuje SQLAdmin. Własne widoki powstają tylko dla przepływów: import, skrzynka, rozliczenie, inwentaryzacja, należności i raporty. HTMX daje akcje jednym kliknięciem (np. zatwierdzenie w skrzynce) bez osobnej aplikacji SPA. Sterownik bazy to psycopg 3 (`postgresql+psycopg://`).
- *Alternatywy:* Django ma najwięcej rzeczy wbudowanych, ale użytkownik go nie zna. Streamlit jest świetny do wykresów, ale nie nadaje się do przepływów decyzyjnych, bo przelicza całą stronę przy każdej akcji.
- Wersje bibliotek, wersję PostgreSQL i aktywność rozwoju SQLAdmin weryfikujemy przy zakładaniu projektu (zadanie 1.1).

### D2. Warstwy kodu
```
web/ (routery, szablony)  -->  services/ (przypadki użycia)  -->  db/repositories  -->  SQLAlchemy  -->  PostgreSQL
                                     |
                                     v
                               domain/ (czysty Python, dataclassy)
```
```
finbro/
  domain/          kwoty, tygodnie ISO, podział, rozliczenie, należności, silnik reguł  (czysty Python)
  importers/       pko_xml.py: XML -> lista operacji domenowych                         (czysty Python)
  classification/  potok: reguły -> historia -> kolejka LLM
  llm/             interfejs klasyfikatora + implementacja przez API zgodne z OpenAI
  services/        przypadki użycia: import, zatwierdzenie, zamknięcie rozliczenia, inwentaryzacja, ...
  db/              modele SQLAlchemy, repositories/, migracje Alembic
  web/             FastAPI: routery, szablony Jinja2, SQLAdmin, worker w tle
```
- `domain` i `importers` nie importują niczego z `db`, `services` ani `web`. Testy jednostkowe obejmują je w całości.
- **Zapytania do bazy wykonują wyłącznie repozytoria w `db/repositories`.** Routery wołają serwisy, serwisy wołają repozytoria i domenę. Repozytoria przekazują domenie zwykłe obiekty (dataclassy), a nie encje ORM. Wyjątkiem jest SQLAdmin, który z definicji działa bezpośrednio na modelach.
- Repozytoria to konkretne klasy, bez abstrakcyjnych interfejsów (`Protocol`) dla każdego z nich. Granica w jednym katalogu wystarcza do ewentualnej wymiany warstwy danych, a domenę i tak testujemy bez bazy.

### D3. Kwoty jako liczby całkowite w groszach
W bazie `BIGINT` (grosze), w domenie typ `Money` oparty na `int` z konwersją z i do tekstu (`"-645.00"`, `"1 234,56"`). Nigdy `float`. Udziały procentowe zapisujemy w punktach bazowych (12,5% = 1250), żeby dzielenie też odbywało się na liczbach całkowitych. Zaokrąglenie w dół do grosza robimy przez dzielenie całkowite.
- *Alternatywa:* `NUMERIC(14,2)` + `Decimal`. PostgreSQL obsługuje to poprawnie, ale grosze w `int` są prostsze w domenie, a arytmetyka i zaokrąglenia działają tak samo w całym kodzie.

### D4. Format importu: XML z iPKO
XML ma jednoznaczne pola dat, numer rachunku w sekcji `search`, kwoty z kropką i poprawne UTF-8. CSV i HTML odrzucamy (patrz Kontekst).
- Opis rozbijamy przez wyszukanie znanych etykiet (`Rachunek nadawcy`, `Rachunek odbiorcy`, `Nazwa nadawcy`, `Nazwa odbiorcy`, `Adres nadawcy`, `Tytuł`, `Lokalizacja`, `Adres`, `Miasto`, `Kraj`, `Numer referencyjny`, `Numer telefonu`, `Numer karty`, `Data wykonania operacji`, `Oryginalna kwota operacji`) wzorcem `<etykieta>\s*:`. Wartość to tekst do następnej znanej etykiety. Tekst przed pierwszą etykietą traktujemy jako identyfikator operacji kartowej.
- Surowy `description` i `type` zapisujemy zawsze.
- Weryfikacja rachunku porównuje widoczne cyfry z początku i końca (eksport może maskować środek numeru).

### D5. Deduplikacja: unikalny odcisk `(rachunek, exec-date, amount, ending-balance, occurrence)`
Unikalne ograniczenie w bazie. `occurrence` to numer wystąpienia tego samego odcisku w obrębie jednego pliku (patrz Ryzyka). Import wstawia wiersze przez `INSERT ... ON CONFLICT DO NOTHING` i liczy, ile faktycznie przybyło. Dzięki temu deduplikacja jest poprawna nawet przy równoległych żądaniach. Saldo po operacji odróżnia identyczne płatności tego samego dnia.
- *Alternatywa:* hash surowego opisu. Odrzucona, bo bank potrafi zmienić formatowanie opisu między eksportami, co dałoby duplikaty.

### D6. Model danych (zarys)
- `Account`: konto główne PKO, Portfel. Rachunki docelowe kopert trzymamy w `Envelope`.
- `Transaction`: konto, źródło (import / ręczny wpis / inwentaryzacja / darowanie), data transakcji (`DATE`), data księgowania (`DATE`), kwota ze znakiem (`BIGINT`), typ banku, surowy opis, pola wyodrębnione, odcisk (dla importu).
- `Classification` (1:1 z `Transaction`): typ, kategoria, dłużnik, źródło propozycji (reguła / historia / LLM / użytkownik), uzasadnienie, `confirmed`, `settlement_week` (dla dochodów: tydzień, w którym dochód jest dzielony).
- `Category`, `Rule` (warunki w kolumnie `JSONB`, wynik, priorytet, aktywna), `Debtor`.
- `AllocationPlan` (`effective_from`) + `AllocationShare` (koperta, punkty bazowe), `Envelope` (nazwa, rachunek docelowy, czy jest Życiem).
- `Settlement` (rok, tydzień ISO, status) + `SettlementLine` (koperta, należność tygodnia, korekty, przeniesienie, kwota do przelania), `SettlementPayment` (powiązanie transakcji ODKŁADANIE z linią).
- `WalletInventory` (data, stan faktyczny, stan oczekiwany, wygenerowana transakcja).
- `ImportBatch` (plik, zakres dat, liczniki) do pokrycia okresów i podsumowań.
- `LlmJob` (transakcja, status, próby, błąd), czyli kolejka zadań dla klasyfikatora.
- `Settings`: data startu, numer konta głównego, nazwa modelu (adres serwera modelu pochodzi wyłącznie ze zmiennej `LLM_URL`).

### D7. Rozliczenie: zamrażanie wyników i korekty przez `settlement_week`
Przy zatwierdzeniu dochodu ustawiamy `settlement_week` = tydzień jego daty, jeśli rozliczenie tego tygodnia nie jest zamknięte. W przeciwnym razie ustawiamy najbliższy niezamknięty tydzień (korekta). Przeklasyfikowanie dochodu z zamkniętego tygodnia tworzy ujemną pozycję korekty w najbliższym niezamkniętym tygodniu.

Przy zamknięciu `SettlementLine` zapisuje wyliczone kwoty, które od tej chwili są niezmienne. Przeniesienie dla tygodnia N to `kwota_do_przelania(N-1) - suma_płatności(N-1)` dla danej koperty. Zamknięcie rozliczenia i przypisanie korekt odbywają się w jednej transakcji bazodanowej, z blokadą wiersza rozliczenia (`SELECT ... FOR UPDATE`), żeby równoległe zatwierdzenie dochodu nie trafiło do tygodnia, który właśnie się zamyka.

Korekty dzielimy według planu obowiązującego w dniu danego dochodu. Każda grupa (tydzień właściwy oraz każda korekta z innym planem) jest zaokrąglana osobno, a reszta trafia do Życia. Dzięki temu suma kopert zawsze równa się sumie dochodów.

- *Alternatywa:* przeliczanie wszystkiego od zera przy każdym wyświetleniu. Odrzucona, bo zamknięte rozliczenie, na podstawie którego użytkownik już zrobił przelewy, musi być stabilne.

### D8. Tytuły przelewów i dopasowanie
Format `FinBro 2026-T41 Wakacje`. Rok jest w tytule, żeby tytuły nie kolidowały na przełomie lat. Dopasowanie robimy wyrażeniem regularnym odpornym na wielkość liter i wielokrotne spacje (bank potrafi je wstawiać): `FinBro\s+(\d{4})-T(\d{1,2})\s+(\S+)`. Nazwę koperty porównujemy bez polskich znaków i wielkości liter. Fallback: przelew na rachunek docelowy koperty (porównanie numeru bez spacji) jest przypisywany do najstarszej linii z niedopłatą.

### D9. Potok klasyfikacji i worker LLM
Po imporcie, synchronicznie:
1. Reguły według priorytetu (pierwsza pasująca wygrywa).
2. Historia: ostatnia potwierdzona transakcja z tym samym rachunkiem kontrahenta, a gdy go brak, z tą samą znormalizowaną nazwą kontrahenta lub sprzedawcy, w tym samym kierunku.
3. Pozostałe transakcje trafiają jako `LlmJob` do kolejki.

Worker LLM to jeden wątek w tle uruchamiany przy starcie aplikacji. Przetwarza zadania sekwencyjnie (CPU i tak nie pozwoli na więcej). Zadanie pobiera przez `SELECT ... FOR UPDATE SKIP LOCKED`, więc kolejka pozostaje poprawna nawet przy przypadkowym drugim workerze. Kolejka jest w bazie, więc zadania przetrwają restart. Skrzynka odświeża się przez HTMX (polling co kilka sekund, gdy kolejka nie jest pusta).
- *Alternatywa:* Celery lub RQ. Odrzucone, bo to zbędna infrastruktura (broker) dla jednego użytkownika.

Reguły akceptacji (spec `transaction-classification`):
- wydatki są przyjmowane automatycznie z każdego źródła;
- wpływy z reguły o typie neutralnym są przyjmowane automatycznie;
- DOCHÓD zawsze wymaga zatwierdzenia;
- inne wpływy z historii lub od LLM wymagają zatwierdzenia.

### D10. Klasyfikator LLM: API zgodne z OpenAI, odpowiedź według schematu JSON
Interfejs `Classifier.classify(tx_view, context) -> Suggestion | None`. Implementacja wywołuje `POST {LLM_URL}/chat/completions` (API zgodne z OpenAI) pod konfigurowalnym adresem: domyślnie Docker Model Runner (z kontenera `http://model-runner.docker.internal/engines/v1`, z hosta `http://127.0.0.1:12434/engines/v1`). Odpowiedź jest ograniczona parametrem `response_format` typu `json_schema`, gdzie typ, kategoria i dłużnik są enumami z dozwolonych wartości. Tryb rozumowania modelu wyłączamy (`chat_template_kwargs.enable_thinking = false`), bo bez niego odpowiedź przychodzi kilkukrotnie szybciej. Ten sam klient działa z Ollamą (`http://<host>:11434/v1`). Sprawdziliśmy, że API Docker Model Runner w stylu Ollamy (`/api/chat`) ignoruje schemat w polu `format`, a endpoint zgodny z OpenAI go przestrzega. Odpowiedź spoza dozwolonych wartości traktujemy jak brak propozycji.

`tx_view` budujemy wyłącznie z dozwolonych pól (spec "Minimalizacja danych"). Z tytułu dodatkowo wycinamy ciągi cyfr wyglądające na numery telefonów, rachunków i kart. Prompt jest krótki, ze stałym prefiksem (kategorie, dłużnicy, kilka przykładów z historii), co pozwala korzystać z cache'u prefiksu po stronie serwera modelu.
- Model wybraliśmy w spike'u (zadanie 8.1, `docs/llm-spike.md`): `ai/gemma4:E2B` na CPU, około 16 s na transakcję, trafny typ w 90–93% i kategoria w około 80% przypadków syntetycznego zestawu.

### D11. PostgreSQL: konfiguracja i konwencje
- **Wersja:** oficjalny obraz `postgres` z przypiętą wersją główną (aktualna stabilna, weryfikowana w zadaniu 1.1). Zmiana wersji głównej wymaga dump/restore, więc przypinamy ją jawnie, a nie używamy `latest`.
- **Połączenie:** jedna zmienna `DATABASE_URL` (`postgresql+psycopg://finbro:<hasło>@db:5432/finbro`). Hasło trafia do `.env` (ignorowanego przez git). `.env.example` zawiera tylko miejsce na hasło.
- **Typy wyliczeniowe** (typ transakcji, status rozliczenia, źródło propozycji) jako `VARCHAR` z ograniczeniem `CHECK` (`native_enum=False`), a nie natywny `ENUM` PostgreSQL. Dodanie wartości do natywnego enuma wymaga osobnych, nietransakcyjnych migracji, a `CHECK` zmienia się zwykłą migracją.
- **Nazewnictwo ograniczeń:** `MetaData(naming_convention=...)`, żeby Alembic generował przewidywalne nazwy indeksów i kluczy, a migracje dało się odwracać.
- **Daty:** daty transakcji jako `DATE`, znaczniki czasu (import, zatwierdzenie) jako `TIMESTAMPTZ`.
- **Agregacje raportów:** grupowanie po tygodniu ISO, miesiącu i roku może korzystać z funkcji PostgreSQL (`date_trunc`, `extract(isoyear/week)`) w repozytorium raportów. Domena definiuje, które typy wchodzą do przychodów i wydatków, a repozytorium tylko sumuje.
- **Testy:** testy domeny nie potrzebują bazy. Testy integracyjne działają na prawdziwym PostgreSQL, w osobnej bazie `finbro_test` na tym samym serwerze, który uruchamia `docker compose`. Fixture sesji tworzy schemat migracjami Alembic (co przy okazji testuje migracje), a każdy test działa w transakcji wycofywanej na końcu. Brak dostępnej bazy testowej to czytelny błąd z instrukcją `docker compose up -d db`, a nie ciche pominięcie testów.
  - *Alternatywa:* testcontainers (świeży kontener na sesję testów). Odrzucona, bo dokłada zależność i kilkanaście sekund startu każdej sesji, a baza z compose i tak jest uruchomiona podczas pracy.
  - *Alternatywa:* SQLite w testach. Odrzucona, bo testy przechodziłyby na innej bazie niż produkcyjna (inne typowanie, brak `ON CONFLICT`/`FOR UPDATE` w tej samej postaci).

### D12. Przechowywanie danych i prywatność
Dane leżą w PostgreSQL, w nazwanym wolumenie Dockera `finbro-pgdata` (system plików WSL2, nie katalog montowany z NTFS). Przesyłane wyciągi XML są przetwarzane z żądania HTTP i nie są zapisywane na dysku. `.gitignore` wyklucza `*.xml`, `*.csv`, `*.dump`, `.env` i katalog `backups/`. Fixture'y testowe są syntetyczne i nie pochodzą z prawdziwych wyciągów. Aplikacja i baza są osiągalne wyłącznie z loopbacku hosta.

### D13. Docker i docker compose
`docker-compose.yml` z trzema usługami:
```
services:
  db       image: postgres:<wersja główna>    port "127.0.0.1:5432:5432"   wolumen finbro-pgdata:/var/lib/postgresql (od PG 18 dane są w podkatalogu wersji)
           env z .env (POSTGRES_USER/PASSWORD/DB), healthcheck: pg_isready
           skrypt init tworzy dodatkowo bazę finbro_test
  app      build: .                           port "127.0.0.1:8000:8000"
           env: DATABASE_URL, LLM_URL=http://model-runner.docker.internal/engines/v1, LLM_MODEL
           depends_on: db (condition: service_healthy)
           start: alembic upgrade head && uvicorn ... --host 0.0.0.0 --workers 1
```
- **Dockerfile:** obraz `python:3.13-slim`, instalacja zależności z `pyproject.toml` w osobnej warstwie (cache), użytkownik bez uprawnień roota, `HEALTHCHECK` na endpoint `/health` (sprawdzający też połączenie z bazą).
- **Porty tylko na loopback hosta.** Wewnątrz kontenerów serwery słuchają na `0.0.0.0`. Ograniczenie dostępu zapewnia publikacja `127.0.0.1:...`. Port bazy jest opublikowany, żeby aplikacja i testy uruchamiane z `.venv` mogły się z nią łączyć.
- **Kolejność startu:** `depends_on` z `service_healthy` sprawia, że migracje startują dopiero przy gotowej bazie.
- **Jeden worker Uvicorna.** Worker LLM z D9 to wątek w procesie aplikacji. Jeden proces wystarcza dla jednego użytkownika i upraszcza zarządzanie zasobami CPU.
- **Kopie zapasowe:** `pg_dump -Fc` wykonywany wewnątrz kontenera do pliku, potem `docker compose cp` na hosta (do `backups/`). Przywracanie przez `pg_restore --clean`. Nie przekierowujemy wyjścia `pg_dump` przez `>` w PowerShellu, bo zmienia on kodowanie strumienia i psuje binarny dump.
- **Model przez Docker Model Runner, bez trzeciego kontenera.** DMR jest częścią Docker Desktop: uruchamia llama.cpp bezpośrednio w Windows (poza maszyną WSL2 i jej limitem pamięci), a kontenery osiągają go pod `http://model-runner.docker.internal`. Model pobiera się raz poleceniem `docker model pull <model>` i ładuje do pamięci przy pierwszym zapytaniu. Na tym laptopie DMR musi działać na CPU: przy akceleracji Vulkan na zintegrowanym GPU (512 MB pamięci) ładowanie modelu kończy się błędem `ErrorOutOfDeviceMemory`. Bez włączonego DMR albo bez modelu klasyfikacja kończy się na regułach i historii (spec: "Model niedostępny"). API DMR nie ma uwierzytelnienia, ale jest osiągalne tylko lokalnie. Odrzucona alternatywa: kontener `ollama/ollama` w profilu `llm` (obraz 9,4 GB na dysku, model liczony w maszynie WSL2 z limitem ~7,4 GB).
- **Praca deweloperska** w `.venv` (szybkie testy, debugowanie w PyCharmie) z bazą z compose: `docker compose up -d db`, a potem aplikacja i `pytest` lokalnie. Testy można też uruchomić w kontenerze: `docker compose run --rm tests pytest` (usługa `tests` w profilu `test`, obraz z etapu `dev` z zależnościami deweloperskimi; obraz aplikacji ich nie zawiera).
- *Alternatywa:* Ollama (natywnie w Windows albo w kontenerze), osiągana pod `http://host.docker.internal:11434/v1`. Wystarczy zmienić `LLM_URL` i `LLM_MODEL`, bo klient używa API zgodnego z OpenAI.

### D14. Reguły początkowe jako dane
Reguły startowe (bankomat i wpłatomat → TRANSFER Portfela, "Przelew z karty" + Revolut → TRANSFER budżet rodzinny, tytuł FinBro → ODKŁADANIE) tworzy migracja danych jako zwykłe, edytowalne reguły. Regułę refundacji od rodziny użytkownik dodaje sam, bo nadawcy to jego dane. Rozpoznanie tytułu FinBro (D8) jest dodatkowo wbudowane w logikę rozliczenia, więc działa nawet po usunięciu reguły.

## Ryzyka / Kompromisy

- **[Kolizja odcisku]** Sekwencja `+X`, `-X`, `+X` tego samego dnia daje dwa razy to samo saldo po operacji. → W obrębie jednego pliku odróżniamy operacje numerem wystąpienia (`occurrence` w D5). Między plikami ryzyko pozostaje, ale jest skrajnie mało prawdopodobne. Podsumowanie importu pokazuje "istniejące", więc anomalię da się zauważyć.
- **[Zmiana formatu iPKO]** → Parser ma testy na syntetycznych fixture'ach. Nieznany element główny lub brak wymaganych pól daje twardy błąd importu (atomowość). Nieznane etykiety w opisie nie przerywają importu.
- **[Wolny lub słaby model lokalny]** → Model działa w tle i jest trzecią warstwą po regułach i historii, a aplikacja działa bez niego. Spike przed integracją sprawdza, czy jakikolwiek model daje akceptowalny czas i trafność. Jeśli nie, MVP może zostać wydane z wyłączonym LLM.
- **[Zapomniany import lub inwentaryzacja]** → Ostrzeżenia przed zamknięciem rozliczenia (pokrycie importów, niezatwierdzone wpływy, brak inwentaryzacji). Spóźnione dane trafiają do korekt.
- **[Wakacje doładowane kartą zamiast przelewem]** Doładowanie zostanie uznane za budżet rodzinny, a koperta Wakacje pokaże niedopłatę. → Użytkownik przeklasyfikuje transakcję ręcznie na ODKŁADANIE (Wakacje). Przeniesienie zniknie w następnym tygodniu.
- **[Brak uwierzytelniania aplikacji]** Inny użytkownik tego samego komputera ma dostęp do danych. → Akceptowane dla MVP (porty tylko na loopbacku, komputer prywatny, baza chroniona hasłem z `.env`).
- **[Utrata danych przy usuwaniu wolumenu]** `docker compose down -v` albo czyszczenie Docker Desktop usuwa wolumen `finbro-pgdata`. → README opisuje kopię zapasową i przywracanie, a test end-to-end (11.3) sprawdza, że dane przeżywają `down`/`up` bez `-v`.
- **[Aktualizacja wersji głównej PostgreSQL]** Nowy obraz z inną wersją główną nie odczyta starego katalogu danych. → Wersja główna przypięta w compose. Procedura aktualizacji przez `pg_dump`/`pg_restore` opisana w README.
- **[Baza musi działać do pracy i testów]** Bez uruchomionego kontenera `db` nie działają ani aplikacja, ani testy integracyjne. → Czytelny komunikat błędu z instrukcją, a testy domeny działają bez bazy.
- **[Pamięć dla modelu]** Docker Model Runner działa poza maszyną WSL2, więc model nie dzieli jej limitu (~8 GB) z PostgreSQL, tylko korzysta z pamięci Windows. → Spike (8.1) mierzy zużycie pamięci procesu modelu. Aplikacja nie zmienia ustawień systemu.
- **[Kompromis: brak dzielenia transakcji]** Wpływ, który jest częściowo spłatą, a częściowo dochodem, trzeba sklasyfikować jako jedno albo drugie. Spłata większa niż saldo jest odrzucana. → Rzadki przypadek, poza MVP.

## Plan wdrożenia

1. Skopiować `.env.example` do `.env` i ustawić hasło bazy.
2. `docker compose up -d --build`. Baza startuje pierwsza, a aplikacja po jej gotowości wykonuje `alembic upgrade head`, które tworzy schemat, kategorie, reguły startowe i plan 50/12,5/12,5/25. Aplikacja jest pod `http://127.0.0.1:8000`.
3. Pierwsze uruchomienie: w panelu admina użytkownik ustawia datę startu, numer konta głównego, rachunki docelowe kopert (Revolut, XTB, rachunek rejestrowy obligacji) i stan początkowy Portfela.
4. Opcjonalnie: włączyć Docker Model Runner w Docker Desktop (na CPU) i pobrać model wybrany w spike'u (`docker model pull <model>`). Bez tego klasyfikacja kończy się na regułach i historii.
5. Aktualizacja: `docker compose up -d --build`. Migracje wykonają się przy starcie, dane zostają w wolumenie `finbro-pgdata`.
6. Wycofanie zmian: `docker compose down` (bez `-v`). Dane zostają w wolumenie. Powrót do poprzedniej wersji aplikacji z zachowaniem danych wymaga `alembic downgrade` do odpowiedniej rewizji albo odtworzenia kopii z `pg_dump`.

## Otwarte pytania

- ~~Który model lokalny wybrać.~~ Rozstrzygnięte w spike'u (zadanie 8.1): `ai/gemma4:E2B` przez Docker Model Runner.
- Czy SQLAdmin jest aktywnie utrzymywany dla aktualnych wersji SQLAlchemy i FastAPI. Jeśli nie, panel CRUD powstaje jako proste widoki Jinja2, a zakres funkcji się nie zmienia.
