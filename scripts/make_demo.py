"""Writes demo/statement.csv: an INVENTED current account, Italian bank format, Nov 2025 - Oct 2026.

The account holder is a made-up retired teacher, "Walter Brenner", who dies on 12 May 2026. His everyday
spending stops; his subscriptions do not. Every name and number here is invented for the demo."""

import random
from datetime import date, timedelta
from pathlib import Path

random.seed(7)
DIED = date(2026, 5, 12)
START, END = date(2025, 11, 1), date(2026, 10, 31)
rows = []


def add(d, desc, out=None, inn=None):
    if START <= d <= END:
        rows.append((d, desc, out, inn))


def monthly(day, n=12, start=START):
    y, m = start.year, start.month
    for _ in range(n):
        d = date(y, m, min(day, 28))
        if d.weekday() >= 5:
            d += timedelta(days=7 - d.weekday())
        yield d
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


card = "CARTA N. ****4417"
for i, d in enumerate(monthly(3)):
    add(d, f"PAGAMENTO POS NETFLIX.COM 866-579-7172 AMSTERDAM {card} DEL {d:%d/%m/%Y}", "13,49" if i < 4 else "15,49")
for d in monthly(9):
    add(d, "PAGAMENTO TRAMITE PAYPAL SPOTIFY AB" if d.month % 2 else "PAYPAL *SPOTIFYAB 35314369", "17,99")
for d in monthly(1):
    add(d, "ADDEBITO SDD CORE FITNESS POINT SSD MANDATO FP00231 CID IT55ZZZ0000096", "42,00")
for d in monthly(16):
    add(d, f"PAGAMENTO POS APPLE.COM/BILL 866-712-7753 {card}", "2,99")
for d in monthly(21):
    add(d, "ADDEBITO SDD CORE MEDICI SENZA FRONTIERE DONAZIONE REGOLARE", "15,00")
for d in monthly(12):
    add(d, f"PAGAMENTO POS AUDIBLE GMBH ADBL.CO/PYMT {card}", "9,99")
for d in monthly(27):
    add(d, "ADDEBITO SDD CORE WINDTRE SPA FATTURA", "11,99")
add(date(2026, 3, 30), f"PAGAMENTO POS PADDLE.NET* BABBEL {card}", "0,00")
for d in monthly(30, 7, date(2026, 4, 1)):
    add(d, f"PAGAMENTO POS PADDLE.NET* BABBEL {card}", "12,99")
add(date(2026, 2, 6), f"PAGAMENTO POS SQUARESPACE DOMAINS {card}", "20,00")
add(date(2025, 11, 14), "ADDEBITO SDD CORE UNIPOL ASSICURAZIONI POLIZZA CASA", "86,40")
add(date(2026, 2, 14), "ADDEBITO SDD CORE UNIPOL ASSICURAZIONI POLIZZA CASA", "86,40")
add(date(2026, 5, 14), "ADDEBITO SDD CORE UNIPOL ASSICURAZIONI POLIZZA CASA", "86,40")
add(date(2026, 8, 14), "ADDEBITO SDD CORE UNIPOL ASSICURAZIONI POLIZZA CASA", "86,40")
add(date(2026, 6, 4), f"PAGAMENTO POS NETFLIX.COM 866-579-7172 AMSTERDAM {card}", "15,49")  # double charge

# Life: pension in, groceries, pharmacy, the bar, fuel. It stops when he dies.
for d in monthly(1):
    if d <= DIED:
        add(d, "ACCREDITO PENSIONE INPS", inn="1.684,20")
d = START
while d <= DIED:
    add(d, random.choice(["PAGAMENTO POS COOP ALLEANZA 3.0", "PAGAMENTO POS CONAD CITY", "PAGAMENTO POS PANIFICIO ROSSI"]),
        f"{random.randint(8, 74)},{random.randint(0, 99):02d}")
    if random.random() < .45:
        add(d + timedelta(days=2), "PAGAMENTO POS BAR CENTRALE", f"{random.choice([1, 2, 3, 4])},{random.choice(['20', '40', '80', '50'])}")
    if random.random() < .25:
        add(d + timedelta(days=3), "PAGAMENTO POS FARMACIA COMUNALE 2", f"{random.randint(6, 39)},{random.randint(0, 99):02d}")
    if random.random() < .2:
        add(d + timedelta(days=4), "PAGAMENTO POS ENI STATION 4412", f"{random.randint(30, 60)},00")
    d += timedelta(days=random.choice([3, 4, 5]))
add(date(2026, 6, 20), "BONIFICO A VOSTRO FAVORE DA BRENNER ANNA PER SPESE", inn="500,00")

rows = [r for r in rows if r[1]]
rows.sort(key=lambda r: r[0], reverse=True)
out = ["Data contabile;Data valuta;Descrizione;Accrediti;Addebiti"]
for d, desc, o, i in rows:
    out.append(f"{d:%d/%m/%Y};{d:%d/%m/%Y};{desc};{i or ''};{o or ''}")
Path(__file__).parent.parent.joinpath("demo", "statement.csv").write_text("\n".join(out) + "\n", encoding="utf-8")
print(len(rows), "rows")
