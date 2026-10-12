# Propozycja

## Dlaczego

Mam nieregularne i zmienne dochody, z bankowych przelewów i z gotówki. Każdy dochód dzielę według stałych proporcji na życie, inwestycje i wakacje. Do tej pory robiłem to ręcznie: wpisywałem przychody do Excela, liczyłem kwoty i przelewałem je między PKO BP, Revolutem, XTB i rachunkiem obligacji skarbowych. To jest żmudne i podatne na błędy. Do tego nie mam wiarygodnego obrazu tego, ile zarabiam i wydaję tygodniowo, miesięcznie i rocznie. FinBro ma zautomatyzować całe liczenie, księgowanie i analizę. Same przelewy wykonuję ręcznie, bo dla osoby prywatnej nie ma realnego API do ich zlecania.

## Co się zmienia

- Nowa lokalna aplikacja webowa FinBro (jeden użytkownik, uruchamiana na własnym komputerze), uruchamiana w kontenerach Docker przez `docker compose`: aplikacja oraz opcjonalnie lokalny serwer modelu językowego.
- Import wyciągu z konta głównego PKO BP w formacie XML z iPKO, z deduplikacją przy wielokrotnym imporcie nakładających się okresów.
- Portfel gotówkowy jako konto prowadzone ręcznie: gotówkowe dochody i wydatki oraz cotygodniowa inwentaryzacja. Różnica stanu staje się wydatkiem gotówkowym bez kategorii.
- Klasyfikacja każdej transakcji według typu (dochód, wydatek, odkładanie, transfer własny, zwrot, rozliczenie, pożyczka, spłata) i kategorii wydatku. Kolejne warstwy to reguły, historia kontrahenta, lokalny LLM działający w tle i decyzja użytkownika w skrzynce. Dochód zawsze wymaga zatwierdzenia przez użytkownika.
- Cotygodniowe rozliczenie w poniedziałek za poprzedni tydzień (pon–nd). Dochody są dzielone według datowanych proporcji (domyślnie 50% życie / 25% inwestycje = 12,5% XTB + 12,5% obligacje / 25% wakacje). FinBro generuje listę przelewów z tytułami `FinBro T<nr> ...`, a z kolejnych importów sam rozpoznaje wykonane przelewy. Różnice przechodzą na kolejny tydzień.
- Ewidencja należności "kto i ile jest mi winien" ze spłatami częściowymi i darowaniem długu (darowana kwota staje się wydatkiem).
- Raporty: przychody i wydatki tygodniowo, miesięcznie i rocznie, z podziałem na kategorie i sprzedawców.
- Poza zakresem MVP: integracja z API banków (PSD2/agregatory), import z Revoluta i XTB, automatyczne zlecanie przelewów, bot lub aplikacja na telefon, migracja historii z Excela, budżety i prognozy, śledzenie własnych długów.

## Możliwości (capabilities)

### Nowe możliwości

- `transaction-import`: import wyciągów XML z iPKO dla konta głównego. Obejmuje parsowanie pól opisu, rozróżnienie daty transakcji i daty księgowania, pomijanie blokad i deduplikację po odcisku `(data, kwota, saldo po transakcji)`.
- `cash-wallet`: konto "Portfel" dla gotówki: ręczne dochody i wydatki gotówkowe, wypłaty z bankomatu jako zasilenie portfela oraz cotygodniowa inwentaryzacja stanu portfela.
- `transaction-classification`: typy transakcji, płaska lista kategorii wydatków, reguły klasyfikacji, podpowiedzi z historii kontrahenta i z lokalnego LLM, skrzynka do zatwierdzania oraz tworzenie reguł z decyzji użytkownika.
- `weekly-settlement`: datowane proporcje podziału, wyliczenie należnych kwot dla każdego tygodnia, lista przelewów z tytułami, automatyczne dopasowanie wykonanych przelewów i przeniesienia różnic na kolejne tygodnie.
- `receivables`: należności od osób: pożyczki, spłaty (także częściowe), darowanie długu i saldo na osobę.
- `financial-reporting`: zestawienia przychodów i wydatków w okresach tygodnia, miesiąca i roku, z podziałem na kategorie i sprzedawców, z poprawnym traktowaniem typów neutralnych.

### Zmodyfikowane możliwości

Brak. Projekt nie ma jeszcze żadnych specyfikacji.

## Wpływ

- Nowy kod w Pythonie 3.13 (istniejące, puste `.venv` do pracy deweloperskiej). Stos: FastAPI, SQLAlchemy 2.0 (psycopg 3), Alembic, SQLAdmin, Jinja2 + HTMX, Chart.js, pytest. Baza danych: PostgreSQL (także w testach integracyjnych), bez SQLite.
- Uruchamianie: `Dockerfile` aplikacji i `docker-compose.yml` z usługami PostgreSQL i aplikacji (Docker Desktop z WSL2 jest już zainstalowany). Dane w wolumenie Dockera, porty udostępnione tylko na `127.0.0.1`.
- Nowa zależność uruchomieniowa: Ollama z lokalnym modelem językowym jako opcjonalna usługa w `docker compose` (aplikacja działa bez niej). Konkretny model zostanie wybrany w spike'u pod kątem sprzętu użytkownika (16 GB RAM, CPU bez dedykowanego GPU).
- Testy kluczowej logiki są obowiązkową częścią każdego zadania implementacyjnego (zasada zapisana w konfiguracji OpenSpec projektu).
- Dane finansowe i dane osób trzecich zostają wyłącznie na komputerze użytkownika. Wyciągi bankowe nie mogą trafić do repozytorium.
- Zmiana w procesie użytkownika: przelewy na Revolut (wakacje) są wykonywane przelewem na IBAN z tytułem wygenerowanym przez FinBro, a doładowania kartą służą wyłącznie budżetowi rodzinnemu.
