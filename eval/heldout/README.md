# Held-out evaluation set

**All data here is invented.** The people, employers, landlords, IBANs, card numbers, mandate
references and transactions are fictional, produced by a seeded deterministic generator. Real
merchant names (Canal+, Movistar, Strava, Ziggo, ...) and their typical billing-descriptor styles
are used only so the exports look like real ones.

**Made blind:** this set was written without opening the detector's code (`app/`, `scripts/`).
Only the gold JSON schema was copied from `eval/gold.json` / `eval/README.md`. Banks and merchant
line-up differ from the main eval set.

| File | Style | Period | Rows | Recurring |
|---|---|---|---|---|
| `statements/fr-credit-agricole-style.csv` | Crédit Agricole-like: preamble lines, `;`, dd/mm/yyyy, `2 412,37`, Débit/Crédit columns, multi-line quoted libellés, newest first | Oct 2025 - Oct 2026 | 180 | 8 |
| `statements/es-santander-style.csv` | Santander-like: preamble, `;`, Fecha Operación/Fecha Valor/Concepto/Importe/Saldo, signed `-9,99`, `1.985,40`, newest first | Dec 2025 - Oct 2026 | 184 | 8 |
| `statements/ie-revolut-style.csv` | Revolut-like EUR: Type/Product/Started Date/Completed Date/Description/Amount/Fee/Currency/State/Balance, ISO datetimes, includes a DECLINED row | Nov 2025 - Oct 2026 | 189 | 7 |
| `statements/nl-ing-style.csv` | ING NL-like: all quoted, `;`, yyyymmdd, Af/Bij + unsigned `12,99`, Mededelingen with incasso/card details | Jan - Oct 2026 | 152 | 7 |

Gold conventions match the main set: dates are the primary date column (FR `Date`, ES `Fecha
Operación`, Revolut `Started Date`, ING `Datum`); `amounts` are positive EUR amounts in date order
and exclude the duplicate charge (listed under `duplicates`); only COMPLETED Revolut rows count.
For ING the descriptor is `Naam / Omschrijving | Mededelingen`.

Run: `python3 generate.py && python3 check_gold.py` (the checker re-parses each CSV on its own and
must print `ALL OK`).

## Results log (rules only, no model)

1. **First run** (`first-run-rules.txt`): the detector could read none of the four files (0 / 30). The
   preamble lines confused delimiter detection, and the column names (`Débit euros`, `Completed Date`,
   `Bedrag (EUR)` with `Af Bij`, `20261027` dates) were unknown to it.
2. **After fixing only the CSV reader** (`app/statement.py`; the detection code in `app/ghosts.py` was
   not touched): `rules-after-reader-fix.txt`, 25 / 30 found, 14 / 25 named right, 8 false alarms,
   3 / 4 double charges.
