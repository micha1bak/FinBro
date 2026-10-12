# Spec Delta

## Purpose

Odpowiada na pytanie, ile użytkownik zarabia i wydaje w ujęciu tygodniowym, miesięcznym i rocznym, z podziałem na kategorie i sprzedawców. Przychody i wydatki liczone są według jednoznacznych reguł, w których przesunięcia własnych pieniędzy nie udają ani dochodu, ani wydatku.

## ADDED Requirements

### Requirement: Okresy raportowe
System SHALL prezentować raporty w okresach: tydzień (poniedziałek–niedziela, numeracja ISO 8601), miesiąc kalendarzowy i rok kalendarzowy. Transakcja należy do okresu według swojej daty transakcji. Użytkownik SHALL móc przechodzić do poprzednich i następnych okresów.

#### Scenario: Płatność z soboty zaksięgowana w poniedziałek
- **WHEN** płatność kartą ma datę transakcji 2026-10-31 i datę księgowania 2026-11-02
- **THEN** jest liczona w październiku 2026 i w tygodniu 2026-T44

### Requirement: Definicja przychodów
Przychody okresu SHALL być sumą zatwierdzonych transakcji typu DOCHÓD, bankowych i gotówkowych. Wpływy typów TRANSFER, SPŁATA, ZWROT i ROZLICZENIE SHALL NOT być liczone jako przychody.

#### Scenario: Refundacja i spłata nie są przychodem
- **WHEN** w tygodniu wpłynęły: dochód 705,87 zł, refundacja budżetu rodzinnego 477,08 zł i spłata pożyczki 500,00 zł
- **THEN** przychody tygodnia wynoszą 705,87 zł

### Requirement: Definicja wydatków
Wydatki okresu SHALL być sumą transakcji typu WYDATEK (bankowych i gotówkowych, w tym różnic z inwentaryzacji portfela) i darowanych kwot należności, pomniejszoną o transakcje typu ZWROT i ROZLICZENIE. Transakcje typów ODKŁADANIE, TRANSFER i POŻYCZKA SHALL NOT być liczone jako wydatki.

#### Scenario: Odkładanie nie jest wydatkiem
- **WHEN** w tygodniu były wydatki kartą 200,00 zł, przelew "FinBro 2026-T41 Wakacje" 1237,50 zł i wypłata z bankomatu 2300,00 zł
- **THEN** wydatki tygodnia wynoszą 200,00 zł

#### Scenario: Rozliczenie wspólnego wydatku
- **WHEN** użytkownik zapłacił 200,00 zł w kategorii Restauracje i na mieście, a znajomi oddali 150,00 zł sklasyfikowane jako ROZLICZENIE w tej kategorii
- **THEN** wydatki w kategorii Restauracje i na mieście wynoszą 50,00 zł

### Requirement: Podsumowanie okresu
Dla wybranego okresu system SHALL pokazywać przychody, wydatki i ich różnicę (bilans).

#### Scenario: Bilans miesiąca
- **WHEN** w październiku 2026 przychody wynoszą 9000,00 zł, a wydatki 5200,00 zł
- **THEN** raport miesięczny pokazuje przychody 9000,00 zł, wydatki 5200,00 zł i bilans 3800,00 zł

### Requirement: Trend w kolejnych okresach
System SHALL pokazywać wykres przychodów i wydatków dla kolejnych okresów wybranego rodzaju (tygodnie, miesiące albo lata), kończący się na wybranym okresie.

#### Scenario: Trend tygodniowy
- **WHEN** użytkownik wybiera widok tygodniowy dla 2026-T41
- **THEN** widzi przychody i wydatki dla tygodnia 2026-T41 i tygodni poprzedzających

### Requirement: Wydatki według kategorii
Dla wybranego okresu system SHALL pokazywać wydatki w podziale na kategorie, w tym kategorię systemową "Gotówka (bez kategorii)", z kwotą i udziałem procentowym każdej kategorii.

#### Scenario: Podział na kategorie
- **WHEN** w tygodniu wydatki wynoszą 150,00 zł w kategorii Spożywcze i 50,00 zł w kategorii Transport
- **THEN** raport pokazuje Spożywcze 150,00 zł (75%) i Transport 50,00 zł (25%)

### Requirement: Wydatki według sprzedawców
Dla wybranego okresu system SHALL pokazywać sprzedawców i kontrahentów z największą sumą wydatków.

#### Scenario: Najwięcej wydane w sklepie
- **WHEN** w październiku najwięcej wydano u sprzedawcy "JMP S.A. BIEDRONKA 2422"
- **THEN** jest on pierwszy na liście sprzedawców w raporcie październikowym

### Requirement: Oznaczenie niepełnych danych
Gdy w okresie są transakcje o statusie "do klasyfikacji" albo niezatwierdzone wpływy, raport SHALL to wyraźnie sygnalizować, podając ich liczbę i łączną kwotę, i SHALL NOT wliczać ich do przychodów ani wydatków.

#### Scenario: Niezatwierdzony wpływ w okresie
- **WHEN** w tygodniu jest niezatwierdzony wpływ 477,08 zł
- **THEN** raport tygodniowy informuje o 1 niezatwierdzonej pozycji na 477,08 zł i nie wlicza jej do przychodów
