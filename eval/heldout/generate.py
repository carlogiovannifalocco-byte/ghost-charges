#!/usr/bin/env python3
"""Held-out eval set generator for the ghost-charges subscription detector.

ALL DATA IS INVENTED: people, employers, landlords, IBANs, card numbers, mandate
references and transactions are fictional. Real merchant names and their typical
billing-descriptor styles are used only so the exports look realistic.

Deterministic: fixed seed, no clock reads. Writes statements/*.csv and gold.json
next to this file.
"""
import csv
import datetime as dt
import io
import json
import os
import random
from calendar import monthrange

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "statements")
SEED = 4127
D = dt.date
ONE = dt.timedelta(days=1)


def months(y, m, y2, m2):
    while (y, m) <= (y2, m2):
        yield y, m
        m += 1
        if m == 13:
            y, m = y + 1, 1


def dom(y, m, d):
    return D(y, m, min(d, monthrange(y, m)[1]))


def biz(d):
    while d.weekday() >= 5:
        d += ONE
    return d


def digits(rng, n):
    return "".join(rng.choice("0123456789") for _ in range(n))


def alnum(rng, n):
    return "".join(rng.choice("ABCDEFGHJKLMNPQRSTUVWXYZ0123456789") for _ in range(n))


def r2(x):
    return round(x + 1e-9, 2)


class Stmt:
    def __init__(self, name, start, end):
        self.name, self.start, self.end = name, start, end
        self.tx = []          # dicts: date, amt (signed), desc, sub, dup, extra
        self.meta = {}        # sub name -> dict(cadence, active, price_rise, trial, note)
        self.not_subs = []

    def add(self, date, amt, desc, sub=None, dup=False, **extra):
        assert self.start <= date <= self.end, (self.name, date, desc)
        self.tx.append(dict(date=date, amt=r2(amt), desc=desc, sub=sub, dup=dup, extra=extra))

    def sub(self, name, cadence, active, price_rise=False, trial=False, note=None):
        self.meta[name] = dict(cadence=cadence, active=active, price_rise=price_rise,
                               trial=trial, note=note)

    def chrono(self):
        return sorted(self.tx, key=lambda t: (t["date"], t["extra"].get("time", "12:00:00"), t["desc"]))

    def gold(self, descfn=lambda t: t["desc"]):
        rec = []
        for name, m in self.meta.items():
            ch = [t for t in self.chrono() if t["sub"] == name and not t["dup"]
                  and t["extra"].get("state", "COMPLETED") == "COMPLETED"]
            assert ch, name
            ex = []
            for t in ch:
                s = descfn(t)
                if s not in ex:
                    ex.append(s)
            e = dict(merchant=name, cadence=m["cadence"], amounts=[-t["amt"] for t in ch],
                     count=len(ch), first=ch[0]["date"].isoformat(), last=ch[-1]["date"].isoformat(),
                     active_at_end=m["active"], price_rise=m["price_rise"],
                     trial_converted=m["trial"], descriptor_examples=ex[:4])
            if m["note"]:
                e["note"] = m["note"]
            rec.append(e)
        dups = [dict(merchant=t["sub"], date=t["date"].isoformat(), amount=-t["amt"],
                     descriptor=descfn(t)) for t in self.chrono() if t["dup"]]
        assert len(dups) == 1, self.name
        return dict(rows=len(self.tx), recurring=rec, duplicates=dups, not_subscriptions=self.not_subs)


def fx_eur(rng, usd):
    rate = rng.uniform(1.055, 1.165)       # USD per EUR
    return r2(usd / rate), rate


