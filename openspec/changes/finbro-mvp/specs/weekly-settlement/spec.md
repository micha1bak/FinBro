# Spec Delta

## Purpose

Co tydzień dzieli zatwierdzone dochody poprzedniego tygodnia na koperty według obowiązujących proporcji i generuje listę przelewów do wykonania. Pilnuje też, żeby żadna należna kwota nie zginęła: niedopłaty, nadpłaty i spóźnione dochody przechodzą na kolejne tygodnie.

## ADDED Requirements

### Requirement: Koperty i datowane proporcje
System SHALL prowadzić koperty Życie, XTB, Obligacje i Wakacje z udziałami procentowymi, które razem dają 100%. Każdy zestaw udziałów ma datę obowiązywania od. Początkowy zestaw to 50% / 12,5% / 12,5% / 25%. Dla każdej koperty poza Życiem system SHALL przechowywać nazwę i numer rachunku docelowego.

#### Scenario: Nieprawidłowa suma udziałów
- **WHEN** użytkownik zapisuje zestaw udziałów, który sumuje się do 95%
- **THEN** system odrzuca zapis z komunikatem o wymaganej sumie 100%

#### Scenario: Zmiana proporcji nie zmienia przeszłości
- **WHEN** od 2026-11-02 obowiązuje nowy zestaw udziałów
- **THEN** dochody z datą wcześniejszą niż 2026-11-02 są dzielone według poprzedniego zestawu, a już zamknięte rozliczenia się nie zmieniają

### Requirement: Data startu
System SHALL mieć konfigurowalną datę startu rozliczeń. Dochody z datą transakcji wcześniejszą niż data startu SHALL NOT podlegać podziałowi, ale SHALL być uwzględniane w raportach.

#### Scenario: Import historii sprzed startu
- **WHEN** data startu to 2026-10-12, a użytkownik importuje wyciąg od 2026-01-01
- **THEN** dochody sprzed 2026-10-12 są widoczne w raportach, ale nie pojawiają się w żadnym rozliczeniu

### Requirement: Tydzień rozliczeniowy
Tydzień rozliczeniowy SHALL trwać od poniedziałku do niedzieli, zgodnie z numeracją tygodni ISO 8601. Dochód należy do tygodnia, w którym przypada jego data transakcji. Rozliczenie tygodnia SHALL być dostępne dopiero po jego zakończeniu.

#### Scenario: Rozliczenie w poniedziałek
- **WHEN** w poniedziałek 2026-10-12 użytkownik otwiera rozliczenie
- **THEN** system proponuje rozliczenie tygodnia 2026-T41 (2026-10-05 – 2026-10-11)

#### Scenario: Tydzień w trakcie
- **WHEN** użytkownik próbuje zamknąć rozliczenie tygodnia, który jeszcze trwa
- **THEN** system nie pozwala go zamknąć

### Requirement: Wyliczenie kwot należnych
Dla tygodnia system SHALL zsumować zatwierdzone dochody (bankowe i gotówkowe) przypisane do tego tygodnia i wyliczyć kwotę dla każdej koperty poza Życiem jako udział od sumy, zaokrąglony w dół do pełnego grosza. Życie dostaje resztę, więc suma kopert jest dokładnie równa sumie dochodów.

#### Scenario: Podział z zaokrągleniem
- **WHEN** zatwierdzone dochody tygodnia wynoszą łącznie 4950,03 zł przy udziałach 50/12,5/12,5/25
- **THEN** XTB dostaje 618,75 zł, Obligacje 618,75 zł, Wakacje 1237,50 zł, a Życie 2475,03 zł

### Requirement: Uwzględnianie spóźnionych zmian
Dochód zatwierdzony po zamknięciu rozliczenia swojego tygodnia albo zmiana klasyfikacji dochodu z zamkniętego tygodnia SHALL wejść do najbliższego niezamkniętego rozliczenia jako korekta (dodatnia albo ujemna). Zamknięte rozliczenie SHALL NOT się zmieniać.

#### Scenario: Późno zatwierdzony dochód
- **WHEN** rozliczenie T41 jest zamknięte, a użytkownik zatwierdza dochód 1000,00 zł z datą w T41
- **THEN** T41 się nie zmienia, a rozliczenie T42 zawiera korektę z dochodem 1000,00 zł, dzieloną według udziałów obowiązujących w dniu tego dochodu

