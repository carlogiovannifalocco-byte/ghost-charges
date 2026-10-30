# Ghost-charges evaluation set

**All data here is invented.** The people, employers, landlords, IBANs, card numbers, mandate
references and transactions are fictional and were produced by a seeded random generator. No real
person's bank data was used. Merchant names (Netflix, Spotify, Esselunga, ...) and their public
billing descriptors are used only so the statements look like real exports.

## Files

| File | Style | Period | Rows | Recurring items |
|---|---|---|---|---|
| `statements/it-intesa-style.csv` | `;` separator, dd/mm/yyyy, comma decimals, `1.850,00` thousands, separate Accrediti/Addebiti, newest first | Nov 2025 - Oct 2026 | 172 | 8 |
| `statements/uk-monzo-style.csv` | comma, ISO dates, signed `Amount`, `Category`, clean `Name` + raw `Description`, local currency columns | Nov 2025 - Oct 2026 | 182 | 9 |
| `statements/us-chase-style.csv` | Chase layout, mm/dd/yyyy, negative debits, running Balance, newest first, **each data row ends with a trailing comma** (as real Chase exports do) | Nov 2025 - Oct 2026 | 180 | 7 |
| `statements/de-n26-style.csv` | N26 layout: all fields quoted, ISO dates, dot decimals, German column names | Jan - Oct 2026 | 132 | 8 |

`gold.json` holds, per file: `rows`, `recurring` (merchant, cadence, amounts in date order,
count, first/last date, active_at_end, price_rise, trial_converted, descriptor_examples, optional
note), `duplicates` and `not_subscriptions`.

## Conventions used by the gold

- Dates are the statement's primary date column (Italy: *Data contabile*; US: *Posting Date*).
  The Italian POS descriptions also embed the real purchase date ("DEL 25.07.2026").
- `amounts` are positive numbers and **exclude** the duplicate charge, which is listed under
  `duplicates` instead (so rows for that merchant = `count` + duplicates).
- `active_at_end` = still charging at the end of the export (not cancelled).
- A free/cheap first charge followed by full price is `trial_converted`, not `price_rise`.
- Utilities with varying amounts (Octopus Energy, Con Ed) are listed as not subscriptions.

## How it was made

`scripts/generate.py` (seeded, deterministic) writes the four CSVs and `gold.json` from one spec.
`scripts/check_gold.py` independently re-parses each CSV in its own bank format, matches each gold
merchant with a hand-written regex, and checks counts, amounts, first/last dates, cadence gaps,
duplicates and the active/price-rise/trial flags. Run `python3 scripts/generate.py && python3 scripts/check_gold.py`.