# ---------------------------------------------------------------------------
# 1. French bank, Crédit-Agricole-like
# ---------------------------------------------------------------------------
def build_fr(rng):
    s = Stmt("fr-credit-agricole-style.csv", D(2025, 10, 27), D(2026, 10, 29))
    CITY = "LYON"

    def cb(label, post, lag=None):
        lag = rng.choice([1, 1, 2, 3]) if lag is None else lag
        p = post - dt.timedelta(days=lag)
        return f"CB {label:<24}{p:%d/%m}"

    def prlv(name, detail):
        return f"PRLV SEPA {name}\n{detail}"

    # Canal+ — price rise from March 2026
    s.sub("Canal+", "monthly", True, price_rise=True)
    for y, m in months(2025, 11, 2026, 10):
        d = biz(D(y, m, 5))
        amt = 25.99 if (y, m) < (2026, 3) else 27.99
        name = rng.choice(["GROUPE CANAL +", "CANAL+ FRANCE", "GROUPE CANAL+"])
        s.add(d, -amt, prlv(name, f"ECH/{d:%d%m%y} ID EMETTEUR/FR83ZZZ401857 MDT/++CNL7781093X REF/{digits(rng, 13)}"), "Canal+")
    # Free Mobile
    s.sub("Free Mobile", "monthly", True)
    for y, m in months(2025, 11, 2026, 10):
        d = biz(D(y, m, 14))
        s.add(d, -15.99, prlv(rng.choice(["FREE MOBILE", "Free Mobile"]),
              f"FM-{digits(rng, 8)} ECH/{d:%d%m%y} ID EMETTEUR/FR11ZZZ432189 MDT/FM5512038 REF/{digits(rng, 10)}"), "Free Mobile")
    # Deezer — card, cancelled after April 2026
    s.sub("Deezer", "monthly", False)
    for y, m in months(2025, 11, 2026, 4):
        d = dom(y, m, 18) + dt.timedelta(days=rng.choice([0, 1, 2]))
        s.add(d, -11.99, cb(rng.choice(["DEEZER PARIS", "DEEZER.COM", "DEEZER SA 75009"]), d), "Deezer")
    # Two Apple subscriptions (same biller): iCloud+ 2.99 ~3rd, Apple Music 10.99 ~21st
    s.sub("Apple iCloud+", "monthly", True,
          note="Same biller/descriptor family (APPLE.COM/BILL) as Apple Music; told apart by amount and day.")
    for y, m in months(2025, 11, 2026, 10):
        d = biz(dom(y, m, 3) + dt.timedelta(days=rng.choice([0, 1])))
        s.add(d, -2.99, cb(rng.choice(["APPLE.COM/BILL", "APPLE.COM/BILL CORK", "APPLE.COM BILL ITUNES"]), d), "Apple iCloud+")
    s.sub("Apple Music", "monthly", True,
          note="Second Apple subscription; the June charge was taken twice (see duplicates).")
    for y, m in months(2026, 1, 2026, 10):
        d = dom(y, m, 21) + dt.timedelta(days=rng.choice([0, 1]))
        desc = cb(rng.choice(["APPLE.COM/BILL", "APPLE.COM/BILL ITUNES.COM", "APPLE.COM/FR"]), d)
        s.add(d, -10.99, desc, "Apple Music")
        if (y, m) == (2026, 6):
            s.add(d + ONE, -10.99, cb("APPLE.COM/BILL", d + ONE, 2), "Apple Music", dup=True)
    # Amazon Prime yearly (both renewals inside the window)
    s.sub("Amazon Prime", "yearly", True,
          note="Yearly; both renewals fall inside the export (first days and last days). One-off Amazon purchases are separate.")
    s.add(D(2025, 10, 29), -69.90, cb("AMAZON PRIME FR*2K4XT", D(2025, 10, 29), 1), "Amazon Prime")
    s.add(D(2026, 10, 27), -69.90, cb("AMZ Prime FR*R82LM0", D(2026, 10, 27), 2), "Amazon Prime")
    # Basic-Fit membership from Feb 2026
    s.sub("Basic-Fit", "monthly", True)
    for y, m in months(2026, 2, 2026, 10):
        d = biz(D(y, m, 26)) if (y, m) != (2026, 10) else D(2026, 10, 26)
        s.add(d, -29.99, prlv("BASIC FIT FRANCE SAS", f"Cotisation BF{digits(rng, 7)} ECH/{d:%d%m%y} ID EMETTEUR/FR40ZZZ836411 MDT/BFF0031847 REF/{digits(rng, 9)}"), "Basic-Fit")
    # ChatGPT Plus in USD — converted amount wobbles
    s.sub("ChatGPT Plus (OpenAI, billed in USD)", "monthly", True,
          note="USD 20.00 converted to EUR at each month's rate, so the EUR amount varies by a few percent; not a price rise.")
    for y, m in months(2025, 12, 2026, 10):
        d = dom(y, m, 9) + dt.timedelta(days=rng.choice([0, 1, 2]))
        eur, rate = fx_eur(rng, 20.00)
        lab = rng.choice(["OPENAI *CHATGPT SUBSCR", "OPENAI SAN FRANCISCO", "CHATGPT SUBSCRIPTION"])
        s.add(d, -eur, cb(lab, d) + f"\nUSD 20,00 1 EURO = {rate:.4f}".replace(".", ","), "ChatGPT Plus (OpenAI, billed in USD)")

    # ---------------- noise ----------------
    for y, m in months(2025, 11, 2026, 10):
        s.add(biz(dom(y, m, 28)) if (y, m) != (2026, 10) else D(2026, 10, 28), 2412.37 + (380 if m == 12 else 0),
              f"VIR SEPA RECU /DE SARL ATELIERS DUBREUIL /MOTIF SALAIRE {m:02d}/{y} /REF {digits(rng, 8)}")
        d = biz(D(y, m, 2))
        s.add(d, -890.00, f"VIR SEPA EMIS /MOTIF LOYER {['', 'JANVIER','FEVRIER','MARS','AVRIL','MAI','JUIN','JUILLET','AOUT','SEPTEMBRE','OCTOBRE','NOVEMBRE','DECEMBRE'][m]} /BEN Mme Sophie GARNIER /REFDO {digits(rng, 6)}")
        d = biz(D(y, m, 11))
        winter = m in (11, 12, 1, 2, 3)
        s.add(d, -r2(rng.uniform(78, 118) if winter else rng.uniform(41, 66)),
              prlv("ENGIE", f"Facture {digits(rng, 10)} ECH/{d:%d%m%y} ID EMETTEUR/FR22ZZZ395712 MDT/EN0099172 REF/{digits(rng, 9)}"))
    d = D(2025, 10, 30)
    shops = ["CARREFOUR CITY " + CITY, "MONOPRIX LYON 3", "LIDL 1543", "CARREFOUR MARKET", "BIOCOOP CROIX ROUSSE"]
    while d <= D(2026, 10, 24):
        s.add(d, -r2(rng.uniform(14, 96)), cb(rng.choice(shops), d))
        d += dt.timedelta(days=rng.randint(8, 14))
    for _ in range(9):
        d = s.start + dt.timedelta(days=rng.randint(5, 360))
        s.add(d, -r2(rng.choice([23.5, 31.0, 38.4, 46.9, 27.8, 52.0])), cb("BRASSERIE GEORGES", d))
    for _ in range(9):
        d = s.start + dt.timedelta(days=rng.randint(5, 360))
        s.add(d, -r2(rng.uniform(48, 74)), cb("TOTALENERGIES LYON 7", d))
    for d, a in [(D(2025, 12, 8), 18.40), (D(2026, 3, 2), 19.10), (D(2026, 6, 15), 18.40), (D(2026, 9, 21), 21.30)]:
        s.add(d, -a, cb("PHARMACIE DU PARC", d))
    for d in [D(2026, 1, 13), D(2026, 4, 22), D(2026, 8, 19)]:
        s.add(d, -12.00, cb("ON AIR FITNESS LYON", d))
    for d in [D(2025, 11, 22), D(2026, 2, 7), D(2026, 4, 30), D(2026, 7, 11), D(2026, 9, 5)]:
        s.add(d, -rng.choice([40.0, 60.0, 80.0]), f"RETRAIT DAB {d - ONE:%d/%m} {CITY} BELLECOUR")
    s.add(D(2025, 12, 15), -149.99, cb("FNAC BELLECOUR", D(2025, 12, 15)))
    s.add(D(2026, 3, 19), -64.90, cb("DECATHLON LYON", D(2026, 3, 19)))
    s.add(D(2026, 3, 30), 64.90, "AVOIR CB DECATHLON LYON 27/03")
    s.add(D(2026, 5, 7), -37.48, cb("AMAZON PAYMENTS", D(2026, 5, 7)))
    s.add(D(2026, 8, 3), -212.00, cb("SNCF CONNECT", D(2026, 8, 3)))
    s.add(D(2026, 8, 24), 48.00, "REMBOURSEMENT SNCF CONNECT /REF " + digits(rng, 10))
    s.add(D(2026, 6, 9), 120.00, "VIR SEPA RECU /DE M. LUCAS LEFEVRE /MOTIF REMBOURSEMENT WEEKEND")
    s.not_subs = [
        "Carrefour / Monoprix / Lidl / Biocoop groceries (varying amounts)",
        "rent transfer to Mme Sophie Garnier (VIR SEPA EMIS LOYER, monthly 890,00)",
        "salary SARL Ateliers Dubreuil (monthly)",
        "ENGIE energy direct debit (monthly, amount varies - utility)",
        "Brasserie Georges (repeated restaurant)",
        "TotalEnergies fuel",
        "Pharmacie du Parc (roughly quarterly, similar amounts 18-21 EUR)",
        "On Air Fitness day pass bought three times (12,00)",
        "Amazon Payments one-off order (not Prime)",
        "Fnac / Decathlon / SNCF one-off purchases and their refunds",
        "cash withdrawals (RETRAIT DAB)",
    ]
    return s


