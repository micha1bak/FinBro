# Projekt: FinBro w wersji prostej

## Kontekst

Motywacja i zakres: patrz `proposal.md`. Wymagania: `specs/income-allocation`, `specs/transfer-settlement`, `specs/net-worth`.

Obecny kod (`finbro-mvp`) ma warstwy web → serwisy (UnitOfWork) → repozytoria → domena, 18 tabel, wątek LLM, SQLAdmin i import XML. Infrastruktura (Docker, PostgreSQL 18, Alembic, FastAPI z Jinja2 i HTMX, testy na prawdziwej bazie `finbro_test`) działa dobrze i zostaje. Model danych jest zbudowany wokół transakcji bankowych i klasyfikacji, więc nie nadaje się do przeróbki: piszemy go od nowa.

## Cele / Poza zakresem

**Cele:**
- Kod na tyle mały, żeby użytkownik mógł go przejrzeć i sprawdzić ręcznie w kilka minut: cztery widoki, sześć tabel.
- Obliczenia (podział, sumy przelewów, salda) jako czyste funkcje z testami jednostkowymi, w tym na przykładach z arkusza.

**Poza zakresem:**
- Import wyciągów, wydatki, kategorie, model językowy, wiele walut, wielu użytkowników, logowanie.
- Konfigurowalna lista kopert (koperty są stałe, patrz D3).
- Migracja danych z pierwszej wersji i z arkusza.

## Decyzje

### D1. Prostsza struktura kodu: domena, baza, serwisy, web
```
finbro/
  domain/    money.py (zostaje), allocation.py (podział), networth.py (salda) – czyste funkcje, bez SQLAlchemy
  db/        models.py, session.py, migrations/
  services/  incomes.py, settlements.py, networth.py, settings.py – operują na Session SQLAlchemy
  web/       app.py, routes/ (incomes, settlement, networth, settings), templates/, static/
```
Rezygnujemy z repozytoriów i UnitOfWork: przy sześciu tabelach i jednym użytkowniku serwis z sesją jest czytelniejszy. Test architektury pilnuje tylko, żeby `domain` nie importowała SQLAlchemy ani FastAPI, a `web` nie wykonywała zapytań poza serwisami.
*Alternatywa:* zostawić obecne warstwy. Odrzucona: dużo kodu przejściowego przy małej logice.

### D2. Model danych
- `income`: id, `date`, `source`, `amount` (grosze), `form` (`PKO` / `GOTOWKA`, CHECK, domyślnie `PKO`), `settlement_id` (null = nierozliczony).
- `allocation_plan`: id, `effective_from` (unikalna), `pko`, `wakacje`, `xtb`, `obligacje` (punkty bazowe, CHECK: suma = 10000).
- `income_share`: `income_id`, `envelope`, `amount` – podział zamrożony w chwili rozliczenia.
- `settlement`: id, `date`, `created_at`; `settlement_line`: `settlement_id`, `envelope`, `amount`.
- `envelope_account`: `envelope` (PK), `target_account` – rachunki docelowe Wakacji, XTB i Obligacji.
- `balance_entry`: id, `account` (PKO / GOTOWKA / XTB / OBLIGACJE), `date`, `amount`, unikalne (`account`, `date`).

Podział nierozliczonego dochodu liczymy w locie z planu obowiązującego w jego dniu. Przy rozliczeniu zapisujemy go w `income_share`, dzięki czemu późniejsza zmiana planu nie zmienia rozliczonych dochodów. Kwoty w groszach (`BIGINT`), udziały w punktach bazowych.
*Alternatywa:* zapisywać podział przy każdym wpisie. Odrzucona: zmiana planu wymagałaby przeliczania zapisanych wierszy.

### D3. Stałe koperty w kodzie
Koperty PKO, Wakacje, XTB i Obligacje to wyliczenie w `domain` (nazwa, kolejność, czy jest przelewem). Konta majątku to osobne wyliczenie: PKO, Gotówka, XTB i Obligacje, z informacją, czy saldo jest tylko ręczne (PKO, Gotówka) i z której koperty rosną rozliczeniami (XTB, Obligacje). Plan ma stałe kolumny zamiast tabeli udziałów.
*Alternatywa:* koperty jako tabela edytowalna w ustawieniach. Odrzucona: arkusz od lat ma te same koperty, a stała lista upraszcza formularze, walidację i testy. Nowa koperta to mała zmiana kodu i migracja.

### D4. Zaokrąglenie jak w arkuszu
Dla Wakacji, XTB i Obligacji: `kwota × udział` zaokrąglone do pełnych złotych, połówki w górę (`ROUND_HALF_UP`, jak `ROUND(x;0)` w Excelu). PKO dostaje resztę. Liczymy na `Decimal` z groszy, bez `float`. Test własności (hypothesis): suma podziału zawsze równa się kwocie.

### D5. Rozliczenie dokładnie tego, co użytkownik widział
Formularz „Rozliczone” wysyła listę id dochodów z wyświetlonej listy. Serwis w jednej transakcji blokuje te wiersze (`SELECT ... FOR UPDATE`), pomija już rozliczone, liczy kwoty od nowa z tych dochodów, zapisuje `settlement`, `settlement_line` i `income_share` i ustawia `settlement_id`. Jeśli lista po stronie serwera różni się od wyświetlonej (np. ktoś poprawił kwotę w innej karcie), serwis odrzuca rozliczenie z prośbą o odświeżenie widoku. Tytuł przelewu: `FinBro <Koperta> <data rozliczenia>`, np. `FinBro XTB 2026-10-19`.

