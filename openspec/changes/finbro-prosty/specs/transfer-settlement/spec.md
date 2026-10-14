# Spec Delta

## Purpose

Zbiorcze rozliczanie przelewów na koperty: jedna lista przelewów dla wszystkich nierozliczonych dochodów i oznaczanie ich jako rozliczonych po wykonaniu przelewów.

## ADDED Requirements

### Requirement: Lista przelewów do wykonania
System SHALL pokazywać sumę części Wakacje, XTB i Obligacje wszystkich nierozliczonych dochodów jako listę przelewów: koperta, kwota, rachunek docelowy i tytuł do skopiowania. Część PKO zostaje na koncie głównym i nie jest przelewem. Koperta z sumą 0 zł nie pojawia się na liście.

#### Scenario: Dwa nierozliczone dochody
- **WHEN** nierozliczone są dochody 2401,30 zł i 174,00 zł przy planie 50/25/12,5/12,5
- **THEN** lista zawiera przelewy Wakacje 644 zł, XTB 322 zł i Obligacje 322 zł, każdy z rachunkiem docelowym koperty i tytułem zawierającym nazwę koperty i datę

#### Scenario: Brak nierozliczonych dochodów
- **WHEN** wszystkie dochody są rozliczone
- **THEN** widok informuje, że nie ma przelewów do wykonania

#### Scenario: Brak rachunku docelowego
- **WHEN** koperta na liście nie ma ustawionego rachunku docelowego
- **THEN** przelew jest pokazany z kwotą i ostrzeżeniem, że trzeba uzupełnić rachunek w ustawieniach

### Requirement: Oznaczenie rozliczenia
System SHALL po potwierdzeniu użytkownika zapisać rozliczenie z datą i kwotami przelewów oraz oznaczyć jako rozliczone dokładnie te dochody, które były na liście w chwili jej wyświetlenia. Dochody dodane później MUST pozostać nierozliczone.

#### Scenario: Rozliczenie listy
- **WHEN** użytkownik klika „Rozliczone” przy liście z dwoma dochodami
- **THEN** oba dochody mają status rozliczony, rozliczenie z kwotami Wakacje 644 zł, XTB 322 zł i Obligacje 322 zł trafia do historii, a lista przelewów jest pusta

#### Scenario: Dochód dodany w międzyczasie
- **WHEN** po wyświetleniu listy, a przed kliknięciem „Rozliczone”, pojawia się nowy dochód
- **THEN** nowy dochód pozostaje nierozliczony i trafia na następną listę

### Requirement: Historia i cofnięcie rozliczenia
System SHALL pokazywać historię rozliczeń (data, kwoty przelewów, liczba dochodów) i pozwalać cofnąć najnowsze rozliczenie. Cofnięcie przywraca jego dochodom status nierozliczony i usuwa rozliczenie z historii oraz z wyliczeń majątku.

#### Scenario: Cofnięcie pomyłki
- **WHEN** użytkownik cofa najnowsze rozliczenie
- **THEN** jego dochody wracają na listę przelewów do wykonania, a salda XTB i Obligacji wyliczone w majątku maleją o kwoty tego rozliczenia

#### Scenario: Starsze rozliczenie
- **WHEN** istnieje nowsze rozliczenie
- **THEN** starszego rozliczenia nie można cofnąć

### Requirement: Rachunki docelowe kopert
System SHALL pozwalać ustawić numer rachunku docelowego dla kopert Wakacje, XTB i Obligacje. Numery rachunków są daną użytkownika i MUST NOT trafiać do repozytorium.

#### Scenario: Ustawienie rachunku
- **WHEN** użytkownik zapisuje numer rachunku dla XTB w ustawieniach
- **THEN** lista przelewów pokazuje ten numer przy przelewie na XTB
