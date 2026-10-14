# Spec Delta

## Purpose

Rejestr ręcznie wpisywanych dochodów i ich podział na koperty (PKO, Wakacje, XTB, Obligacje) według planu procentowego obowiązującego w dniu dochodu, jak w arkuszu użytkownika.

## ADDED Requirements

### Requirement: Wpisywanie dochodu
System SHALL pozwalać wpisać dochód z datą, źródłem (dowolny tekst) i kwotą w złotych z groszami. Kwota MUST być większa od zera, a data i źródło są wymagane.

#### Scenario: Poprawny wpis
- **WHEN** użytkownik wpisuje dochód z 2026-10-14, źródło „Zlecenie”, kwota „174,00”
- **THEN** dochód pojawia się na liście dochodów jako nierozliczony, z wyliczonym podziałem na koperty

#### Scenario: Niepoprawna kwota
- **WHEN** użytkownik wpisuje kwotę „0”, ujemną albo niebędącą liczbą
- **THEN** system odrzuca wpis z komunikatem, a lista dochodów się nie zmienia

### Requirement: Forma dochodu
System SHALL zapisywać przy każdym dochodzie formę: wpływ na PKO albo gotówka, domyślnie PKO. Forma jest widoczna na liście dochodów i można ją zmienić przy poprawianiu nierozliczonego dochodu. Forma nie zmienia podziału ani listy przelewów.

#### Scenario: Dochód w gotówce
- **WHEN** użytkownik wpisuje dochód 174,00 zł z formą „gotówka”
- **THEN** lista pokazuje go z formą „gotówka” i z tym samym podziałem co dochód na PKO

#### Scenario: Forma domyślna
- **WHEN** użytkownik wpisuje dochód bez zmiany formy
- **THEN** dochód ma formę PKO

### Requirement: Podział dochodu na koperty
System SHALL dzielić każdy dochód według planu obowiązującego w dniu dochodu. Kwota każdej koperty poza PKO to iloczyn kwoty i udziału zaokrąglony do pełnych złotych (połówki w górę). PKO dostaje resztę, więc suma podziału zawsze równa się kwocie dochodu, co do grosza.

#### Scenario: Podział z groszami
- **WHEN** dochód wynosi 2401,30 zł przy planie PKO 50%, Wakacje 25%, XTB 12,5%, Obligacje 12,5%
- **THEN** podział to Wakacje 600 zł (600,325), XTB 300 zł (300,1625), Obligacje 300 zł i PKO 1201,30 zł

#### Scenario: Zaokrąglenie połówek
- **WHEN** dochód wynosi 174,00 zł przy tym samym planie
- **THEN** podział to Wakacje 44 zł (43,50), XTB 22 zł (21,75), Obligacje 22 zł i PKO 86 zł

### Requirement: Plan podziału z datą obowiązywania
System SHALL przechowywać plan podziału jako udziały procentowe kopert PKO, Wakacje, XTB i Obligacje, których suma MUST wynosić 100%. Nowy plan obowiązuje od wskazanej daty i SHALL zmieniać podział wyłącznie nierozliczonych dochodów z tą datą lub późniejszą.

#### Scenario: Plan startowy
- **WHEN** aplikacja startuje z pustą bazą
- **THEN** obowiązuje plan PKO 50%, Wakacje 25%, XTB 12,5%, Obligacje 12,5%

#### Scenario: Zmiana planu
- **WHEN** użytkownik zapisuje plan PKO 60%, Wakacje 20%, XTB 10%, Obligacje 10% od 2026-11-01
- **THEN** dochody z 2026-11-01 i później są dzielone według nowego planu, a wcześniejsze według poprzedniego

#### Scenario: Udziały nie sumują się do 100%
- **WHEN** użytkownik zapisuje plan, którego udziały sumują się do 95%
- **THEN** system odrzuca plan z komunikatem

#### Scenario: Rozliczony dochód zachowuje podział
- **WHEN** nowy plan obowiązuje od daty wcześniejszej niż data rozliczonego dochodu
- **THEN** podział rozliczonego dochodu się nie zmienia

### Requirement: Poprawianie i usuwanie dochodu
System SHALL pozwalać poprawić datę, źródło i kwotę nierozliczonego dochodu oraz usunąć go. Dochodu rozliczonego MUST NOT dać się zmienić ani usunąć, dopóki jego rozliczenie nie zostanie cofnięte.

#### Scenario: Poprawka nierozliczonego dochodu
- **WHEN** użytkownik zmienia kwotę nierozliczonego dochodu ze 174,00 na 210,00 zł
- **THEN** podział jest przeliczony dla nowej kwoty

#### Scenario: Próba zmiany rozliczonego dochodu
- **WHEN** użytkownik próbuje zmienić albo usunąć rozliczony dochód
- **THEN** system odmawia z informacją, że najpierw trzeba cofnąć rozliczenie

### Requirement: Lista dochodów
System SHALL pokazywać listę dochodów od najnowszych, z datą, źródłem, kwotą, podziałem na koperty i statusem (rozliczony albo nierozliczony), oraz sumę dochodów, sumę każdej koperty i sumę każdej formy dochodu w wybranym miesiącu.

#### Scenario: Podsumowanie miesiąca
- **WHEN** w październiku 2026 są dochody 2401,30 zł i 174,00 zł
- **THEN** widok października pokazuje sumę 2575,30 zł oraz sumy kopert Wakacje 644 zł, XTB 322 zł, Obligacje 322 zł i PKO 1287,30 zł

#### Scenario: Sumy według formy
- **WHEN** w październiku 2026 jest dochód 2401,30 zł na PKO i 174,00 zł w gotówce
- **THEN** widok października pokazuje osobno sumę wpływów na PKO 2401,30 zł i sumę gotówki 174,00 zł
