# Spec Delta

## Purpose

Prowadzi gotówkę jako konto "Portfel", żeby gotówkowe dochody wchodziły do podziału, a wydatki gotówkowe do analityki. Wymagany wysiłek ogranicza się do jednej inwentaryzacji w tygodniu.

## ADDED Requirements

### Requirement: Konto Portfel i stan początkowy
System SHALL prowadzić konto "Portfel" z bieżącym stanem oczekiwanym. Użytkownik SHALL móc ustawić stan początkowy na dzień startu FinBro. Stan początkowy jest neutralny i nie jest ani przychodem, ani wydatkiem.

#### Scenario: Ustawienie stanu początkowego
- **WHEN** użytkownik ustawia stan początkowy portfela na 500,00 zł
- **THEN** oczekiwany stan portfela wynosi 500,00 zł, a raporty nie wykazują z tego tytułu przychodu ani wydatku

### Requirement: Ręczny dochód gotówkowy
System SHALL pozwalać wpisać dochód gotówkowy (data, kwota, opis). Taki wpis jest od razu zatwierdzonym dochodem, zwiększa oczekiwany stan portfela i podlega podziałowi w rozliczeniu tygodnia, do którego należy jego data.

#### Scenario: Gotówka od klienta
- **WHEN** użytkownik wpisuje dochód gotówkowy 800,00 zł z datą 2026-10-07
- **THEN** oczekiwany stan portfela rośnie o 800,00 zł, a dochód wchodzi do rozliczenia tygodnia 2026-10-05 – 2026-10-11 bez potrzeby zatwierdzania w skrzynce

### Requirement: Ręczny wydatek gotówkowy
System SHALL pozwalać wpisać wydatek gotówkowy z datą, kwotą i kategorią. Wpis zmniejsza oczekiwany stan portfela.

#### Scenario: Większy zakup za gotówkę
- **WHEN** użytkownik wpisuje wydatek gotówkowy 120,00 zł w kategorii "Restauracje i na mieście"
- **THEN** oczekiwany stan portfela maleje o 120,00 zł, a wydatek pojawia się w raportach w tej kategorii

### Requirement: Wypłaty i wpłaty gotówki
Wypłata z bankomatu z konta głównego SHALL być transferem własnym do Portfela, który zwiększa jego oczekiwany stan. Wpłata gotówki na konto główne SHALL być transferem własnym z Portfela, który zmniejsza jego oczekiwany stan. Żadna z tych operacji nie jest przychodem ani wydatkiem.

#### Scenario: Wypłata z bankomatu
- **WHEN** zaimportowana jest operacja "Wypłata w bankomacie" na -2300,00 zł
- **THEN** oczekiwany stan portfela rośnie o 2300,00 zł, a raporty nie wykazują wydatku z tego tytułu

#### Scenario: Wpłata gotówki we wpłatomacie
- **WHEN** zaimportowana jest wpłata gotówki na konto główne na 1000,00 zł
- **THEN** oczekiwany stan portfela maleje o 1000,00 zł, a wpłata nie jest dochodem i nie podlega podziałowi

### Requirement: Inwentaryzacja portfela
System SHALL pozwalać wpisać faktyczny stan portfela na wskazany dzień (domyślnie ostatni dzień poprzedniego tygodnia). Jeśli faktyczny stan jest niższy od oczekiwanego, system SHALL zapisać różnicę jako wydatek w systemowej kategorii "Gotówka (bez kategorii)", datowany na dzień inwentaryzacji, i wyrównać stan oczekiwany do faktycznego.

#### Scenario: Niezapisane wydatki gotówkowe
- **WHEN** oczekiwany stan portfela na 2026-10-11 wynosi 900,00 zł, a użytkownik wpisuje faktyczny stan 340,00 zł
- **THEN** system zapisuje wydatek 560,00 zł w kategorii "Gotówka (bez kategorii)" z datą 2026-10-11, a oczekiwany stan wynosi 340,00 zł

#### Scenario: Stan zgodny
- **WHEN** faktyczny stan portfela jest równy oczekiwanemu
- **THEN** system nie tworzy żadnego wydatku

### Requirement: Nadwyżka w portfelu
Jeśli faktyczny stan portfela jest wyższy od oczekiwanego, system SHALL NOT automatycznie uznawać nadwyżki za dochód. Nadwyżka SHALL trafić do skrzynki, gdzie użytkownik decyduje, czy to niezapisany dochód gotówkowy (podlegający podziałowi), czy neutralna korekta stanu.

#### Scenario: Więcej gotówki niż oczekiwano
- **WHEN** oczekiwany stan wynosi 300,00 zł, a użytkownik wpisuje faktyczny stan 450,00 zł
- **THEN** w skrzynce pojawia się pozycja 150,00 zł do decyzji: dochód gotówkowy albo korekta, i do czasu decyzji nie wchodzi ona do podziału