def write_fr(s):
    bal = 2431.18
    total = sum(t["amt"] for t in s.tx)
    start_bal = r2(bal - total)

    def num(x):
        whole, frac = f"{x:.2f}".split(".")
        w = ""
        while len(whole) > 3:
            w = " " + whole[-3:] + w
            whole = whole[:-3]
        return whole + w + "," + frac

    buf = io.StringIO()
    buf.write("Téléchargement du 30/10/2026;\n;\n")
    buf.write("Mme Camille LEFEVRE;\n")
    buf.write("Compte de Dépôt carte n° 98765432101;\n")
    buf.write(f"Solde au 29/10/2026 {num(bal)} €;\n;\n")
    buf.write("Liste des opérations du compte entre le 27/10/2025 et le 29/10/2026;\n;\n")
    w = csv.writer(buf, delimiter=";", lineterminator="\n")
    w.writerow(["Date", "Libellé", "Débit euros", "Crédit euros", ""])
    for t in reversed(s.chrono()):
        a = t["amt"]
        w.writerow([t["date"].strftime("%d/%m/%Y"), t["desc"], num(-a) if a < 0 else "", num(a) if a > 0 else "", ""])
    _ = start_bal
    return buf.getvalue()


# ---------------------------------------------------------------------------
# 2. Spanish bank, Santander/BBVA-like
# ---------------------------------------------------------------------------
def build_es(rng):
    s = Stmt("es-santander-style.csv", D(2025, 12, 1), D(2026, 10, 28))
    CARD = "5489XXXXXXXX1102"

    def compra(txt, internet=True):
        if internet:
            return rng.choice([
                f"Compra Internet En {txt}, Tarj. :*481102",
                f"Compra Internet En {txt}, Tarjeta {CARD} , Comision 0,00",
            ])
        return f"Pago Movil En {txt}, Tarj. :*481102"

    # Movistar — price rise Feb 2026
    s.sub("Movistar (Telefonica)", "monthly", True, price_rise=True)
    for y, m in months(2025, 12, 2026, 10):
        d = biz(D(y, m, 3))
        amt = 58.90 if (y, m) < (2026, 2) else 61.90
        s.add(d, -amt, f"Recibo Telefonica De Espana, S.a.u. Nº Recibo 0049 {digits(rng, 4)} {digits(rng, 3)} Bbbbbb "
              f"Ref. Mandato 21{digits(rng, 7)}, Referencia {digits(rng, 10)}", "Movistar (Telefonica)")
    # Filmin — 1 EUR first month then 7.99
    s.sub("Filmin", "monthly", True, trial=True,
          note="Promotional first month at 1,00 then 7,99: trial converted, not a price rise.")
    for i, (y, m) in enumerate(months(2026, 2, 2026, 10)):
        d = dom(y, m, 10) + dt.timedelta(days=rng.choice([0, 1]))
        s.add(d, -(1.00 if i == 0 else 7.99),
              compra(rng.choice(["Filmin, Barcelona", "Www.filmin.es, Barcelona", "Filmin Sl, Barcelona"])), "Filmin")
    # Two Google subscriptions
    s.sub("Google One", "monthly", True,
          note="Same biller as the Duolingo charge (GOOGLE *); told apart by amount (1,99) and day.")
    for y, m in months(2025, 12, 2026, 10):
        d = dom(y, m, 6) + dt.timedelta(days=rng.choice([0, 1]))
        s.add(d, -1.99, compra(rng.choice(["Google *google One, G.co/helppay#", "Google One, Mountain View",
                                           "Google *google Storage, G.co/helppay#"])), "Google One")
    s.sub("Duolingo Super (via Google Play)", "monthly", True,
          note="Billed through Google Play; some months the descriptor only says 'Google Play' with no app name.")
    for y, m in months(2025, 12, 2026, 10):
        d = dom(y, m, 23) + dt.timedelta(days=rng.choice([0, 1]))
        s.add(d, -6.99, compra(rng.choice(["Google *duolingo, G.co/helppay#", "Google Play Apps, G.co/helppay#",
                                           "Google *google Play, G.co/helppay#"])), "Duolingo Super (via Google Play)")
    # PlayStation Plus quarterly
    s.sub("PlayStation Plus", "quarterly", True)
    for d in [D(2025, 12, 12), D(2026, 3, 13), D(2026, 6, 12), D(2026, 9, 14)]:
        s.add(d, -24.99, compra(rng.choice(["Playstation Network, London", "Sony Interactive Entertai, London",
                                            "Psn*playstation Plus, London"])), "PlayStation Plus")
    # Glovo Prime vs Glovo orders
    s.sub("Glovo Prime", "monthly", True,
          note="Same merchant as one-off Glovo food orders; only the fixed 5,99 monthly charge is the subscription.")
    for y, m in months(2025, 12, 2026, 10):
        d = dom(y, m, 19) + dt.timedelta(days=rng.choice([0, 1]))
        s.add(d, -5.99, compra(rng.choice(["Glovo Prime, Barcelona", "Glovoapp23, Barcelona", "Glovo*prime Subs, Barcelona"]), False), "Glovo Prime")
    # HBO Max and El Pais, same price & cadence
    s.sub("HBO Max", "monthly", True,
          note="Same price and cadence (9,99 monthly) as El Pais; separate subscription. The March charge was taken twice.")
    for y, m in months(2025, 12, 2026, 10):
        d = dom(y, m, 8) + dt.timedelta(days=rng.choice([0, 1]))
        s.add(d, -9.99, compra(rng.choice(["Hbo Max, Amsterdam", "Hbomax.com, Amsterdam", "Max*hbomax Subscr, Amsterdam"])), "HBO Max")
        if (y, m) == (2026, 3):
            s.add(d + 2 * ONE, -9.99, compra("Hbomax.com, Amsterdam"), "HBO Max", dup=True)
    s.sub("El Pais (digital subscription)", "monthly", True,
          note="Billed by the publisher Prisa (Ediciones El Pais); 9,99 like HBO Max.")
    for y, m in months(2026, 1, 2026, 10):
        d = dom(y, m, 15) + dt.timedelta(days=rng.choice([0, 1]))
        s.add(d, -9.99, compra(rng.choice(["Ediciones El Pais, Madrid", "Prisa Noticias Suscrip, Madrid", "Elpais.com, Madrid"])), "El Pais (digital subscription)")

    # ---------------- noise ----------------
    for y, m in months(2025, 12, 2026, 10):
        d = biz(dom(y, m, 27)) if (y, m) != (2026, 10) else D(2026, 10, 27)
        s.add(d, 1985.40 + (1985.40 if m in (12, 6) else 0), "Nomina Recibida Distribuciones Levante S.l.")
        d = biz(D(y, m, 1))
        mes = ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"][m]
        s.add(d, -850.00, f"Transferencia A Favor De Lucia Ferrer Garcia Concepto: Alquiler {mes}")
        d = biz(D(y, m, 16))
        s.add(d, -r2(rng.uniform(38, 91)), f"Recibo Iberdrola Clientes, S.a.u. Nº Recibo 0049 {digits(rng, 4)} Ref. Mandato IB{digits(rng, 8)}, Referencia {digits(rng, 10)}")
    d = D(2025, 12, 2)
    while d <= D(2026, 10, 26):
        s.add(d, -r2(rng.uniform(12, 88)), f"Pago Movil En Mercadona {rng.choice(['Ruzafa', 'Av. Del Puerto', 'Benimaclet'])}, Valencia, Tarj. :*481102")
        d += dt.timedelta(days=rng.randint(8, 13))
    for _ in range(10):
        d = s.start + dt.timedelta(days=rng.randint(3, 325))
        s.add(d, -r2(rng.choice([8.5, 12.4, 14.0, 17.8, 22.6, 9.9])), "Pago Movil En Bar Casa Paco, Valencia, Tarj. :*481102")
    for _ in range(7):
        d = s.start + dt.timedelta(days=rng.randint(3, 325))
        s.add(d, -r2(rng.uniform(40, 68)), "Compra Repsol Est. Serv. 3341, Valencia, Tarj. :*481102")
    for d, a in [(D(2026, 1, 20), 12.35), (D(2026, 4, 9), 12.35), (D(2026, 7, 2), 13.10), (D(2026, 9, 29), 12.35)]:
        s.add(d, -a, "Pago Movil En Farmacia Lda. M. Soler, Valencia, Tarj. :*481102")
    for d in [D(2026, 2, 18), D(2026, 5, 26), D(2026, 9, 2)]:
        s.add(d, -9.00, "Pago Movil En Altafit Entrada Dia, Valencia, Tarj. :*481102")
    for _ in range(6):
        d = s.start + dt.timedelta(days=rng.randint(3, 325))
        s.add(d, -r2(rng.uniform(16, 34)), "Pago Movil En Glovo Pedido, Barcelona, Tarj. :*481102")
    for d, a, who in [(D(2026, 1, 3), -15.0, "Bizum Enviado A Pablo Ruiz Concepto Cena"),
                      (D(2026, 3, 22), 22.5, "Bizum Recibido De Marta Gil Concepto Entradas"),
                      (D(2026, 6, 14), -30.0, "Bizum Enviado A Pablo Ruiz Concepto Regalo Ana"),
                      (D(2026, 8, 30), 12.0, "Bizum Recibido De Marta Gil Concepto Taxi")]:
        s.add(d, a, who)
    s.add(D(2026, 1, 9), -79.95, "Compra Zara Colon, Valencia, Tarj. :*481102")
    s.add(D(2026, 1, 21), 79.95, "Devolucion Compra Zara Colon, Valencia, Tarj. :*481102")
    s.add(D(2026, 4, 17), -129.00, "Compra Internet En Pccomponentes, Murcia, Tarj. :*481102")
    s.add(D(2026, 7, 21), -246.30, "Compra Internet En Renfe Viajeros, Madrid, Tarj. :*481102")
    for d in [D(2026, 2, 28), D(2026, 7, 31)]:
        s.add(d, -50.0, "Retirada De Efectivo En Cajero Santander Valencia")
    s.not_subs = [
        "Mercadona groceries (varying amounts)",
        "rent transfer to Lucia Ferrer Garcia (Transferencia ... Alquiler, monthly 850,00)",
        "salary Distribuciones Levante (monthly, extra pay in June and December)",
        "Iberdrola electricity direct debit (monthly, amount varies - utility)",
        "Bar Casa Paco (repeated bar/restaurant)",
        "Repsol fuel",
        "Farmacia Lda. M. Soler (roughly quarterly, 12,35-13,10)",
        "Altafit day pass (Entrada Dia) bought three times",
        "Glovo food orders (one-off; only Glovo Prime 5,99 is the subscription)",
        "Bizum transfers",
        "Zara purchase and its refund, PcComponentes, Renfe one-offs",
        "cash withdrawals",
    ]
    return s