#### Scenario: Wycofanie dochodu
- **WHEN** w zamkniętym T41 dochód 400,00 zł zostaje przeklasyfikowany jako SPŁATA
- **THEN** rozliczenie T42 zawiera ujemną korektę odpowiadającą podziałowi 400,00 zł

### Requirement: Przeniesienia między tygodniami
Dla każdej koperty poza Życiem różnica między kwotą do przelania a sumą przelewów przypisanych do rozliczenia SHALL przechodzić na kolejne rozliczenie: niedopłata zwiększa, a nadpłata zmniejsza kwotę do przelania w następnym tygodniu.

#### Scenario: Przelew zaokrąglony w dół
- **WHEN** w T41 do przelania na Wakacje było 1237,50 zł, a użytkownik przelał 1200,00 zł
- **THEN** rozliczenie T42 zawiera dla Wakacji przeniesienie +37,50 zł

#### Scenario: Nadpłata
- **WHEN** w T41 do przelania na XTB było 618,75 zł, a użytkownik przelał 700,00 zł
- **THEN** rozliczenie T42 zawiera dla XTB przeniesienie -81,25 zł

### Requirement: Lista przelewów
Po zamknięciu rozliczenia system SHALL pokazać dla każdej koperty poza Życiem przelew do wykonania: rachunek docelowy, kwotę (należność tygodnia + korekty + przeniesienie) i tytuł w formacie `FinBro <rok>-T<numer tygodnia> <koperta>`. Koperta o kwocie zerowej lub ujemnej SHALL NOT mieć przelewu, a ujemna kwota przechodzi jako przeniesienie na kolejny tydzień.

#### Scenario: Lista po zamknięciu
- **WHEN** użytkownik zamyka rozliczenie T41 z kwotami XTB 618,75 zł, Obligacje 618,75 zł i Wakacje 1237,50 zł
- **THEN** widzi trzy przelewy, m.in. 1237,50 zł na rachunek Revoluta z tytułem "FinBro 2026-T41 Wakacje"

### Requirement: Automatyczne rozpoznanie wykonanych przelewów
System SHALL rozpoznawać w importowanych wydatkach z konta głównego przelewy z tytułem w formacie FinBro, klasyfikować je jako ODKŁADANIE i przypisywać do wskazanego rozliczenia i koperty. Przelew na rachunek docelowy koperty bez rozpoznawalnego tytułu SHALL być klasyfikowany jako ODKŁADANIE i przypisany do najstarszego nierozliczonego rozliczenia tej koperty.

#### Scenario: Przelew z tytułem FinBro
- **WHEN** import zawiera przelew 1237,50 zł z tytułem "FinBro 2026-T41 Wakacje"
- **THEN** przelew jest klasyfikowany jako ODKŁADANIE i zaliczony na kopertę Wakacje rozliczenia T41

#### Scenario: Przelew bez tytułu na rachunek koperty
- **WHEN** import zawiera przelew na rachunek docelowy koperty XTB bez tytułu FinBro
- **THEN** przelew jest klasyfikowany jako ODKŁADANIE i zaliczony na kopertę XTB najstarszego nierozliczonego rozliczenia

### Requirement: Status rozliczenia
Rozliczenie SHALL mieć status: otwarte (przed zamknięciem), zamknięte (lista przelewów wygenerowana) albo rozliczone (każdy przelew z listy ma przypisane przelewy pokrywające co najmniej jego kwotę).

#### Scenario: Wszystkie przelewy wykonane
- **WHEN** do zamkniętego rozliczenia T41 przypisano przelewy pokrywające wszystkie trzy kwoty
- **THEN** rozliczenie T41 ma status rozliczone

### Requirement: Ostrzeżenia przed zamknięciem
Przed zamknięciem rozliczenia system SHALL ostrzec, jeśli tydzień nie jest w pełni pokryty importami konta głównego, jeśli w skrzynce są niezatwierdzone wpływy z tego tygodnia albo jeśli nie wykonano inwentaryzacji portfela na koniec tego tygodnia. Ostrzeżenia nie blokują zamknięcia.

#### Scenario: Niezatwierdzone wpływy
- **WHEN** użytkownik zamyka rozliczenie T41, a w skrzynce są dwa niezatwierdzone wpływy z T41
- **THEN** system ostrzega o dwóch niezatwierdzonych wpływach i pozwala zamknąć rozliczenie po potwierdzeniu
