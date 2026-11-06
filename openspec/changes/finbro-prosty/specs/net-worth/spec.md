# Spec Delta

## Purpose

Bieżący obraz majątku na kontach PKO, Gotówka, Fundusz wakacyjny, XTB i Obligacje: salda wyliczane z rozliczonych przelewów, korygowane wpisanym saldem faktycznym, z sumą i wykresem w czasie.

## ADDED Requirements

### Requirement: Wpis salda faktycznego
System SHALL pozwalać wpisać faktyczne saldo konta PKO, Gotówka, Fundusz wakacyjny, XTB albo Obligacje na wybrany dzień, także z przeszłości. Kwota MUST być nieujemna. Kolejny wpis dla tego samego konta i dnia zastępuje poprzedni.

#### Scenario: Saldo początkowe
- **WHEN** użytkownik wpisuje saldo XTB 1200,00 zł na 2026-10-12
- **THEN** saldo XTB od tego dnia wynosi 1200,00 zł

### Requirement: Saldo wyliczane Funduszu wakacyjnego, XTB i Obligacji
System SHALL wyliczać saldo Funduszu wakacyjnego (z koperty Wakacje), XTB i Obligacji na dany dzień jako ostatnie saldo faktyczne z tego dnia lub wcześniejsze powiększone o kwoty rozliczeń tej koperty z datą późniejszą niż to saldo, a nie późniejszą niż dany dzień. Bez salda faktycznego saldo to suma wszystkich takich rozliczeń.

#### Scenario: Przelew po wpisaniu salda
- **WHEN** saldo XTB z 2026-10-12 to 1200,00 zł, a rozliczenie z 2026-10-19 przelało na XTB 322 zł
- **THEN** saldo XTB na 2026-10-19 wynosi 1522,00 zł

#### Scenario: Przelew przed saldem nie liczy się podwójnie
- **WHEN** rozliczenie z 2026-10-19 przelało na XTB 322 zł, a saldo faktyczne z 2026-10-20 to 1550,00 zł
- **THEN** saldo XTB na 2026-10-20 wynosi 1550,00 zł

### Requirement: Różnica między wyliczeniem a saldem faktycznym
System SHALL przy wpisie salda faktycznego XTB albo Obligacji pokazać różnicę względem salda wyliczonego na ten dzień jako zysk (dodatnia) albo stratę (ujemna), a przy wpisie salda Funduszu wakacyjnego jako dopłatę (dodatnia) albo wypłatę (ujemna).

#### Scenario: Zysk z inwestycji
- **WHEN** saldo wyliczone XTB na 2026-11-01 to 1522,00 zł, a użytkownik wpisuje 1560,00 zł
- **THEN** system pokazuje różnicę +38,00 zł

### Requirement: Saldo PKO i Gotówki tylko ręcznie
System SHALL pokazywać saldo PKO i saldo Gotówki wyłącznie jako ostatnie wpisane saldo faktyczne, bez doliczania dochodów, bo oba salda zmieniają wydatki, których aplikacja nie zna.

#### Scenario: Dochód nie zmienia salda PKO
- **WHEN** ostatnie saldo PKO to 3000,00 zł, a później wpisano i rozliczono dochód z częścią PKO 86 zł
- **THEN** saldo PKO nadal wynosi 3000,00 zł

#### Scenario: Dochód w gotówce nie zmienia salda Gotówki
- **WHEN** ostatnie saldo Gotówki to 250,00 zł, a później wpisano dochód 174,00 zł w gotówce
- **THEN** saldo Gotówki nadal wynosi 250,00 zł

### Requirement: Suma i wykres majątku
System SHALL pokazywać bieżące saldo każdego z kont PKO, Gotówka, Fundusz wakacyjny, XTB i Obligacje, ich sumę z datą ostatniej aktualizacji oraz wykres sumy w czasie z punktami w dniach wpisów sald i rozliczeń. Wpis salda z datą w przeszłości zmienia punkty wykresu i różnice od tego dnia.

#### Scenario: Bieżąca suma
- **WHEN** salda wynoszą PKO 3000,00 zł, Gotówka 250,00 zł, Fundusz wakacyjny 1144,00 zł, XTB 1522,00 zł i Obligacje 1410,25 zł
- **THEN** majątek wynosi 7326,25 zł

#### Scenario: Saldo funduszu wpisane z datą w przeszłości
- **WHEN** salda pozostałych kont wpisano 2026-10-14 i 2026-10-19, a użytkownik dopisuje saldo Funduszu wakacyjnego na oba te dni
- **THEN** oba punkty wykresu zawierają fundusz, a wpis z 2026-10-19 pokazuje różnicę względem wpisu z 2026-10-14 powiększonego o rozliczone przelewy

#### Scenario: Brak danych
- **WHEN** nie wpisano żadnego salda i nie ma rozliczeń
- **THEN** widok zachęca do wpisania sald początkowych zamiast pokazywać pusty wykres