def es_num(x):
    neg = x < 0
    whole, frac = f"{abs(x):.2f}".split(".")
    parts = []
    while len(whole) > 3:
        parts.insert(0, whole[-3:])
        whole = whole[:-3]
    parts.insert(0, whole)
    return ("-" if neg else "") + ".".join(parts) + "," + frac


def write_es(s):
    rows = s.chrono()
    bal = 3120.55
    out = []
    for t in rows:
        bal = r2(bal + t["amt"])
        vd = t["date"] + (ONE if t["desc"].startswith(("Compra", "Pago Movil")) and t["date"].weekday() < 4 else dt.timedelta(0))
        out.append([t["date"].strftime("%d/%m/%Y"), vd.strftime("%d/%m/%Y"), t["desc"], es_num(t["amt"]), es_num(bal)])
    buf = io.StringIO()
    buf.write("Movimientos de la cuenta;ES21 0049 5512 3456 7890 1234;\n")
    buf.write("Titular;ALEJANDRO MOLINA NAVARRO;\n;\n")
    w = csv.writer(buf, delimiter=";", lineterminator="\n")
    w.writerow(["Fecha Operación", "Fecha Valor", "Concepto", "Importe", "Saldo"])
    for r in reversed(out):
        w.writerow(r)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# 3. Revolut-like (EUR account, Ireland)
