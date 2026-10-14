# Zadania

## 1. Sprzątanie po pierwszej wersji

- [x] 1.1 Usunąć zmianę `openspec/changes/finbro-mvp` (bez archiwizacji) i zaktualizować wskazówki w `openspec/config.yaml` (najważniejsze funkcje do testów: podział, rozliczenie, salda majątku). Weryfikacja: `openspec list` pokazuje tylko `finbro-prosty`, a `openspec validate finbro-prosty --strict` przechodzi.
- [x] 1.2 Usunąć moduły pierwszej wersji z testami (import XML i fixture'y PKO, klasyfikacja, LLM i worker, SQLAdmin, portfel, należności, raporty, tygodniowe rozliczenie, repozytoria i UnitOfWork, `scripts/`, `docs/llm-spike.md`), zmienne `LLM_*` z `config.py`, `docker-compose.yml` i `.env.example` oraz zależności `sqladmin` i `itsdangerous`. Zostaje szkielet aplikacji ze stroną startową i `/health`. Weryfikacja: pozostałe testy (`Money`, konfiguracja, `/health`, fixture'y bazy) przechodzą, a `docker compose build app` się udaje.

## 2. Model danych

- [x] 2.1 Zastąpić stare migracje nową migracją początkową z tabelami z D2 (`income`, `allocation_plan`, `income_share`, `settlement`, `settlement_line`, `envelope_account`, `balance_entry`) i planem startowym 50/25/12,5/12,5 od 2000-01-01. Weryfikacja: testy na `finbro_test` sprawdzają utworzenie tabel i planu startowego, odrzucenie planu o sumie różnej od 100% (CHECK) oraz unikalność salda dla konta i dnia.

## 3. Dochody i podział

- [x] 3.1 Zaimplementować w `domain` koperty (D3), plan i podział z zaokrągleniem jak w arkuszu (D4). Weryfikacja: testy jednostkowe dla przykładów ze specyfikacji (2401,30 zł i 174,00 zł), wyboru planu obowiązującego w dniu dochodu oraz test własności, że suma podziału równa się kwocie.
- [x] 3.2 Zaimplementować serwis dochodów: dodawanie z walidacją, poprawianie i usuwanie tylko nierozliczonych, podział (zamrożony dla rozliczonych), lista i podsumowanie miesiąca, dodawanie planu z walidacją. Weryfikacja: testy integracyjne dla scenariuszy z `specs/income-allocation`, w tym zmiany planu, która nie zmienia rozliczonego dochodu.
- [x] 3.3 Zbudować widok Dochody (strona startowa): formularz dodawania, lista miesiąca z podziałem, statusem i sumami, przełącznik miesięcy, edycja i usuwanie, nowa nawigacja (Dochody, Rozliczenie, Majątek, Ustawienia). Weryfikacja: testy `TestClient` dla dodania poprawnego i błędnego dochodu, podsumowania października i odmowy edycji rozliczonego dochodu.

## 4. Rozliczenie

- [x] 4.1 Zaimplementować w `domain` sumy przelewów z nierozliczonych dochodów i tytuł `FinBro <Koperta> <data>`. Weryfikacja: testy jednostkowe dla dwóch dochodów (644 / 322 / 322 zł), pominięcia koperty z sumą 0 zł i formatu tytułu.
- [x] 4.2 Zaimplementować serwis rozliczeń (D5, D6): rozliczenie wskazanych dochodów z blokadą wierszy, zapis linii i zamrożonego podziału, odrzucenie przy zmienionej liście, historia i cofnięcie tylko najnowszego. Weryfikacja: testy integracyjne dla scenariuszy z `specs/transfer-settlement`, w tym dochodu dodanego w międzyczasie i próby cofnięcia starszego rozliczenia.
- [x] 4.3 Zbudować widok Rozliczenie: lista przelewów z rachunkiem, tytułem i przyciskami kopiowania, ostrzeżenie o braku rachunku, przycisk „Rozliczone”, historia z cofnięciem najnowszego. Weryfikacja: testy `TestClient` dla listy, braku przelewów, rozliczenia i cofnięcia.

## 5. Majątek

- [x] 5.1 Zaimplementować w `domain` salda na dzień, różnicę przy wpisie salda faktycznego i oś czasu sumy majątku (D7). Weryfikacja: testy jednostkowe dla scenariuszy z `specs/net-worth` (1522,00 zł, brak podwójnego liczenia, +38,00 zł, PKO tylko ręcznie, suma 5932,25 zł).
- [x] 5.2 Zaimplementować serwis majątku: wpis salda faktycznego (zastąpienie wpisu z tego samego dnia, kwota nieujemna) i odczyt sald, różnicy i osi czasu z bazy. Weryfikacja: testy integracyjne, w tym spadek wyliczonego salda XTB po cofnięciu rozliczenia.
- [x] 5.3 Zbudować widok Majątek: salda trzech kont, suma z datą aktualizacji, formularz wpisu salda z pokazaną różnicą, wykres sumy (Chart.js) i zachęta do wpisania sald przy braku danych. Weryfikacja: testy `TestClient` dla pustego widoku, wpisu salda z różnicą i danych wykresu.

## 6. Ustawienia

- [x] 6.1 Zbudować widok Ustawienia: rachunki docelowe Wakacji, XTB i Obligacji oraz nowy plan podziału z datą obowiązywania i listą dotychczasowych planów. Weryfikacja: testy `TestClient` dla zapisu rachunku widocznego potem na liście przelewów i odrzucenia planu o sumie 95%.

## 7. Integracja i uruchomienie

- [x] 7.1 Test end-to-end przez widoki: dwa dochody → lista przelewów → rozliczenie → saldo XTB w majątku rośnie o 322 zł → cofnięcie przywraca stan. Weryfikacja: test przechodzi razem z pełnym zestawem testów, także w kontenerze (`docker compose run --rm tests pytest`).
- [ ] 7.2 Przepisać README pod nową wersję: uruchomienie w Dockerze, pierwsza konfiguracja (rachunki, salda początkowe), praca w `.venv`, kopia zapasowa i przywracanie oraz jednorazowy reset bazy po przejściu z pierwszej wersji (D9). Weryfikacja: kroki z README wykonane na izolowanym projekcie compose dają działającą aplikację z czterema widokami.
- [ ] 7.3 Po wyraźnej zgodzie użytkownika zresetować wolumen `finbro-pgdata` i uruchomić nową wersję. Weryfikacja: `docker compose ps` pokazuje bazę i aplikację jako `healthy`, a cztery widoki odpowiadają kodem 200.
