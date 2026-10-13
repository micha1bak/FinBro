# Spike modelu językowego (zadanie 8.1)

Data: 2026-10-13. Sprzęt: Ryzen 5 7520U (4 rdzenie / 8 wątków), 16 GB RAM, zintegrowany
Radeon 610M (512 MB). Serwer modelu: Docker Model Runner z Docker Desktop 4.93, backend
llama.cpp `b9879-cpu` (tylko procesor).

## Wybór kandydatów

Testowany był jeden model: **`ai/gemma4:E2B`** (Gemma 4 E2B, 4,65 mld parametrów, Q4_K_M),
wybrany przez użytkownika i już pobrany do DMR. Zgodnie z decyzją użytkownika nie pobieraliśmy
innych modeli, bo ten daje akceptowalny wynik. Wcześniejsze próby:

- `ai/gemma4:E4B` w DMR z akceleracją Vulkan na zintegrowanym GPU kończyła się błędem
  `ErrorOutOfDeviceMemory` (logi Docker Desktop z 2026-10-04), więc DMR musi działać na CPU.
- API DMR w stylu Ollamy (`/api/chat`) ignoruje schemat JSON w polu `format`, a z włączonym
  trybem rozumowania odpowiedź trwała 96–130 s. Endpoint zgodny z OpenAI
  (`/engines/v1/chat/completions`) przestrzega `response_format` typu `json_schema`, a z
  `chat_template_kwargs.enable_thinking = false` odpowiada w kilkanaście sekund. Klasyfikator
  korzysta z tego endpointu (D10).

## Metoda

Skrypt [`scripts/llm_spike.py`](../scripts/llm_spike.py) klasyfikuje 30 zmyślonych transakcji
(21 wydatków kartą i przelewem, pożyczka, odkładanie, transfer, dochody, spłaty, rozliczenie,
zwrot) tym samym klasyfikatorem co aplikacja: ten sam prompt, schemat JSON z 13 kategoriami
startowymi i dwoma dłużnikami, ta sama walidacja odpowiedzi. Dwa przebiegi: bez przykładów
i z przykładami wcześniejszych decyzji (jak w aplikacji, do 5 decyzji w tym samym kierunku).

```bash
docker compose run --rm --no-deps -v ./scripts:/scripts:ro app python /scripts/llm_spike.py ai/gemma4:E2B
```

## Wyniki

| Przebieg | Typ | Kategoria | Dłużnik | Brak propozycji | Czas: mediana / średnio | Pierwsze zapytanie |
|---|---|---|---|---|---|---|
| bez przykładów | 28/30 | 18/23 | 3/3 | 0 | 15,7 s / 17,4 s | 59,1 s (ładowanie modelu) |
| z przykładami | 27/30 | 19/23 | 2/3 | 0 | 16,0 s / 16,8 s | 24,1 s |

Prompt ma około 390 tokenów bez przykładów i 480–560 z przykładami, odpowiedź 55–75 tokenów.
Proces `com.docker.llama-server` zajmował podczas testu około 3,9 GB RAM (4,6 GB pamięci
prywatnej) w Windows, poza maszyną WSL2. Baza i aplikacja w kontenerach zajmują łącznie
około 170 MB.

Błędy modelu (w nawiasie przebieg: 1 bez przykładów, 2 z przykładami):

- ZARA POLSKA: „Inne” (1) i „Spożywcze” (2) zamiast „Ubrania”.
- SMYK (sklep z zabawkami): „Rozrywka i hobby” zamiast „Prezenty” lub „Inne” (1, 2).
- APTEKA DOZ: „Spożywcze” zamiast „Zdrowie” (1).
- Przelew na telefon do Martyny „Pożyczka do wypłaty”: WYDATEK zamiast POŻYCZKI (2).
- Przelew do ANNA TESTOWA „Na wspólne wydatki domowe”: POŻYCZKA zamiast TRANSFERU (1, 2).
- Wpływ „Za pizzę wczoraj”: DOCHÓD zamiast ROZLICZENIA (1, 2).
- Zwrot z ZALANDO: poprawny typ ZWROT, ale bez kategorii (1, 2).

## Wnioski i rekomendacja

- **Model domyślny: `ai/gemma4:E2B`** (`DEFAULT_LLM_MODEL` w `finbro/config.py`). Typ jest trafny
  w 90–93% przypadków, kategoria w około 80%, odpowiedź zawsze mieści się w schemacie.
- Typowa klasyfikacja trwa około 16 s, więc tydzień z 10–20 pozycjami bez reguły i historii
  przetwarza się w tle w 3–6 minut. Import kończy się od razu, a propozycje pojawiają się
  w skrzynce stopniowo (D9), co jest akceptowalne.
- Najsłabsze są typy wymagające kontekstu (rozliczenie wspólnego wydatku, transfer do rodziny
  kontra pożyczka). To przypadki, które i tak zatwierdza użytkownik, a po pierwszej decyzji
  z „zapamiętaj” przejmują je reguły i historia.
- Propozycja ZWROTU bez kategorii nie spełnia wymagań typu, więc nie jest przyjmowana
  automatycznie i użytkownik uzupełnia kategorię w skrzynce.
- **Ryzyko do decyzji użytkownika:** zgodnie z D9 propozycje dla wydatków są przyjmowane
  automatycznie z każdego źródła, także od modelu. Błędy z tabeli dla wydatków (zła kategoria,
  a zwłaszcza POŻYCZKA zamiast TRANSFERU, która dopisuje należność) trafiłyby więc do danych
  bez przeglądu. Model myli się w około 1 na 5 kategorii, więc warto rozważyć, by propozycje
  modelu dla wydatków wymagały zatwierdzenia albo przynajmniej by POŻYCZKA od modelu go wymagała.