# ---------------------------------------------------------------------------
def build_rev(rng):
    s = Stmt("ie-revolut-style.csv", D(2025, 11, 1), D(2026, 10, 29))

    def tm():
        return f"{rng.randint(0, 23):02d}:{rng.randint(0, 59):02d}:{rng.randint(0, 59):02d}"

    def add(d, amt, desc, sub=None, dup=False, typ="CARD_PAYMENT", state="COMPLETED", lag=None):
        if lag is None:
            lag = rng.choice([0, 0, 1]) if typ == "CARD_PAYMENT" else 0
        s.add(d, amt, desc, sub, dup, time=tm(), typ=typ, state=state, lag=lag)

    # HelloFresh weekly — discounted first box (trial) then full price
    s.sub("HelloFresh", "weekly", True, trial=True,
          note="Weekly meal box; first box discounted (29,99) then 59,99: trial converted.")
    d = D(2026, 6, 25)
    i = 0
    while d <= s.end:
        add(d, -(29.99 if i == 0 else 59.99), rng.choice(["HelloFresh", "HLLFRSH*IE", "Hellofresh Dublin", "HLLFRSH*HelloFresh"]), "HelloFresh")
        d += 7 * ONE
        i += 1
    # Uber One vs Uber rides
    s.sub("Uber One", "monthly", True,
          note="Same biller as Uber rides (varying amounts); the March fee was taken twice.")
    for y, m in months(2025, 11, 2026, 10):
        d = dom(y, m, 11)
        add(d, -5.99, rng.choice(["Uber One", "Uber *One", "UBER *ONE HELP.UBER.COM"]), "Uber One", lag=0)
        if (y, m) == (2026, 3):
            add(d + ONE, -5.99, "Uber *One", "Uber One", dup=True, lag=0)
    # Midjourney in USD
    s.sub("Midjourney (billed in USD)", "monthly", True,
          note="USD 10.00 converted to EUR, so the amount wobbles by a few percent; not a price rise.")
    for y, m in months(2026, 1, 2026, 10):
        d = dom(y, m, 27)
        eur, _ = fx_eur(rng, 10.00)
        add(d, -eur, rng.choice(["Midjourney Inc", "MIDJOURNEY INC.", "Midjourney"]), "Midjourney (billed in USD)")
    # Two Microsoft subscriptions
    s.sub("Xbox Game Pass", "monthly", False,
          note="Same biller as Microsoft 365 (Microsoft*); cancelled after May 2026.")
    for y, m in months(2025, 11, 2026, 5):
        d = dom(y, m, 7)
        add(d, -17.99, rng.choice(["Microsoft*Xbox", "Microsoft*Ultimate 1 Mon", "MSFT * E0400" + digits(rng, 5)]), "Xbox Game Pass")
    s.sub("Microsoft 365 Personal", "monthly", True, price_rise=True)
    for y, m in months(2025, 11, 2026, 10):
        d = dom(y, m, 2)
        add(d, -(7.00 if (y, m) < (2026, 3) else 10.00),
            rng.choice(["Microsoft*Microsoft 365 P", "MSFT * Microsoft 365", "Microsoft*Store"]), "Microsoft 365 Personal")
    # Revolut's own plan fee
    s.sub("Revolut Premium plan", "monthly", True,
          note="Bank's own plan fee (Type FEE); same price and cadence as Strava.")
    for y, m in months(2025, 11, 2026, 10):
        add(dom(y, m, 1), -7.99, "Premium plan fee", "Revolut Premium plan", typ="FEE")
    # Strava, with one declined attempt
    s.sub("Strava", "monthly", True,
          note="April attempt on the 16th was DECLINED (not charged) and retried successfully next day; the declined row is neither a charge nor a duplicate.")
    for y, m in months(2025, 11, 2026, 10):
        d = dom(y, m, 16)
        if (y, m) == (2026, 4):
            add(d, -7.99, "Strava", None, state="DECLINED")
            d += ONE
        add(d, -7.99, rng.choice(["Strava", "Strava Inc.", "STRAVA.COM"]), "Strava")

    # ---------------- noise ----------------
    for y, m in months(2025, 11, 2026, 10):
        d = biz(dom(y, m, 25))
        add(d, 2840.15, "Payment from Corrib Software Ltd", typ="TRANSFER")
        add(biz(D(y, m, 1)), -1400.00, "To Aoife Brennan", typ="TRANSFER")
        add(biz(D(y, m, 20)), -r2(rng.uniform(55, 132)), "Electric Ireland", typ="TRANSFER")
    d = D(2025, 11, 3)
    while d <= D(2026, 10, 28):
        add(d, -r2(rng.uniform(11, 79)), rng.choice(["Tesco", "Lidl", "Tesco Express", "SuperValu Rathmines"]))
        d += dt.timedelta(days=rng.randint(11, 17))
    for _ in range(8):
        d = s.start + dt.timedelta(days=rng.randint(2, 360))
        add(d, -r2(rng.choice([18.5, 24.0, 31.2, 42.8, 27.3])), "Bunsen")
    for _ in range(6):
        d = s.start + dt.timedelta(days=rng.randint(2, 360))
        add(d, -r2(rng.uniform(45, 70)), "Circle K")
    for _ in range(9):
        d = s.start + dt.timedelta(days=rng.randint(2, 360))
        add(d, -r2(rng.uniform(7.2, 26.9)), "Uber")
    for d, a in [(D(2025, 12, 4), 16.49), (D(2026, 3, 9), 16.49), (D(2026, 6, 1), 17.20), (D(2026, 9, 8), 16.49)]:
        add(d, -a, "Boots")
    for d in [D(2026, 1, 24), D(2026, 4, 25), D(2026, 8, 8)]:
        add(d, -10.00, "Flyefit Day Pass")
    for d in [D(2025, 11, 14), D(2026, 2, 13), D(2026, 5, 15), D(2026, 8, 14), D(2026, 10, 9)]:
        add(d, 100.00, "Top-Up by *7731", typ="TOPUP")
    add(D(2026, 2, 3), -180.00, "Exchanged to GBP", typ="EXCHANGE")
    add(D(2026, 7, 6), -95.00, "Exchanged to USD", typ="EXCHANGE")
    add(D(2026, 1, 10), -89.99, "Zara")
    add(D(2026, 1, 19), 89.99, "Zara", typ="CARD_REFUND")
    add(D(2026, 3, 28), -54.20, "Amazon.ie")
    add(D(2026, 9, 18), -312.40, "Ryanair")
    s.not_subs = [
        "Tesco / Lidl / SuperValu groceries (varying amounts)",
        "rent transfer to Aoife Brennan (monthly 1400.00)",
        "salary Corrib Software Ltd",
        "Electric Ireland (monthly, amount varies - utility)",
        "Bunsen (repeated restaurant)",
        "Circle K fuel",
        "Uber rides (varying; only Uber One 5.99 is the subscription)",
        "Boots pharmacy (roughly quarterly, 16.49-17.20)",
        "Flyefit day pass bought three times",
        "top-ups, currency exchanges",
        "Zara purchase and refund, Amazon.ie, Ryanair one-offs",
        "the DECLINED Strava attempt on 2026-04-16",
    ]
    return s


