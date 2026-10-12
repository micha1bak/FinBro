# Spec Delta

## Purpose

Wczytuje do FinBro transakcje z konta głównego w PKO BP z wyciągów XML eksportowanych z iPKO. Każda operacja bankowa trafia do systemu dokładnie raz, z poprawnymi datami, kwotą i rozbitym opisem.

## ADDED Requirements

### Requirement: Import wyciągu XML z iPKO
System SHALL przyjmować plik wyciągu w formacie XML eksportowanym z iPKO (element główny `account-history`) i tworzyć z każdej zaksięgowanej operacji transakcję konta głównego. Import SHALL być atomowy: przy błędzie żadna transakcja z pliku nie zostaje zapisana.

#### Scenario: Poprawny import
- **WHEN** użytkownik importuje poprawny plik XML z iPKO zawierający 14 zaksięgowanych operacji, z których żadnej nie ma w systemie
- **THEN** system zapisuje 14 nowych transakcji konta głównego

#### Scenario: Plik w nieobsługiwanym formacie
- **WHEN** użytkownik importuje plik, który nie jest wyciągiem XML z iPKO (np. CSV, HTML albo uszkodzony XML)
- **THEN** system odrzuca import z czytelnym komunikatem błędu i nie zapisuje żadnej transakcji

### Requirement: Weryfikacja rachunku
System SHALL porównać numer rachunku z sekcji kryteriów wyciągu z numerem skonfigurowanego konta głównego i odrzucić import, jeśli się różnią. Numer w eksporcie może być częściowo zamaskowany. Wtedy porównuje się widoczne cyfry z początku i końca numeru.

#### Scenario: Wyciąg z innego rachunku
- **WHEN** użytkownik importuje wyciąg z rachunku innego niż skonfigurowane konto główne
- **THEN** system odrzuca import z komunikatem wskazującym niezgodność rachunku

### Requirement: Data transakcji i data księgowania
System SHALL zapisywać dla każdej transakcji datę transakcji (z pola `order-date`) i datę księgowania (z pola `exec-date`). Data transakcji SHALL być datą wiążącą dla przypisania transakcji do tygodnia, miesiąca i roku.

#### Scenario: Płatność kartą zaksięgowana później
- **WHEN** importowana jest płatność kartą z `order-date` 2026-10-10 (sobota) i `exec-date` 2026-10-12 (poniedziałek)
- **THEN** transakcja ma datę transakcji 2026-10-10 i należy do tygodnia 2026-10-05 – 2026-10-11

### Requirement: Pomijanie blokad
System SHALL pomijać operacje bez daty księgowania (blokady i operacje w toku) i uwzględniać je dopiero w imporcie, w którym są już zaksięgowane.

#### Scenario: Operacja niezaksięgowana
- **WHEN** plik zawiera operację bez wartości `exec-date`
- **THEN** system jej nie zapisuje i wykazuje ją w podsumowaniu importu jako pominiętą blokadę

### Requirement: Deduplikacja przy ponownym imporcie
System SHALL rozpoznawać operacje już zaimportowane na podstawie rachunku, daty księgowania, kwoty i salda po transakcji i SHALL nie tworzyć ich ponownie. Dwie operacje o tej samej dacie i kwocie, ale różnym saldzie po transakcji, SHALL być traktowane jako różne transakcje.

#### Scenario: Nakładające się okresy
- **WHEN** użytkownik importuje wyciąg za 2026-10-05 – 2026-10-11, a potem wyciąg za 2026-10-08 – 2026-10-18
- **THEN** operacje z 2026-10-08 – 2026-10-11 nie są duplikowane, a podsumowanie drugiego importu wykazuje je jako już istniejące

#### Scenario: Dwie identyczne płatności tego samego dnia
- **WHEN** wyciąg zawiera dwie płatności po -7,00 zł z tą samą datą i tym samym opisem, z saldami po transakcji 6351,56 i 6344,56
- **THEN** system zapisuje obie jako osobne transakcje

### Requirement: Kierunek i kwota operacji
System SHALL określać kierunek operacji (wpływ albo wydatek) wyłącznie na podstawie znaku kwoty, niezależnie od nazwy typu operacji w banku. Kwoty SHALL być przechowywane bez utraty dokładności do grosza.

#### Scenario: Mylący typ operacji
- **WHEN** importowana jest operacja typu "Przelew na telefon przychodz. zew." z kwotą -645.00
- **THEN** transakcja jest wydatkiem w kwocie 645,00 zł

### Requirement: Rozbicie opisu operacji
System SHALL wyodrębniać z opisu operacji znane pola: rachunek i nazwę kontrahenta (nadawcy lub odbiorcy), tytuł, sprzedawcę i lokalizację (adres, miasto, kraj) oraz numer referencyjny. Typ operacji z banku i pełny surowy opis SHALL być zachowane niezależnie od wyniku rozbicia.

#### Scenario: Płatność kartą
- **WHEN** opis zawiera "Lokalizacja : Adres : ZABKA Z8627 K.1 Miasto : LOMIANKI Kraj : POLSKA"
- **THEN** transakcja ma sprzedawcę "ZABKA Z8627 K.1", miasto "LOMIANKI" i kraj "POLSKA"

#### Scenario: Przelew przychodzący
- **WHEN** opis zawiera "Rachunek nadawcy : ... Nazwa nadawcy : ... Tytuł : zgodnie z umową zlecenie ..."
- **THEN** transakcja ma wypełnione pola rachunku nadawcy, nazwy kontrahenta i tytułu

#### Scenario: Nieznana etykieta w opisie
- **WHEN** opis zawiera etykietę, której system nie rozpoznaje
- **THEN** import się udaje, znane pola są wyodrębnione, a pełny surowy opis jest dostępny przy transakcji

### Requirement: Podsumowanie importu
Po każdym imporcie system SHALL pokazać podsumowanie: liczbę nowych transakcji, liczbę już istniejących, liczbę pominiętych blokad oraz zakres dat wyciągu.

#### Scenario: Podsumowanie po imporcie
- **WHEN** import kończy się powodzeniem
- **THEN** użytkownik widzi liczby nowych, istniejących i pominiętych operacji oraz zakres dat z pliku

### Requirement: Pokrycie okresów importami
System SHALL zapamiętywać zakresy dat objęte zaimportowanymi wyciągami i SHALL wskazywać dni bez pokrycia między datą startu FinBro a ostatnim importem.

#### Scenario: Luka w importach
- **WHEN** zaimportowano wyciągi za 2026-10-05 – 2026-10-11 i 2026-10-19 – 2026-10-25
- **THEN** system wskazuje okres 2026-10-12 – 2026-10-18 jako niepokryty importem
