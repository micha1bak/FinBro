# Fixture'y testowe

Wszystkie pliki są syntetyczne: kontrahenci, numery rachunków, telefonów i kart są
zmyślone, a struktura odwzorowuje eksport XML z iPKO. Prawdziwe wyciągi nigdy nie trafiają
do repozytorium.

Konto główne w fixture'ach: `27 1020 1026 0000 1234 5678 9012`.

- `pko/pko_2026-10-05_2026-10-11.xml`: tydzień 2026-T41, 14 zaksięgowanych operacji
  i jedna blokada (bez `exec-date`). Zawiera przelew przychodzący, płatności kartą
  zaksięgowane w poniedziałek po sobocie, przelew na telefon o mylącym typie
  ("przychodz.", a kwota ujemna), wypłatę z bankomatu, "Przelew z karty" na Revolut,
  dwie identyczne płatności po 7,00 zł z saldami 6351,56 i 6344,56, wpłatę we wpłatomacie
  i nieznaną etykietę (`Kod MCC`).
- `pko/pko_2026-10-08_2026-10-18.xml`: wyciąg nakładający się z poprzednim (zamaskowany
  numer rachunku), z zaksięgowaną wcześniejszą blokadą i przelewami FinBro za 2026-T41.
- `pko/pko_2026-10-12_2026-10-18.xml`: tydzień 2026-T42 z przelewami FinBro pokrywającymi
  rozliczenie T41 przy dochodach 4250,00 + 705,87 zł i dochodzie gotówkowym 800,00 zł
  (test end-to-end poniedziałkowego rozliczenia).
- `pko/pko_inny_rachunek.xml`: wyciąg z innego rachunku.
- `pko/pko_uszkodzony.xml`: ucięty, niepoprawny XML.
- `pko/nie_ipko.xml` i `pko/wyciag.csv`: pliki w nieobsługiwanym formacie.
