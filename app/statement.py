"""Reads a bank statement export, whatever bank it comes from.

Every bank exports a different CSV: `;` or `,`, "12,99" or "12.99", 31/10/2026 or 10/31/2026 or
2026-10-31, one signed amount column or separate debit and credit columns, headers in Italian, English or
German. This module finds the columns by their names and by what is in them, and returns one list of
transactions. No model is involved: reading numbers and dates is the code's job."""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation


@dataclass(frozen=True)
class Txn:
    day: date
    amount: Decimal       # positive: money that left the account
    description: str      # the bank's text, joined from the columns that describe the payment
    row: int              # line number in the file, for the "show me" link


class StatementError(ValueError):
    pass


DATE_HEADERS = ("data contabile", "data operazione", "data", "posting date", "transaction date", "date",
                "datum", "buchungstag", "booking date", "fecha", "completed date", "started date", "date opération",
                "date operation", "fecha operación", "fecha operacion")
VALUE_DATE = ("data valuta", "valuta", "value date", "wertstellung")
AMOUNT_HEADERS = ("importo", "amount", "betrag", "betrag (eur)", "amount (eur)", "money out/in", "importe", "bedrag",
                  "montant", "bedrag (eur)", "montant (eur)")
DEBIT_HEADERS = ("addebiti", "uscite", "dare", "debit", "debits", "money out", "paid out", "soll", "ausgang", "débit",
                 "debito", "cargo")
CREDIT_HEADERS = ("accrediti", "entrate", "avere", "credit", "credits", "money in", "paid in", "haben", "eingang",
                  "crédit", "credito", "abono")
DIRECTION = ("af bij", "af/bij", "debit/credit", "credit/debit", "dr/cr", "cr/dr", "soll/haben")  # "Af" = out
STATE = ("state", "status")  # Revolut writes DECLINED and REVERTED rows that never took money
TEXT_HEADERS = ("descrizione", "causale", "description", "details", "name", "payee", "merchant", "empfänger",
                "verwendungszweck", "beschreibung", "concepto", "descrizione operazione", "counterparty", "notes",
                "libellé", "libelle", "naam / omschrijving", "omschrijving", "mededelingen", "naam")


def _decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    raise StatementError("The file is not text.")


def parse_amount(raw: str) -> Decimal | None:
    """ "1.234,56" and "1,234.56" and "-12,99 €" and "(12.99)" all read correctly."""
    s = raw.strip().replace(" ", "").replace(" ", "")
    if not s:
        return None
    negative = s.startswith("(") and s.endswith(")") or s.startswith("-") or s.endswith("-")
    s = re.sub(r"[^\d.,]", "", s)
    if not s:
        return None
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".") if re.search(r",\d{1,2}$", s) else s.replace(",", "")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", s):  # "1.234" with no decimals: a thousands separator
        s = s.replace(".", "")
    try:
        value = Decimal(s)
    except InvalidOperation:
        return None
    return -value if negative else value


_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d.%m.%Y", "%d-%m-%Y", "%d/%m/%y", "%m/%d/%y", "%Y/%m/%d",
                 "%d.%m.%y", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%d %b %Y", "%d/%m/%Y %H:%M", "%Y%m%d")


def _date_format(values: list[str]) -> str | None:
    """The one format that reads every value in the column. dd/mm and mm/dd are told apart by the values
    themselves: a 13 in the first place settles it for the whole file."""
    sample = [v.strip() for v in values if v.strip()]
    if not sample:
        return None
    for fmt in _DATE_FORMATS:
        try:
            for v in sample:
                datetime.strptime(v, fmt)
            return fmt
        except ValueError:
            continue
    return None


def _find(headers: list[str], names: tuple[str, ...]) -> int | None:
    low = [h.strip().lower() for h in headers]
    for name in names:
        if name in low:
            return low.index(name)
    for i, h in enumerate(low):
        if any(h.startswith(n) for n in names):
            return i
    return None


