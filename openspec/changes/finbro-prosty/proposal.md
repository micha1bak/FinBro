# Propozycja: FinBro w wersji prostej

## Dlaczego

Pierwsza wersja FinBro (zmiana `finbro-mvp`) okazała się przeinżynierowana. Użytkownik po pierwszym imporcie wyciągu nie potrafił się w niej odnaleźć ani sprawdzić, czy wyniki są poprawne. Jego faktyczna potrzeba to zastąpienie arkusza „Finanse osobiste.xlsx” wygodnym interfejsem. Arkusz robi trzy rzeczy: dzieli ręcznie wpisane dochody na koperty według stałych proporcji, pozwala oznaczyć przelewy jako rozliczone i przechowuje okresowe salda kont oszczędnościowych. Większość funkcji pierwszej wersji (import wyciągów, klasyfikacja wydatków, skrzynka, reguły, model językowy, portfel gotówki, należności, raporty wydatków, tygodniowe rozliczenia z korektami) nie odpowiada na tę potrzebę.

## Co się zmienia

- Dochody wpisywane ręcznie (data, źródło, kwota), z możliwością poprawienia i usunięcia wpisu.
- Automatyczny podział każdego dochodu według planu PKO (Życie) 50%, Wakacje 25%, XTB 12,5%, Obligacje 12,5%, z zaokrągleniem do pełnych złotych i resztą na PKO, jak w arkuszu „Kalk2”. Plan można zmienić od wybranej daty.
- Zbiorcze rozliczenie: widok sumuje nierozliczone dochody (osobno dla każdego planu), dzieli sumę z zaokrągleniem do pełnych złotych i pokazuje jedną listę przelewów na Wakacje, XTB i Obligacje (kwota, rachunek, tytuł do skopiowania). Jedno kliknięcie oznacza wszystkie te dochody jako rozliczone.
- Majątek: konta PKO, XTB i Obligacje. Salda XTB i Obligacji rosną same o rozliczone przelewy. Faktyczne saldo każdego konta można wpisać w dowolnym momencie, a aplikacja pokazuje różnicę względem wyliczenia (zysk lub stratę) oraz wykres sumy w czasie. Saldo PKO jest wyłącznie wpisywane ręcznie. Wakacje są częścią podziału, ale nie wchodzą do majątku.
- Start od stanu z arkusza „Kalk2” (2026-10-12). Starszej historii nie przenosimy.
- **BREAKING:** usunięte zostają import wyciągów XML z iPKO, klasyfikacja transakcji (skrzynka, reguły, historia, model językowy i połączenie z Docker Model Runner), portfel gotówki, należności, raporty przychodów i wydatków oraz tygodniowe rozliczenia z korektami i przenoszeniem kwot. Schemat bazy powstaje od nowa, a dane z pierwszej wersji (jeden zaimportowany tydzień) przepadają. Śledzenie wydatków może wrócić jako osobna, prostsza zmiana.
- **BREAKING:** zmiana `finbro-mvp` zostaje usunięta bez archiwizacji, żeby jej specyfikacje nie trafiły do specyfikacji głównych. Historia zostaje w gicie.

## Możliwości

### Nowe możliwości
- `income-allocation`: rejestr dochodów wpisywanych ręcznie i ich podział na koperty według planu obowiązującego w dniu dochodu.
- `transfer-settlement`: zbiorcza lista przelewów na koperty dla nierozliczonych dochodów i oznaczanie ich jako rozliczonych.
- `net-worth`: salda kont PKO, XTB i Obligacji wyliczane z rozliczonych przelewów i korygowane wpisanym saldem faktycznym, z sumą i wykresem majątku w czasie.

### Zmienione możliwości
Brak. W repozytorium nie ma jeszcze specyfikacji głównych.

## Wpływ

- Kod: zostają Dockerfile, `docker-compose.yml` (baza i aplikacja), konfiguracja, połączenie z bazą, Alembic, szkielet FastAPI z Jinja2 i HTMX, styl oraz typ `Money`. Modele danych, migracje, serwisy, widoki i testy powstają od nowa pod nowy zakres. Moduły importu, klasyfikacji, LLM, portfela, należności i raportów oraz SQLAdmin zostają usunięte.
- Zależności: odpadają `sqladmin`, `itsdangerous` i (jeśli nieużywane) `python-multipart`. Chart.js zostaje do wykresu majątku.
- Docker: bez zmian w liczbie usług. Wolumen `finbro-pgdata` zostaje, ale migracje tworzą nowy schemat od zera (stare tabele są usuwane). Model językowy i Docker Model Runner nie są już potrzebne.
- Konfiguracja OpenSpec (`openspec/config.yaml`): wskazówki o testach obejmują teraz podział, rozliczenie i salda majątku zamiast importu, klasyfikacji, portfela i należności.
- Dane: aplikacja nie przechowuje wyciągów bankowych. Arkusz użytkownika zostaje poza repozytorium.
