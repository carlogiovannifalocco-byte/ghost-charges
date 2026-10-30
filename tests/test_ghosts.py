from datetime import date, timedelta
from decimal import Decimal

from app import ghosts, statement


def _csv(rows: list[tuple[date, str, str]]) -> bytes:
    lines = ["Data contabile;Data valuta;Descrizione;Accrediti;Addebiti"]
    for d, desc, amount in rows:
        lines.append(f"{d:%d/%m/%Y};{d:%d/%m/%Y};{desc};;{amount}")
    return "\n".join(lines).encode()


def _month(start: date, n: int, day_shift=(0, 1, -1, 2, 0, 3)) -> list[date]:
    out, d = [], start
    for i in range(n):
        out.append(d + timedelta(days=day_shift[i % len(day_shift)]))
        d = date(d.year + (d.month == 12), d.month % 12 + 1, d.day)
    return out


def statement_rows():
    rows = []
    for i, d in enumerate(_month(date(2025, 11, 3), 12)):
        rows.append((d, "PAGAMENTO POS NETFLIX.COM 866-579-7172 AMSTERDAM CARTA N. ****1234", "12,99" if i < 6 else "15,49"))
    for i, d in enumerate(_month(date(2025, 11, 10), 12)):
        rows.append((d, "PAYPAL *SPOTIFYAB 35314369" if i % 2 else "PAGAMENTO TRAMITE PAYPAL SPOTIFY AB", "10,99"))
    for d in _month(date(2025, 11, 20), 4):  # cancelled in February
        rows.append((d, "ADDEBITO SDD CORE PALESTRA FITNESS POINT MANDATO X123", "39,00"))
    rows.append((date(2026, 4, 2), "PADDLE.NET* NOTION", "1,00"))  # trial, then full price
    for d in _month(date(2026, 5, 2), 6):
        rows.append((d, "PADDLE.NET* NOTION", "9,50"))
    for i in range(48):  # weekly shop: wandering amounts, not a subscription
        rows.append((date(2025, 11, 1) + timedelta(days=7 * i), "PAGAMENTO POS ESSELUNGA SPA MILANO", f"{40 + (i * 7) % 33},{i % 10}0"))
    rows.append((date(2026, 7, 14), "PAGAMENTO POS RISTORANTE DA MARIO", "48,00"))
    rows.append((date(2026, 7, 14), "PAGAMENTO POS RISTORANTE DA MARIO", "48,00"))  # double charge
    rows.append((date(2025, 11, 2), "APPLE.COM/BILL 866-712-7753", "29,99"))
    rows.append((date(2026, 11, 29) - timedelta(days=30), "APPLE.COM/BILL 866-712-7753", "29,99"))
    return rows


def test_reads_an_italian_export_with_debit_and_credit_columns():
    txns = statement.read(_csv([(date(2026, 1, 5), "PAGAMENTO POS BAR", "1.234,56")]))
    assert txns[0].amount == Decimal("1234.56") and txns[0].day == date(2026, 1, 5)


def test_reads_a_signed_amount_export():
    data = b"Posting Date,Description,Amount\n10/31/2026,NETFLIX.COM,-15.49\n10/30/2026,PAYROLL ACME,2500.00\n"
    txns = statement.read(data)
    assert [(t.description, t.amount) for t in txns] == [("PAYROLL ACME", Decimal("-2500.00")), ("NETFLIX.COM", Decimal("15.49"))]


def test_amounts_in_every_format():
    for raw, want in [("12,99", "12.99"), ("-12.99", "-12.99"), ("1.234,56", "1234.56"), ("1,234.56", "1234.56"),
                      ("(15.00)", "-15.00"), ("12,99 €", "12.99"), ("1.000", "1000")]:
        assert statement.parse_amount(raw) == Decimal(want), raw


def test_finds_the_ghosts_and_leaves_the_groceries_alone():
    found = ghosts.find(statement.read(_csv(statement_rows())))
    by = {g["key"]: g for g in found["ghosts"]}
    assert set(by) == {"NETFLIX", "SPOTIFY", "PALESTRA", "NOTION", "APPLE"}
    assert by["NETFLIX"]["active"] and by["NETFLIX"]["price_changes"][0]["from"] == "12.99"
    assert by["NETFLIX"]["price_changes"][0]["to"] == "15.49" and by["NETFLIX"]["per_year"] == "185.88"
    assert by["SPOTIFY"]["count"] == 12  # "SPOTIFYAB" and "SPOTIFY AB" are one merchant
    assert not by["PALESTRA"]["active"]  # stopped in February
    assert by["NOTION"]["trial"] == {"day": "2026-04-02", "amount": "1.00"}
    assert by["APPLE"]["cadence"] == "yearly"
    assert [d["merchant"] for d in found["duplicates"]] == ["Ristorante"]


def test_clean_names():
    assert ghosts.key("PAGAMENTO POS NETFLIX.COM 866-579-7172 AMSTERDAM CARTA N. ****1234 DEL 03/10/2026") == "NETFLIX"
    assert ghosts.key("AMZN Mktp US*2K3LP1H90") == "AMAZON"
    assert ghosts.key("Amazon Prime*2K3LP1 Amzn.com/bill WA") == "AMAZON PRIME"
    assert ghosts.key("PADDLE.NET* NOTION") == "NOTION"