def read(data: bytes) -> list[Txn]:
    text = _decode(data)
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        raise StatementError("The file is empty.")
    # Some banks put a few lines of account details above the table, which confuses delimiter sniffing:
    # try each delimiter, and take the first row that names a date column and an amount (or debit) column.
    rows, start = [], None
    for delim in ";,\t|":
        rows = list(csv.reader(io.StringIO("\n".join(lines)), delimiter=delim))
        start = next((i for i, r in enumerate(rows[:30]) if _find(r, DATE_HEADERS) is not None and
                      (_find(r, AMOUNT_HEADERS) is not None or _find(r, DEBIT_HEADERS) is not None)), None)
        if start is not None:
            break
    if start is None:
        raise StatementError("I could not find the date and amount columns. Is this a bank statement export?")
    header, body = rows[start], [r for r in rows[start + 1:] if any(c.strip() for c in r)]
    d_col = _find(header, DATE_HEADERS)
    if _find(header, VALUE_DATE) == d_col:  # "Data valuta" matched "data": prefer the booking date
        d_col = _find([h if i != d_col else "" for i, h in enumerate(header)], DATE_HEADERS) or d_col
    a_col, debit_col, credit_col = _find(header, AMOUNT_HEADERS), _find(header, DEBIT_HEADERS), _find(header, CREDIT_HEADERS)
    dir_col, state_col = _find(header, DIRECTION), _find(header, STATE)
    text_cols = [i for i, h in enumerate(header) if h.strip().lower() in TEXT_HEADERS]
    if not text_cols:
        text_cols = [i for i, h in enumerate(header) if any(h.strip().lower().startswith(n) for n in TEXT_HEADERS)]
    if not text_cols:
        raise StatementError("I could not find a description column.")
    # A column that only says what kind of row it is ("DEBIT", "Lastschrift") describes nothing.
    if len(text_cols) > 1 and len(body) >= 10:
        varied = [i for i in text_cols if len({r[i].strip().upper() for r in body if i < len(r)}) > 5]
        text_cols = varied or text_cols
    fmt = _date_format([r[d_col] for r in body if len(r) > d_col])
    if not fmt:
        raise StatementError("I could not read the dates.")

    # Which sign is a payment? With one amount column, most banks write payments as negative numbers; a
    # few write them positive and mark credits. Salary-sized positives settle it.
    out: list[Txn] = []
    signed: list[tuple[int, date, Decimal, str]] = []
    for n, r in enumerate(body, start=start + 2):
        if len(r) <= d_col or not r[d_col].strip():
            continue
        try:
            day = datetime.strptime(r[d_col].strip(), fmt).date()
        except ValueError:
            continue
        if state_col is not None and state_col < len(r) and r[state_col].strip().upper() in ("DECLINED", "REVERTED", "FAILED", "CANCELLED", "PENDING"):
            continue
        desc = " · ".join(dict.fromkeys(r[i].strip() for i in text_cols if i < len(r) and r[i].strip()))
        if a_col is not None and a_col < len(r) and r[a_col].strip():
            value = parse_amount(r[a_col])
            if value is None:
                continue
            if dir_col is not None and dir_col < len(r) and r[dir_col].strip():
                # An unsigned amount with a separate direction column: "Af" / "Debit" / "D" is money out.
                out_ = r[dir_col].strip().lower() in ("af", "debit", "d", "dr", "db", "soll", "s")
                out.append(Txn(day, abs(value) if out_ else -abs(value), desc, n))
                continue
            signed.append((n, day, value, desc))
        else:
            debit = parse_amount(r[debit_col]) if debit_col is not None and debit_col < len(r) else None
            credit = parse_amount(r[credit_col]) if credit_col is not None and credit_col < len(r) else None
            if credit:
                out.append(Txn(day, -abs(credit), desc, n))
            elif debit is not None:  # a 0.00 debit is kept: it is how many free trials start
                out.append(Txn(day, abs(debit), desc, n))
    if signed:
        negatives = sum(1 for _, _, v, _ in signed if v < 0)
        flip = negatives >= len(signed) / 3  # payments are the negative ones
        for n, day, v, desc in signed:
            out.append(Txn(day, -v if flip else v, desc, n))
    if not out:
        raise StatementError("No transactions found.")
    return sorted(out, key=lambda t: (t.day, t.row))
