# Spec Delta

## Purpose

Pokazuje, kto i ile jest winien użytkownikowi z tytułu pożyczonych pieniędzy, ze spłatami częściowymi i możliwością darowania długu. Same pożyczki i spłaty nie zniekształcają przy tym ani podziału dochodów, ani analityki wydatków.

## ADDED Requirements

### Requirement: Dłużnicy i saldo
System SHALL prowadzić listę dłużników (osób). Saldo dłużnika to suma pożyczek minus suma spłat i darowanych kwot. Saldo SHALL NOT być ujemne. System nie śledzi długów użytkownika wobec innych.

#### Scenario: Saldo po pożyczce i spłacie
- **WHEN** użytkownik pożyczył Kubie 200,00 zł, a Kuba oddał 50,00 zł
- **THEN** saldo Kuby wynosi 150,00 zł

### Requirement: Rejestrowanie pożyczki
Pożyczka SHALL powstawać z wydatku z konta głównego sklasyfikowanego jako POŻYCZKA z dłużnikiem albo z ręcznego wpisu pożyczki gotówkowej, który zmniejsza oczekiwany stan Portfela. Pożyczka zwiększa saldo dłużnika i nie jest wydatkiem.

#### Scenario: Pożyczka BLIK-iem
- **WHEN** wydatek 645,00 zł przez BLIK zostaje sklasyfikowany jako POŻYCZKA dla Martyny
- **THEN** saldo Martyny rośnie o 645,00 zł, a raporty nie wykazują wydatku 645,00 zł

#### Scenario: Pożyczka gotówką
- **WHEN** użytkownik wpisuje pożyczkę gotówkową 200,00 zł dla Kuby
- **THEN** saldo Kuby rośnie o 200,00 zł, a oczekiwany stan Portfela maleje o 200,00 zł

### Requirement: Rejestrowanie spłaty
Spłata SHALL powstawać z wpływu na konto główne sklasyfikowanego jako SPŁATA z dłużnikiem albo z ręcznego wpisu spłaty gotówkowej, który zwiększa oczekiwany stan Portfela. Spłata może być częściowa, zmniejsza saldo dłużnika, nie jest dochodem i SHALL NOT podlegać podziałowi.

#### Scenario: Częściowa spłata przelewem
- **WHEN** Martyna z saldem 1290,00 zł przelewa 500,00 zł, a wpływ zostaje sklasyfikowany jako SPŁATA
- **THEN** saldo Martyny wynosi 790,00 zł, a wpływ nie wchodzi do rozliczenia tygodnia

### Requirement: Spłata większa niż saldo
System SHALL odrzucić zarejestrowanie spłaty, której kwota przekracza bieżące saldo dłużnika, z komunikatem podającym to saldo.

#### Scenario: Za duża spłata
- **WHEN** użytkownik próbuje sklasyfikować wpływ 300,00 zł jako SPŁATĘ od Kuby z saldem 150,00 zł
- **THEN** system odrzuca klasyfikację i informuje, że saldo Kuby wynosi 150,00 zł

### Requirement: Darowanie długu
Użytkownik SHALL móc darować dłużnikowi całość lub część salda. Darowana kwota zmniejsza saldo i SHALL być wydatkiem w wybranej kategorii, datowanym na dzień darowania.

#### Scenario: Darowanie reszty długu
- **WHEN** 2026-11-15 użytkownik daruje Kubie pozostałe 150,00 zł, wybierając kategorię Prezenty
- **THEN** saldo Kuby wynosi 0,00 zł, a raporty wykazują wydatek 150,00 zł w kategorii Prezenty z datą 2026-11-15

### Requirement: Zestawienie należności
System SHALL pokazywać listę dłużników z niezerowym saldem, z kwotą salda i datą najstarszej niespłaconej pożyczki, sumę wszystkich należności oraz historię pożyczek, spłat i darowań każdego dłużnika.

#### Scenario: Przegląd należności
- **WHEN** użytkownik otwiera zestawienie należności, a Martyna ma saldo 1290,00 zł i Kuba 150,00 zł
- **THEN** widzi oba salda, daty najstarszych niespłaconych pożyczek i sumę 1440,00 zł