def write_rev(s):
    rows = s.chrono()
    bal = 2380.00
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["Type", "Product", "Started Date", "Completed Date", "Description", "Amount", "Fee", "Currency", "State", "Balance"])
    for t in rows:
        e = t["extra"]
        started = f"{t['date']:%Y-%m-%d} {e['time']}"
        if e["state"] == "COMPLETED":
            bal = r2(bal + t["amt"])
            h, mi, se = map(int, e["time"].split(":"))
            st = dt.datetime(t["date"].year, t["date"].month, t["date"].day, h, mi, se)
            cdt = st + dt.timedelta(days=e["lag"], seconds=61 + (len(t["desc"]) * 977 + t["date"].day * 131) % 5400)
            completed = f"{cdt:%Y-%m-%d %H:%M:%S}"
            b = f"{bal:.2f}"
        else:
            completed, b = "", ""
        w.writerow([e["typ"], "Current", started, completed, t["desc"], f"{t['amt']:.2f}", "0.00", "EUR", e["state"], b])
    return buf.getvalue()


# ---------------------------------------------------------------------------
# 4. Dutch bank, ING-like
# ---------------------------------------------------------------------------
OWN_IBAN = "NL42INGB0001234567"


def build_nl(rng):
    s = Stmt("nl-ing-style.csv", D(2026, 1, 2), D(2026, 10, 29))

    def card(naam, d, fx=None):
        med = (f"Pasvolgnr: 004 {d:%d-%m-%Y} {rng.randint(7, 22):02d}:{rng.randint(0, 59):02d} "
               f"Transactie: {alnum(rng, 6)} Term: {alnum(rng, 8)}")
        if fx:
            med += f" Valuta: {fx[0]:.2f} USD Koers: {fx[1]:.6f} Opslag: 0,15 EUR".replace(".", ",")
        else:
            med += rng.choice(["", " Apple Pay", " Google Pay"])
        return dict(naam=naam, tegen="", code="BA", muts="Betaalautomaat", med=med)

    def incasso(naam, omschr, iid, mid, d):
        med = (f"Naam: {naam} Omschrijving: {omschr} IBAN: NL{rng.randint(10, 99)}{rng.choice(['ABNA', 'RABO', 'INGB', 'DEUT'])}0{digits(rng, 9)} "
               f"Kenmerk: {digits(rng, 12)} Machtiging ID: {mid} Incassant ID: {iid} Doorlopende incasso "
               f"Datum/Tijd: {d:%d-%m-%Y} 0{rng.randint(1, 6)}:{rng.randint(10, 59)}")
        return dict(naam=naam, tegen=f"NL{rng.randint(10, 99)}ABNA0{digits(rng, 9)}", code="IC", muts="Incasso", med=med)

    def add(d, amt, f, sub=None, dup=False):
        s.add(d, amt, f["naam"] + " | " + f["med"], sub, dup, **f)

    s.sub("Ziggo", "monthly", True, price_rise=True)
    for y, m in months(2026, 1, 2026, 10):
        d = biz(D(y, m, 25)) if (y, m) != (2026, 10) else D(2026, 10, 26)
        add(d, -(52.50 if m < 7 else 54.75),
            incasso(rng.choice(["Ziggo Services BV", "ZIGGO SERVICES B.V."]), f"Factuur {digits(rng, 9)} Klantnr 30214877 {y}-{m:02d}",
                    "NL56ZZZ302148770000", "ZG-30214877-01", d), "Ziggo")
    s.sub("Odido mobile", "monthly", True)
    for y, m in months(2026, 1, 2026, 10):
        d = biz(D(y, m, 22))
        add(d, -20.00, incasso(rng.choice(["Odido Netherlands B.V.", "ODIDO NETHERLANDS BV"]), f"Klantnummer 1.29988341 Factuur {digits(rng, 10)}",
                               "NL19ZZZ270886890000", "OD0012998834", d), "Odido mobile")
    s.sub("Videoland", "monthly", True,
          note="Same price and cadence (8,99 monthly) as Disney+; billed by RTL Nederland.")
    for y, m in months(2026, 1, 2026, 10):
        d = biz(D(y, m, 7))
        add(d, -8.99, incasso("RTL Nederland Interactief B.V.", rng.choice(["Videoland abonnement", f"VL{digits(rng, 8)} Videoland Basis", "Abonnement RTL"]),
                              "NL77ZZZ330311430000", "VL" + "7783321", d), "Videoland")
    s.sub("Disney+ (via PayPal)", "monthly", True,
          note="Debtor name is PayPal; the service is named only in some months' description.")
    for y, m in months(2026, 1, 2026, 10):
        d = biz(D(y, m, 12))
        om = rng.choice([f"{digits(rng, 13)} PAYPAL DISNEY PLUS", f"{digits(rng, 13)} {digits(rng, 4)} PAYPAL",
                         f"1048{digits(rng, 9)} Aankoop bij Disney Plus"])
        add(d, -8.99, incasso("PayPal Europe S.a.r.l. et Cie S.C.A", om, "LU96ZZZ0000000000000000058", "5J2P22KZ7QXCA", d), "Disney+ (via PayPal)")
    s.sub("Nintendo Switch Online", "quarterly", True,
          note="3-month plan; the April renewal was charged twice.")
    for d in [D(2026, 1, 19), D(2026, 4, 20), D(2026, 7, 20), D(2026, 10, 19)]:
        add(d, -7.99, card(rng.choice(["Nintendo of Europe", "NINTENDO EUROPE GMBH", "Nintendo eShop"]), d), "Nintendo Switch Online")
        if d.month == 4:
            add(d + ONE, -7.99, card("Nintendo eShop", d + ONE), "Nintendo Switch Online", dup=True)
    s.sub("Storytel", "monthly", False)
    for y, m in months(2026, 1, 2026, 4):
        d = biz(D(y, m, 3))
        add(d, -12.99, incasso("Storytel B.V.", f"Storytel abonnement {m:02d}-{y}", "NL24ZZZ551206610000", "ST-882140", d), "Storytel")
    s.sub("Patreon (billed in USD)", "monthly", True,
          note="USD 6.00 converted to EUR (Valuta/Koers in Mededelingen), so the amount wobbles; not a price rise.")
    for y, m in months(2026, 1, 2026, 10):
        d = biz(D(y, m, 1)) if (y, m) != (2026, 1) else D(2026, 1, 2)
        eur, rate = fx_eur(rng, 6.00)
        eur = r2(eur + 0.15)
        add(d, -eur, card(rng.choice(["Patreon* Membership", "PATREON MEMBERSHIP", "Patreon"]), d, fx=(6.00, rate)), "Patreon (billed in USD)")

    # ---------------- noise ----------------
    def ov(naam, iban, oms, d):
        return dict(naam=naam, tegen=iban, code="GT", muts="Online bankieren",
                    med=f"Naam: {naam} Omschrijving: {oms} IBAN: {iban} Valutadatum: {d:%d-%m-%Y}")

    def bij(naam, iban, oms, d):
        return dict(naam=naam, tegen=iban, code="OV", muts="Overschrijving",
                    med=f"Naam: {naam} Omschrijving: {oms} IBAN: {iban} Kenmerk: {digits(rng, 12)} Valutadatum: {d:%d-%m-%Y}")

    for y, m in months(2026, 1, 2026, 10):
        d = biz(dom(y, m, 24))
        add(d, 3105.62 + (2380.00 if m == 5 else 0), bij("Van Dijk Logistiek BV", "NL08RABO0312456789", f"Salaris {m:02d}-{y}" + (" incl. vakantiegeld" if m == 5 else ""), d))
        d = biz(dom(y, m, 1)) if (y, m) != (2026, 1) else D(2026, 1, 2)
        add(d, -1150.00, ov("J. de Vries", "NL71ABNA0417799012", f"Huur {m:02d}-{y} Kinkerstraat 88-2", d))
        d = biz(D(y, m, 17))
        add(d, -r2(rng.uniform(86, 152) if m in (1, 2, 3, 10) else rng.uniform(52, 84)),
            incasso("Eneco Consumenten B.V.", f"Termijnfactuur {digits(rng, 10)}", "NL31ZZZ240563910000", "EN-55129033", d))
    d = D(2026, 1, 3)
    while d <= D(2026, 10, 28):
        add(d, -r2(rng.uniform(9, 74)), card(rng.choice(["Albert Heijn 1430 AMSTERDAM", "Jumbo Amsterdam Kinkerstr", "AH to go 5821 AMSTERDAM", "Lidl 0298 Amsterdam"]), d))
        d += dt.timedelta(days=rng.randint(7, 11))
    for _ in range(8):
        d = s.start + dt.timedelta(days=rng.randint(2, 295))
        add(d, -r2(rng.choice([14.5, 22.0, 27.8, 33.4, 19.2])), card("Cafe de Klos AMSTERDAM", d))
    for _ in range(5):
        d = s.start + dt.timedelta(days=rng.randint(2, 295))
        add(d, -r2(rng.uniform(48, 71)), card("Shell Amstelveen", d))
    for d, a in [(D(2026, 2, 10), 14.20), (D(2026, 5, 6), 14.20), (D(2026, 8, 11), 15.05)]:
        add(d, -a, card("Apotheek Overtoom AMSTERDAM", d))
    for d in [D(2026, 2, 21), D(2026, 6, 6), D(2026, 9, 26)]:
        add(d, -12.50, card("SportCity Dagpas AMSTERDAM", d))
    for _ in range(4):
        d = s.start + dt.timedelta(days=rng.randint(2, 295))
        add(d, -r2(rng.uniform(19, 41)), card("Thuisbezorgd.nl via Takeaway", d))
    add(D(2026, 3, 4), -89.00, ov("bol.com b.v.", "NL27INGB0000026500", f"Bestelling {digits(rng, 10)} iDEAL", D(2026, 3, 4)))
    add(D(2026, 3, 16), 89.00, bij("bol.com b.v.", "NL27INGB0000026500", "Terugbetaling retour bestelling", D(2026, 3, 16)))
    add(D(2026, 6, 23), -349.00, ov("Coolblue B.V.", "NL42INGB0006668383", f"Order {digits(rng, 8)} iDEAL", D(2026, 6, 23)))
    for d, a, who in [(D(2026, 2, 1), 18.50, "M. Jansen"), (D(2026, 5, 17), 32.00, "S. Bakker"), (D(2026, 9, 13), 21.75, "M. Jansen")]:
        add(d, a, bij(who, "NL55RABO0" + digits(rng, 9), "Tikkie betaalverzoek etentje", d))
    s.not_subs = [
        "Albert Heijn / Jumbo / Lidl groceries (varying amounts)",
        "rent transfer to J. de Vries (monthly 1150,00)",
        "salary Van Dijk Logistiek BV (May includes holiday pay)",
        "Eneco energy direct debit (monthly, amount varies - utility)",
        "Cafe de Klos (repeated restaurant)",
        "Shell fuel",
        "Apotheek Overtoom (roughly quarterly, 14,20-15,05)",
        "SportCity day pass (Dagpas) bought three times",
        "Thuisbezorgd food orders",
        "bol.com purchase and refund, Coolblue one-off",
        "Tikkie incoming payments",
    ]
    return s


