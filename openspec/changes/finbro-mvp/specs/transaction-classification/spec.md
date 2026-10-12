# Spec Delta

## Purpose

Nadaje każdej transakcji typ i, tam gdzie trzeba, kategorię lub dłużnika. Od tego zależy, co jest dzielone w rozliczeniu i co liczy się w analityce. Klasyfikacja ma przy tym chronić przed przypadkowym podziałem wpływu, który nie jest dochodem.

## ADDED Requirements

### Requirement: Typy transakcji
Każda transakcja SHALL mieć dokładnie jeden typ: DOCHÓD, WYDATEK, ODKŁADANIE, TRANSFER, ZWROT, ROZLICZENIE, POŻYCZKA albo SPŁATA. Transakcja bez ostatecznego typu ma status "do klasyfikacji". Typy DOCHÓD, ZWROT, ROZLICZENIE i SPŁATA dotyczą wpływów, a WYDATEK, ODKŁADANIE i POŻYCZKA wydatków. TRANSFER może dotyczyć obu kierunków.

#### Scenario: Niezgodność typu z kierunkiem
- **WHEN** użytkownik próbuje oznaczyć wydatek z konta jako DOCHÓD
- **THEN** system odrzuca zmianę z komunikatem o niezgodności typu z kierunkiem operacji

### Requirement: Kategorie wydatków
System SHALL prowadzić płaską (jednopoziomową) listę kategorii, początkowo: Spożywcze, Restauracje i na mieście, Transport, Mieszkanie, Abonamenty i subskrypcje, Zdrowie, Ubrania, Dom i wyposażenie, Rozrywka i hobby, Prezenty, Edukacja, Podróże, Inne oraz systemową "Gotówka (bez kategorii)". Użytkownik SHALL móc dodawać, zmieniać nazwy i dezaktywować kategorie poza systemową. Kategoria systemowa nie jest dostępna do ręcznego wyboru.

#### Scenario: Dodanie kategorii
- **WHEN** użytkownik dodaje kategorię "Zwierzęta"
- **THEN** kategoria jest dostępna przy klasyfikacji i w raportach

#### Scenario: Dezaktywacja używanej kategorii
- **WHEN** użytkownik dezaktywuje kategorię, do której są przypisane transakcje
- **THEN** istniejące transakcje zachowują tę kategorię i nadal są w raportach, ale nie można jej wybrać dla nowych transakcji

### Requirement: Kategoria dla typów wpływających na wydatki
Transakcje typu WYDATEK, ZWROT i ROZLICZENIE SHALL mieć przypisaną kategorię. Transakcje typu POŻYCZKA i SPŁATA SHALL mieć przypisanego dłużnika.

#### Scenario: Zwrot za zakupy
- **WHEN** wpływ ze sklepu zostaje sklasyfikowany jako ZWROT
- **THEN** system wymaga wskazania kategorii, w której zwrot pomniejszy wydatki

### Requirement: Kolejność warstw klasyfikacji
System SHALL klasyfikować nową transakcję w kolejności: reguły, potem historia kontrahenta, potem lokalny model językowy. Pierwsza warstwa, która da wynik, wyznacza propozycję, a każda propozycja SHALL mieć zapisane źródło (reguła, historia, LLM, użytkownik).

#### Scenario: Transakcja dopasowana regułą
- **WHEN** transakcja pasuje do reguły użytkownika
- **THEN** system używa propozycji z reguły i nie wysyła transakcji do modelu językowego

### Requirement: Reguły klasyfikacji
Użytkownik SHALL móc definiować reguły z warunkami na kierunek, typ operacji bankowej, nazwę i rachunek kontrahenta, tytuł, sprzedawcę i zakres kwot oraz z wynikiem: typ, kategoria lub dłużnik. System SHALL dostarczać edytowalne reguły początkowe: wypłata z bankomatu i wpłata gotówki jako TRANSFER Portfela, doładowanie Revoluta kartą jako TRANSFER (budżet rodzinny) oraz tytuł z oznaczeniem FinBro jako ODKŁADANIE.

#### Scenario: Doładowanie Revoluta kartą
- **WHEN** zaimportowana jest operacja "Przelew z karty" z lokalizacją zawierającą "Revolut"
- **THEN** transakcja dostaje typ TRANSFER (budżet rodzinny) i nie jest ani wydatkiem, ani odkładaniem

#### Scenario: Refundacja od rodziny
- **WHEN** istnieje reguła "wpływ od nadawcy X = TRANSFER (budżet rodzinny)" i wpływa przelew od X
- **THEN** wpływ dostaje typ TRANSFER, nie jest dochodem i nie podlega podziałowi

### Requirement: Podpowiedź z historii kontrahenta
Gdy żadna reguła nie pasuje, a ten sam kontrahent (rachunek lub nazwa) albo sprzedawca ma wcześniej zatwierdzone transakcje w tym samym kierunku, system SHALL zaproponować typ i kategorię z ostatniej takiej transakcji.