### D6. Cofnięcie tylko najnowszego rozliczenia
Cofnięcie usuwa `settlement` (kaskadowo linie i `income_share`) i zeruje `settlement_id` jego dochodów. Ograniczenie do najnowszego eliminuje przypadki, w których starsze rozliczenie byłoby wliczone w późniejsze salda.

### D7. Majątek jako czysta funkcja
`networth.balances(entries, settlement_lines, day)` zwraca saldo każdego konta na dzień według `specs/net-worth`. Oś czasu do wykresu to zbiór dni wpisów sald i rozliczeń, a dla każdego dnia suma sald. Różnica przy wpisie salda faktycznego to wpis minus saldo wyliczone na ten dzień bez tego wpisu. Wykres: Chart.js (już dołączony do repozytorium), linia sumy majątku.

### D8. Własny widok ustawień zamiast SQLAdmin
Ustawienia to jeden formularz: plan podziału (udziały w procentach i data obowiązywania, lista dotychczasowych planów) oraz rachunki docelowe kopert. SQLAdmin i `itsdangerous` znikają z zależności. `python-multipart` zostaje, bo FastAPI potrzebuje go do formularzy.
*Alternatywa:* zostawić SQLAdmin. Odrzucona: osobny wygląd i nawigacja były źródłem pomyłki (numer konta wpisany w złą tabelę).

### D9. Nowy początek migracji i jednorazowy reset bazy
Usuwamy stare migracje i tworzymy nową migrację początkową z nowym identyfikatorem (schemat i plan startowy 50/25/12,5/12,5 od 2000-01-01). Istniejąca baza ma w `alembic_version` rewizję, której nowy łańcuch nie zna, a jej jedyne dane to jeden testowy tydzień z importu. Dlatego README opisuje jednorazowy reset: `docker compose down`, usunięcie wolumenu `finbro-pgdata`, `docker compose up -d --build`. Wykonuje go użytkownik albo agent po jego wyraźnej zgodzie. Skrypt init dalej tworzy bazę `finbro_test`.
*Alternatywa:* migracja 0003 usuwająca stare tabele. Odrzucona: łańcuch dalej zawierałby cały stary schemat, a testy budowałyby go przy każdym uruchomieniu.

### D10. Usunięcie modelu językowego i zależności od Docker Model Runner
Znikają wątek workera, zmienne `LLM_URL` i `LLM_MODEL` (z `config.py`, `docker-compose.yml` i `.env.example`), skrypt spike'a i `docs/llm-spike.md` (zostają w historii gita). `docker-compose.yml` ma dalej usługi `db`, `app` i `tests`.

### D11. Interfejs: cztery widoki
- **Dochody** (strona startowa): formularz dodawania na górze, lista miesiąca z podziałem, statusem i sumami, przełącznik miesięcy, edycja i usuwanie nierozliczonych.
- **Rozliczenie**: lista przelewów do wykonania z przyciskiem „Kopiuj” przy rachunku i tytule, przycisk „Rozliczone”, historia rozliczeń z możliwością cofnięcia najnowszego.
- **Majątek**: salda trzech kont, suma, data ostatniej aktualizacji, formularz wpisu salda z pokazaną różnicą, wykres.
- **Ustawienia**: plan podziału i rachunki docelowe.
Zwykłe formularze z przekierowaniem po zapisie wystarczają, więc HTMX został usunięty razem z plikiem w `static/vendor`. Wygląd: obecny `finbro.css`.

### D12. Testy
- Jednostkowe: podział (przykłady ze specyfikacji na zmyślonych kwotach, test własności), sumy przelewów, salda i różnice majątku.
- Integracyjne na `finbro_test`: serwisy dochodów, rozliczeń (w tym dochód dodany w międzyczasie i cofnięcie) i majątku.
- Widoki: `TestClient` dla czterech stron i ich formularzy oraz jeden test end-to-end: dochody → rozliczenie → saldo XTB w majątku.
Fixture'y bazy (schemat odtwarzany migracjami w każdej sesji, test w wycofywanej transakcji) zostają.

## Ryzyka / Kompromisy

- [Utrata danych pierwszej wersji przy resecie bazy] → To jeden testowy tydzień z wyciągu, który można ponownie wyeksportować z iPKO. Reset wykonujemy tylko po wyraźnej zgodzie użytkownika.
- [Stałe koperty] → Nowa koperta wymaga zmiany kodu i migracji. Akceptowalne przy kopertach niezmiennych od lat.
- [Saldo wyliczone XTB i Obligacji odbiega od rzeczywistego] → Rozliczenie oznacza zamiar przelewu, a nie jego wykonanie, a inwestycje zmieniają wartość. Różnica jest widoczna przy każdym wpisie salda faktycznego.
- [Rozbieżność z arkuszem przy zaokrągleniach] → Ta sama reguła co w „Kalk2” (`ROUND(x;0)` dla trzech kopert, reszta na PKO), sprawdzona testami na zmyślonych kwotach z połówkami groszy i złotych.

## Plan wdrożenia

1. Implementacja według `tasks.md` na nowym schemacie (testy na `finbro_test`).
2. Po zgodzie użytkownika: `docker compose down`, `docker volume rm finbro-pgdata`, `docker compose up -d --build`.
3. Użytkownik ustawia rachunki docelowe i wpisuje salda początkowe PKO, XTB i Obligacji (stan po przelewach z arkusza „Kalk2”, już rozliczonych). Kolejne dochody wpisuje w aplikacji. Rozliczenie z tego samego dnia co saldo faktyczne nie jest do niego doliczane (`specs/net-worth`), więc kolejność wpisów w dniu startu nie ma znaczenia.
4. Wycofanie: powrót do commita sprzed zmiany i odtworzenie bazy z kopii `pg_dump` (procedura w README).