def write_nl(s):
    rows = s.chrono()
    bal = 1872.40
    out = []
    for t in rows:
        e = t["extra"]
        bal = r2(bal + t["amt"])
        out.append([t["date"].strftime("%Y%m%d"), e["naam"], OWN_IBAN, e["tegen"], e["code"],
                    "Af" if t["amt"] < 0 else "Bij", f"{abs(t['amt']):.2f}".replace(".", ","), e["muts"], e["med"],
                    f"{bal:.2f}".replace(".", ","), ""])
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", quoting=csv.QUOTE_ALL, lineterminator="\n")
    w.writerow(["Datum", "Naam / Omschrijving", "Rekening", "Tegenrekening", "Code", "Af Bij", "Bedrag (EUR)",
                "Mutatiesoort", "Mededelingen", "Saldo na mutatie", "Tag"])
    for r in reversed(out):
        w.writerow(r)
    return buf.getvalue()


def main():
    rng = random.Random(SEED)
    os.makedirs(OUT, exist_ok=True)
    gold = {}
    for build, write in [(build_fr, write_fr), (build_es, write_es), (build_rev, write_rev), (build_nl, write_nl)]:
        s = build(rng)
        assert 120 <= len(s.tx) <= 200, (s.name, len(s.tx))
        assert 6 <= len(s.meta) <= 9, s.name
        with open(os.path.join(OUT, s.name), "w", encoding="utf-8", newline="") as f:
            f.write(write(s))
        gold[s.name] = s.gold()
    with open(os.path.join(HERE, "gold.json"), "w", encoding="utf-8") as f:
        json.dump(gold, f, indent=1, ensure_ascii=False)
        f.write("\n")
    for k, v in gold.items():
        print(f"{k}: {v['rows']} rows, {len(v['recurring'])} recurring")


if __name__ == "__main__":
    main()