#### Scenario: Znany sprzedawca
- **WHEN** nowa płatność kartą dotyczy sprzedawcy "JMP S.A. BIEDRONKA 2422", a poprzednia zatwierdzona płatność u niego miała kategorię Spożywcze
- **THEN** system proponuje WYDATEK w kategorii Spożywcze bez użycia modelu językowego

### Requirement: Klasyfikacja lokalnym modelem językowym
Transakcje bez propozycji z reguł i historii SHALL być klasyfikowane przez model językowy działający lokalnie, w tle, bez blokowania importu ani interfejsu. Model SHALL zwracać typ, kategorię lub dłużnika i krótkie uzasadnienie, wybierając wyłącznie spośród dozwolonych typów, aktywnych kategorii i istniejących dłużników.

#### Scenario: Klasyfikacja w tle
- **WHEN** import dodał transakcje bez propozycji z reguł i historii
- **THEN** import kończy się od razu, a propozycje modelu pojawiają się przy tych transakcjach w skrzynce stopniowo, w miarę ich wyliczania

#### Scenario: Model niedostępny
- **WHEN** lokalny serwer modelu nie działa albo zwraca błąd
- **THEN** transakcje trafiają do skrzynki bez propozycji, a reszta aplikacji działa normalnie

### Requirement: Minimalizacja danych dla modelu
Do modelu językowego system SHALL przekazywać wyłącznie typ operacji bankowej, kierunek, kwotę, datę, nazwę kontrahenta lub sprzedawcy, tytuł oraz listy kategorii i dłużników. System SHALL NOT przekazywać numerów rachunków, numerów telefonów, numerów kart ani sald. Dane SHALL NOT opuszczać komputera użytkownika.

#### Scenario: Usunięcie danych wrażliwych
- **WHEN** opis transakcji zawiera numer rachunku odbiorcy i numer telefonu
- **THEN** dane wysłane do modelu nie zawierają ani numeru rachunku, ani numeru telefonu

### Requirement: Obowiązkowe zatwierdzanie dochodu
Wpływ SHALL stać się DOCHODEM wyłącznie po zatwierdzeniu przez użytkownika, niezależnie od źródła propozycji. Wpływ bez ostatecznego typu SHALL NOT podlegać podziałowi. System SHALL umożliwiać zbiorcze zatwierdzenie propozycji dochodu pochodzących z reguł.

#### Scenario: Propozycja dochodu od modelu
- **WHEN** model proponuje dla wpływu typ DOCHÓD
- **THEN** wpływ pozostaje w skrzynce jako niezatwierdzony i nie wchodzi do rozliczenia, dopóki użytkownik go nie zatwierdzi

### Requirement: Automatyczna akceptacja pozostałych propozycji
Propozycje dla wydatków oraz propozycje typów neutralnych z reguł SHALL być przyjmowane automatycznie. Propozycje dla wpływów inne niż z reguł (z historii albo od modelu) SHALL wymagać zatwierdzenia w skrzynce. Użytkownik SHALL móc później zmienić klasyfikację każdej transakcji.

#### Scenario: Wydatek skategoryzowany przez model
- **WHEN** model proponuje dla płatności kartą WYDATEK w kategorii Rozrywka i hobby
- **THEN** transakcja jest od razu sklasyfikowana i widoczna w raportach, a użytkownik może ją poprawić

### Requirement: Skrzynka do zatwierdzania
System SHALL pokazywać skrzynkę z transakcjami i pozycjami wymagającymi decyzji, wraz z propozycją, jej źródłem i uzasadnieniem modelu. Użytkownik SHALL móc przyjąć propozycję jednym działaniem albo wybrać inny typ, kategorię lub dłużnika.

#### Scenario: Przyjęcie propozycji
- **WHEN** użytkownik przyjmuje propozycję dla pozycji w skrzynce
- **THEN** transakcja dostaje zaproponowany typ jako ostateczny i znika ze skrzynki

### Requirement: Utworzenie reguły z decyzji
Przy decyzji w skrzynce lub przy poprawce klasyfikacji użytkownik SHALL móc zapisać decyzję jako regułę dla tego kontrahenta lub sprzedawcy. Taka reguła SHALL obowiązywać dla transakcji importowanych później.

#### Scenario: Zapamiętanie kontrahenta
- **WHEN** użytkownik zatwierdza wpływ od kancelarii jako DOCHÓD z zaznaczoną opcją "zapamiętaj jako regułę"
- **THEN** kolejne wpływy od tego kontrahenta dostają propozycję DOCHÓD z reguły

### Requirement: Podpowiedź spłaty od dłużnika
Gdy wpływ pochodzi od osoby, która ma niezerowe saldo należności, system SHALL zaproponować typ SPŁATA z tym dłużnikiem jako jedną z opcji w skrzynce.

#### Scenario: Wpływ od dłużnika
- **WHEN** wpływa przelew od osoby, której saldo należności wynosi 1290,00 zł
- **THEN** skrzynka pokazuje propozycję SPŁATA od tej osoby wraz z jej bieżącym saldem
