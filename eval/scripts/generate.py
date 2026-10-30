"""Generate invented bank statements + gold.json for the ghost-charges eval."""
import csv, json, random, calendar, datetime as dt, io, os

OUT = "/home/claude/ghost-charges/eval"
D = dt.date
ONE = dt.timedelta(days=1)


def wkd_shift(d):
    while d.weekday() >= 5:
        d += ONE
    return d


def mdate(y, m, day):
    return D(y, m, min(day, calendar.monthrange(y, m)[1]))


def months(y, m, n):
    for _ in range(n):
        yield y, m
        m += 1
        if m == 13:
            y, m = y + 1, 1


class Book:
    def __init__(self, seed):
        self.rng = random.Random(seed)
        self.tx = []      # dicts: date, amount(signed), fields..., tag, dup
        self.gold = {}    # tag -> meta

    def add(self, date, amount, tag=None, dup=False, **f):
        self.tx.append(dict(date=date, amount=round(amount, 2), tag=tag, dup=dup, **f))

    def sub(self, tag, merchant, cadence, active, rise, trial):
        self.gold[tag] = dict(merchant=merchant, cadence=cadence, active_at_end=active,
                              price_rise=rise, trial_converted=trial)

    def build_gold(self, desc_key):
        rec, dups = [], []
        for tag, meta in self.gold.items():
            rows = sorted([t for t in self.tx if t["tag"] == tag and not t["dup"]], key=lambda t: t["date"])
            ex = []
            for t in rows:
                s = desc_key(t)
                if s not in ex:
                    ex.append(s)
            rec.append(dict(merchant=meta["merchant"], cadence=meta["cadence"],
                            amounts=[abs(t["amount"]) for t in rows], count=len(rows),
                            first=rows[0]["date"].isoformat(), last=rows[-1]["date"].isoformat(),
                            active_at_end=meta["active_at_end"], price_rise=meta["price_rise"],
                            trial_converted=meta["trial_converted"], descriptor_examples=ex[:4],
                            **({"note": meta["note"]} if "note" in meta else {})))
            for t in self.tx:
                if t["tag"] == tag and t["dup"]:
                    dups.append(dict(merchant=meta["merchant"], date=t["date"].isoformat(),
                                     amount=abs(t["amount"]), descriptor=desc_key(t)))
        return rec, dups


# ---------------------------------------------------------------- ITALY
IT_M = "GENNAIO FEBBRAIO MARZO APRILE MAGGIO GIUGNO LUGLIO AGOSTO SETTEMBRE OTTOBRE NOVEMBRE DICEMBRE".split()


def italy():
    b = Book(11)
    r = b.rng
    card = "CARTA N. *4417"

    def pos(date, amt, merch, country="ITA", tag=None, dup=False, post_lag=None):
        lag = post_lag if post_lag is not None else r.choice([0, 1, 1, 2])
        post = wkd_shift(date + dt.timedelta(days=lag))
        a = f"{amt:.2f}".replace(".", ",")
        desc = f"PAGAMENTO POS {a} EUR DEL {date:%d.%m.%Y} A ({country}) {merch} {card}"
        b.add(post, -amt, tag, dup, valuta=date, desc=desc)

    def paypal(date, amt, merch, ref, tag=None, dup=False):
        post = wkd_shift(date + ONE)
        desc = f"PAGAMENTO TRAMITE PAYPAL {merch} ID {ref} {card}"
        b.add(post, -amt, tag, dup, valuta=date, desc=desc)

    def sdd(date, amt, creditor, cid, tag=None):
        d = wkd_shift(date)
        desc = f"ADDEBITO SDD {creditor} CID {cid} MANDATO N. {r.randint(10**8, 10**9-1)}"
        b.add(d, -amt, tag, valuta=d, desc=desc)

    def other(date, amt, desc, valuta=None):
        d = wkd_shift(date)
        b.add(d, amt, None, valuta=valuta or d, desc=desc)

    ML = list(months(2025, 11, 12))
    # Netflix monthly, price rise Apr 2026, descriptor switches POS -> POS alt -> PayPal
    b.sub("netflix", "Netflix", "monthly", True, True, False)
    for i, (y, m) in enumerate(ML):
        d = mdate(y, m, 6)
        amt = 13.99 if (y, m) < (2026, 4) else 15.99
        if i < 5:
            pos(d, amt, "NETFLIX.COM AMSTERDAM", "NLD", "netflix")
        elif i < 9:
            pos(d, amt, "NETFLIX COM 866-579-7172", "NLD", "netflix")
        else:
            paypal(d, amt, "*NETFLIX INTERNATIONAL B.V.", f"{r.randint(10**12,10**13-1)}", "netflix")
    # Spotify via PayPal, cancelled after May 2026
    b.sub("spotify", "Spotify", "monthly", False, False, False)
    for y, m in ML[:7]:
        paypal(mdate(y, m, 18) + dt.timedelta(days=r.choice([0, 0, 1])), 10.99,
               r.choice(["*SPOTIFY", "*SPOTIFY P2A91C3F7E", "SPOTIFY AB"]), f"{r.randint(10**12,10**13-1)}", "spotify")
    # Fastweb internet SDD
    b.sub("fastweb", "Fastweb", "monthly", True, False, False)
    for y, m in ML:
        sdd(mdate(y, m, 3), 27.95, "FASTWEB SPA FATT. " + f"{m:02d}/{y}", "IT45ZZZ0000012345670151", "fastweb")
    # Iliad mobile SDD
    b.sub("iliad", "Iliad", "monthly", True, False, False)
    for y, m in ML:
        sdd(mdate(y, m, 22), 9.99, "ILIAD ITALIA S.P.A.", "IT77ZZZ0000098765430017", "iliad")
    # Amazon Prime yearly renewal (both renewals inside window: 2025-11-02, 2026-10-29)
    b.sub("prime", "Amazon Prime", "yearly", True, False, False)
    b.gold["prime"]["note"] = "Both yearly renewals fall inside the window (start and end of the export); renewal day drifted by a few days."
    pos(D(2025, 11, 2), 49.90, "AMAZON PRIME*RT5KQ1Z74 AMAZON.IT/PRM", "LUX", "prime", post_lag=1)
    pos(D(2026, 10, 28), 49.90, "AMZ PRIME IT RINNOVO*NB82HX0 AMAZON.IT", "LUX", "prime", post_lag=1)
    # Telepass quarterly
    b.sub("telepass", "Telepass", "quarterly", True, False, False)
    for d in [D(2025, 12, 10), D(2026, 3, 10), D(2026, 6, 10), D(2026, 9, 10)]:
        sdd(d, 11.70, "TELEPASS S.P.A. CANONE TRIMESTRALE", "IT12ZZZ0000009771230584", "telepass")
    # Disney+ promo 1,99 in Jan then 9,99 (trial converted, started late)
    b.sub("disney", "Disney+", "monthly", True, False, True)
    for i, (y, m) in enumerate(ML[2:]):
        pos(mdate(y, m, 14), 1.99 if i == 0 else 9.99,
            "DISNEY PLUS AMSTERDAM" if i % 3 else "DISNEYPLUS*X7F2 DISNEYPLUS.COM", "NLD", "disney")
    # YouTube Premium via Google (obscure) + duplicate in July
    b.sub("youtube", "YouTube Premium", "monthly", True, False, False)
    for y, m in ML:
        d = mdate(y, m, 25)
        pos(d, 12.99, r.choice(["GOOGLE *YouTubePremium g.co/helppay#", "GOOGLE*YOUTUBE PREMIUM"]), "IRL", "youtube", post_lag=1)
        if (y, m) == (2026, 7):
            pos(d, 12.99, "GOOGLE *YouTubePremium g.co/helppay#", "IRL", "youtube", dup=True, post_lag=1)

    # --- non subscriptions
    for y, m in ML:
        sal = 1850.00 + (1640.00 if m == 12 else 0)
        other(mdate(y, m, 27), sal, f"ACCREDITO EMOLUMENTI STIPENDIO {IT_M[m-1]} {y} ORD: TECNOSTAMPA ROSSETTI SRL")
        other(mdate(y, m, 1), -750.00, f"BONIFICO ISTANTANEO DISPOSTO A FAVORE DI GIULIA MARCHETTI CAUSALE CANONE LOCAZIONE {m:02d}/{y}")
    d = D(2025, 11, 1)
    while d <= D(2026, 10, 31):
        sat = d + dt.timedelta(days=(5 - d.weekday()) % 7)
        if sat <= D(2026, 10, 31) and r.random() < 0.85:
            pos(sat, round(r.uniform(38, 112), 2), "ESSELUNGA MILANO VIA FERRARI", "ITA")
        d = sat + dt.timedelta(days=7)
    for _ in range(9):
        pos(D(2025, 11, 1) + dt.timedelta(days=r.randint(0, 360)), round(r.uniform(45, 70), 2), "ENI STATION 4021 MILANO", "ITA")
    for _ in range(6):
        pos(D(2025, 11, 1) + dt.timedelta(days=r.randint(0, 360)), round(r.uniform(32, 78), 2), "TRATTORIA DA PINO MILANO", "ITA")
    for d in [D(2026, 2, 7), D(2026, 8, 19)]:
        pos(d, 12.00, "MCFIT INGRESSO GIORNALIERO MILANO", "ITA")
    for _ in range(5):
        dd = D(2025, 11, 1) + dt.timedelta(days=r.randint(0, 360))
        other(dd, -r.choice([50.0, 100.0, 150.0]), f"PRELIEVO BANCOMAT DEL {dd:%d.%m.%Y} ATM 08321 MILANO {card}", valuta=dd)
    for _ in range(4):
        pos(D(2025, 11, 1) + dt.timedelta(days=r.randint(0, 360)), round(r.uniform(15, 140), 2), "AMAZON MKTPLACE PMTS AMAZON.IT", "LUX")
    paypal(D(2026, 3, 21), 89.00, "*VINTED", "4471882031001")
    other(D(2026, 5, 12), -120.00, "BONIFICO DISPOSTO A FAVORE DI LUCA BERTOLDI CAUSALE REGALO MATRIMONIO")
    other(D(2026, 1, 15), 40.00, "BONIFICO A VOSTRO FAVORE DA ANNA COLOMBO CAUSALE QUOTA CENA")
    for d in [D(2026, 1, 9), D(2026, 4, 3), D(2026, 7, 10), D(2026, 10, 9)]:
        pos(d, 7.50, "FARMACIA SAN BABILA MILANO", "ITA")

    b.tx = [t for t in b.tx if t["date"] <= D(2026, 10, 31)]
    b.tx.sort(key=lambda t: (t["date"], t["desc"]))
    it = lambda x: f"{abs(x):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    with open(f"{OUT}/statements/it-intesa-style.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";", quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
        w.writerow(["Data contabile", "Data valuta", "Descrizione", "Accrediti", "Addebiti"])
        for t in reversed(b.tx):  # newest first, like the home-banking export
            w.writerow([f"{t['date']:%d/%m/%Y}", f"{t['valuta']:%d/%m/%Y}", t["desc"],
                        it(t["amount"]) if t["amount"] > 0 else "",
                        it(t["amount"]) if t["amount"] < 0 else ""])
    rec, dups = b.build_gold(lambda t: t["desc"])
    return b, rec, dups, ["Esselunga weekly shop (varying amounts, Saturdays)", "rent transfer to Giulia Marchetti (BONIFICO, monthly)",
                          "salary TECNOSTAMPA (monthly, December includes 13th month)", "ENI fuel", "Trattoria Da Pino (repeated restaurant)",
                          "McFit day pass bought twice (Feb, Aug)", "Farmacia San Babila (roughly quarterly, same amount 7,50 - pharmacy, not a subscription)",
                          "Amazon Marketplace one-off orders (not Prime)", "ATM withdrawals"]


# ---------------------------------------------------------------- UK
def uk():
    b = Book(22)
    r = b.rng
    cats = dict(ent="Entertainment", bills="Bills", groc="Groceries", eat="Eating out", trans="Transport",
                shop="Shopping", inc="Income", gen="General", per="Personal care", fam="Family")

    def card(date, amt, name, desc, cat, tag=None, dup=False, local=None):
        b.add(date, -amt, tag, dup, typ="Card payment", name=name, cat=cats[cat], desc=desc, local=local,
              time=f"{r.randint(0,23):02d}:{r.randint(0,59):02d}:{r.randint(0,59):02d}")

    def dd(date, amt, name, desc, cat, tag=None, typ="Direct Debit"):
        d = wkd_shift(date)
        b.add(d, amt, tag, typ=typ, name=name, cat=cats[cat], desc=desc, local=None, time="05:00:00")

    ML = list(months(2025, 11, 12))
    b.sub("netflix", "Netflix", "monthly", True, True, False)
    for y, m in ML:
        amt = 10.99 if (y, m) < (2026, 5) else 12.99
        card(mdate(y, m, 9) + dt.timedelta(days=r.choice([0, 0, 1])), amt, "Netflix",
             r.choice(["NETFLIX.COM            AMSTERDAM     NLD", "NETFLIX.COM            LOS GATOS     USA", "Netflix.com            866-579-7172  NLD"]), "ent", "netflix")
    b.sub("icloud", "Apple iCloud+", "monthly", True, False, False)
    for y, m in ML:
        card(mdate(y, m, 4), 2.99, "Apple", "APPLE.COM/BILL         CORK          IRL", "bills", "icloud")
    b.sub("appletv", "Apple TV+ (billed via Apple)", "monthly", True, False, False)
    b.gold["appletv"]["note"] = "Same merchant name 'Apple' and almost the same descriptor as iCloud+; separate subscription, told apart by amount (8.99) and charge day (~17th)."
    for y, m in ML[4:]:
        card(mdate(y, m, 17), 8.99, "Apple", "APPLE.COM/BILL         ITUNES.COM    IRL", "ent", "appletv")
    b.sub("puregym", "PureGym", "monthly", False, False, False)
    for y, m in ML[:6]:
        dd(mdate(y, m, 1), -24.99, "PureGym Ltd", "PUREGYM LTD            PG-0048813", "per", "puregym")
    b.sub("oddbox", "Oddbox", "weekly", True, False, False)
    d = D(2026, 7, 2)
    while d <= D(2026, 10, 31):
        card(d + dt.timedelta(days=r.choice([0, 0, 1])), 13.49, "Oddbox", "ODDBOX                 LONDON        GBR", "groc", "oddbox")
        d += dt.timedelta(days=7)
    b.sub("audible", "Audible", "monthly", True, False, True)
    for i, (y, m) in enumerate(ML[2:]):
        card(mdate(y, m, 12), 0.99 if i == 0 else 8.99, "Audible",
             "AUDIBLE UK             ADBL.CO/PYMT  GBR" if i % 2 else "Audible UK*2F8KD71L3   amzn.co.uk/pm LUX", "ent", "audible")
    b.sub("cursor", "Cursor (AI code editor, billed in USD)", "monthly", True, False, False)
    b.gold["cursor"]["note"] = "Fixed USD 20.00 price; GBP amount varies every month only because of the FX rate (not a price rise)."
    for y, m in ML:
        rate = round(r.uniform(1.25, 1.36), 4)
        card(mdate(y, m, 21) + dt.timedelta(days=r.choice([0, 1])), round(20 / rate, 2), "CURSOR AI POWERED IDE",
             "CURSOR AI POWERED IDE  NEW YORK      USA", "shop", "cursor", local=-20.00)
    b.sub("harrys", "Harry's razor refills", "quarterly", True, False, False)
    for d in [D(2025, 11, 26), D(2026, 2, 25), D(2026, 5, 27), D(2026, 8, 26)]:
        card(d + dt.timedelta(days=r.choice([0, 1, 2])), 18.50, "Harry's", "HARRYS.COM             LONDON        GBR", "per", "harrys")
    b.sub("deliveroo", "Deliveroo Plus", "monthly", True, False, False)
    for y, m in ML:
        d = mdate(y, m, 28)
        card(d, 3.49, "Deliveroo", "DELIVEROO PLUS SUBS    LONDON        GBR", "eat", "deliveroo")
        if (y, m) == (2026, 8):
            card(d + ONE, 3.49, "Deliveroo", "DELIVEROO PLUS SUBS    LONDON        GBR", "eat", "deliveroo", dup=True)

    for y, m in ML:
        dd(mdate(y, m, 26), 2640.00, "Brightwell Analytics Ltd", "BRIGHTWELL ANALYTICS   SALARY", "inc", typ="Faster payment")
        dd(mdate(y, m, 1), -1150.00, "Harriet Pemberton", "RENT FLAT 2 HARRIET PEMBERTON", "bills", typ="Standing order")
        dd(mdate(y, m, 15), -r.choice([62.10, 58.40, 71.80, 66.25, 49.90, 75.30]), "Octopus Energy", "OCTOPUS ENERGY         A-4F21C0", "bills")
    d = D(2025, 11, 2)
    while d <= D(2026, 10, 31):
        if r.random() < 0.42:
            card(d + dt.timedelta(days=r.choice([0, 1, 2])), round(r.uniform(22, 96), 2), "Tesco", "TESCO STORES 3271      LONDON        GBR", "groc")
        d += dt.timedelta(days=7)
    for _ in range(6):
        card(D(2025, 11, 1) + dt.timedelta(days=r.randint(0, 363)), round(r.uniform(2.8, 12.4), 2), "Transport for London",
             "TFL TRAVEL CH          TFL.GOV.UK/CP GBR", "trans")
    for _ in range(6):
        card(D(2025, 11, 1) + dt.timedelta(days=r.randint(0, 363)), round(r.uniform(6.5, 11.9), 2), "Pret A Manger", "PRET A MANGER          LONDON        GBR", "eat")
    for _ in range(4):
        card(D(2025, 11, 1) + dt.timedelta(days=r.randint(0, 363)), round(r.uniform(48, 72), 2), "Shell", "SHELL CLAPHAM          LONDON        GBR", "trans")
    for dd_ in [D(2026, 3, 14), D(2026, 9, 2)]:
        card(dd_, 25.00, "Gymbox", "GYMBOX DAY PASS        LONDON        GBR", "per")
    for _ in range(3):
        card(D(2025, 11, 1) + dt.timedelta(days=r.randint(0, 363)), round(r.uniform(20, 140), 2), "Amazon", "AMAZON.CO.UK*R82KD1    AMAZON.CO.UK  GBR", "shop")
    dd(D(2026, 6, 6), -45.00, "Tom Ashby", "TOM ASHBY              FESTIVAL", "fam", typ="Faster payment")

    b.tx = [t for t in b.tx if t["date"] <= D(2026, 10, 31)]
    b.tx.sort(key=lambda t: (t["date"], t["time"]))
    with open(f"{OUT}/statements/uk-monzo-style.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["Transaction ID", "Date", "Time", "Type", "Name", "Emoji", "Category", "Amount", "Currency",
                    "Local amount", "Local currency", "Notes and #tags", "Address", "Description"])
        for i, t in enumerate(b.tx):
            usd = t["local"] is not None
            w.writerow([f"tx_0000{r.getrandbits(60):015X}", t["date"].isoformat(), t["time"], t["typ"], t["name"], "",
                        t["cat"], f"{t['amount']:.2f}", "GBP", f"{t['local']:.2f}" if usd else f"{t['amount']:.2f}",
                        "USD" if usd else "GBP", "", "", t["desc"]])
    rec, dups = b.build_gold(lambda t: f"{t['name']} | {t['desc']}")
    return b, rec, dups, ["Tesco weekly-ish shop (varying amounts)", "rent standing order to Harriet Pemberton", "salary Brightwell Analytics",
                          "Octopus Energy direct debit (monthly bill, amount varies - a utility, not a forgotten subscription)",
                          "TfL travel", "Pret A Manger (repeated)", "Shell fuel", "Gymbox day pass bought twice", "Amazon one-off orders"]


# ---------------------------------------------------------------- US
def us():
    b = Book(33)
    r = b.rng

    def cardx(date, amt, desc, tag=None, dup=False):
        post = wkd_shift(date + dt.timedelta(days=r.choice([0, 1, 1, 2])))
        b.add(post, -amt, tag, dup, det="DEBIT", typ="DEBIT_CARD", desc=desc, chk="")

    ML = list(months(2025, 11, 12))
    b.sub("netflix", "Netflix", "monthly", True, True, False)
    for y, m in ML:
        d = mdate(y, m, 14)
        amt = 15.49 if (y, m) < (2026, 1) else 17.99
        desc = r.choice(["NETFLIX.COM 866-579-7172 CA", "NETFLIX.COM NETFLIX.COM CA", "NETFLIX  INC LOS GATOS CA"])
        cardx(d, amt, desc, "netflix")
        if (y, m) == (2026, 3):
            b.add(b.tx[-1]["date"], -amt, "netflix", True, det="DEBIT", typ="DEBIT_CARD", desc=desc, chk="")
    b.sub("spotify", "Spotify", "monthly", False, False, False)
    for y, m in ML[:8]:
        cardx(mdate(y, m, 3), 11.99, r.choice(["SPOTIFY USA 877-778-1161 NY", "Spotify USA New York NY", "SPOTIFY P2C81F0A9D NEW YORK NY"]), "spotify")
    b.sub("icloud", "Apple iCloud+", "monthly", True, False, False)
    for y, m in ML:
        cardx(mdate(y, m, 8), 2.99, "APPLE.COM/BILL 866-712-7753 CA", "icloud")
    b.sub("prime", "Amazon Prime", "yearly", True, False, False)
    cardx(D(2025, 11, 4), 139.00, "Amazon Prime*2K7XY12Q0 Amzn.com/bill WA", "prime")
    cardx(D(2026, 10, 26), 139.00, "AMAZON PRIME*NB4TT31A2 AMZN.COM/BILL WA", "prime")
    b.sub("dashpass", "DoorDash DashPass", "monthly", True, False, True)
    for i, (y, m) in enumerate(ML[3:]):
        cardx(mdate(y, m, 19), 1.00 if i == 0 else 9.99,
              "DD *DOORDASH DASHPASS 855-9731040 CA" if i % 3 else "DOORDASH*DASHPASS SAN FRANCISCO CA", "dashpass")
    b.sub("hellofresh", "HelloFresh", "weekly", False, False, False)
    d = D(2026, 3, 4)
    wk = 0
    while d <= D(2026, 6, 24):
        if wk != 6:  # one skipped (paused) week
            cardx(d, 69.93, r.choice(["HELLOFRESH 646-846-3663 NY", "HLLFRSH*HELLOFRESH US NEW YORK NY"]), "hellofresh")
        d += dt.timedelta(days=7)
        wk += 1
    b.sub("dsc", "Dollar Shave Club", "quarterly", True, False, False)
    for dd in [D(2025, 12, 2), D(2026, 3, 3), D(2026, 6, 2), D(2026, 9, 1)]:
        cardx(dd, 26.00, "DOLLAR SHAVE CLUB 310-975-8528 CA", "dsc")

    # non-subscriptions
    d = D(2025, 11, 7)
    while d <= D(2026, 10, 31):
        b.add(d, 1742.36, None, det="CREDIT", typ="ACH_CREDIT", desc="HARBORLINE LOGISTICS PAYROLL PPD ID: 9000112233", chk="")
        d += dt.timedelta(days=14)
    chk = 1041
    for y, m in ML:
        b.add(wkd_shift(mdate(y, m, 2) + dt.timedelta(days=r.choice([0, 1, 2]))), -2150.00, None, det="CHECK", typ="CHECK_PAID",
              desc=f"CHECK {chk}", chk=str(chk))
        chk += 1
        b.add(wkd_shift(mdate(y, m, 20)), -r.choice([84.12, 91.55, 77.08, 102.67, 69.30, 88.41]), None, det="DEBIT", typ="ACH_DEBIT",
              desc="CON ED OF NY CECONY PPD ID: 1131004000", chk="")
    d = D(2025, 11, 1)
    while d <= D(2026, 10, 28):
        if r.random() < 0.8:
            cardx(d + dt.timedelta(days=r.randint(0, 2)), round(r.uniform(31, 128), 2), "TRADER JOE S #552 BROOKLYN NY")
        d += dt.timedelta(days=r.choice([6, 7, 8]))
    for _ in range(7):
        cardx(D(2025, 11, 1) + dt.timedelta(days=r.randint(0, 360)), round(r.uniform(9, 160), 2),
              f"AMZN Mktp US*{''.join(r.choice('ABCDEFGHJKLMNPQRSTUVWXYZ0123456789') for _ in range(9))} Amzn.com/bill WA")
    for _ in range(6):
        cardx(D(2025, 11, 1) + dt.timedelta(days=r.randint(0, 360)), round(r.uniform(18, 44), 2), "JOE'S PIZZA BROOKLYN NY")
    for _ in range(5):
        cardx(D(2025, 11, 1) + dt.timedelta(days=r.randint(0, 360)), round(r.uniform(38, 61), 2), "SHELL OIL 57444529501 BROOKLYN NY")
    for dd in [D(2026, 1, 24), D(2026, 7, 11)]:
        cardx(dd, 15.00, "BLINK FITNESS DAY PASS BROOKLYN NY")
    for dd, amt, who in [(D(2026, 2, 13), 60.00, "Maya Okafor"), (D(2026, 8, 3), 35.00, "Daniel Reyes")]:
        b.add(dd, -amt, None, det="DEBIT", typ="QUICKPAY_DEBIT", desc=f"Zelle payment to {who} JPM99a{r.randint(10**7,10**8-1)}", chk="")
    for _ in range(3):
        dd = wkd_shift(D(2025, 11, 1) + dt.timedelta(days=r.randint(0, 360)))
        b.add(dd, -r.choice([60.0, 100.0, 200.0]), None, det="DEBIT", typ="ATM",
              desc=f"NON-CHASE ATM WITHDRAW {r.randint(100000,999999)} {dd:%m/%d} 345 FLATBUSH AVE BROOKLYN NY", chk="")

    b.tx = [t for t in b.tx if t["date"] <= D(2026, 10, 30)]
    b.tx.sort(key=lambda t: (t["date"], 0 if t["amount"] > 0 else 1, t["desc"]))
    bal = 3184.27
    for t in b.tx:
        bal = round(bal + t["amount"], 2)
        t["bal"] = bal
    with open(f"{OUT}/statements/us-chase-style.csv", "w", newline="", encoding="utf-8") as f:
        f.write("Details,Posting Date,Description,Amount,Type,Balance,Check or Slip #\n")
        for t in reversed(b.tx):  # Chase exports newest first, each data row has a trailing comma
            s = io.StringIO()
            csv.writer(s, lineterminator="").writerow([t["det"], f"{t['date']:%m/%d/%Y}", t["desc"], f"{t['amount']:.2f}",
                                                       t["typ"], f"{t['bal']:.2f}", t["chk"]])
            f.write(s.getvalue() + ",\n")
    rec, dups = b.build_gold(lambda t: t["desc"])
    return b, rec, dups, ["Trader Joe's weekly shop (varying amounts)", "rent paid by monthly paper check (CHECK 1041...)",
                          "biweekly payroll Harborline Logistics", "Con Ed electricity ACH (monthly, varying - utility)",
                          "AMZN Mktp US one-off orders (not Prime)", "Joe's Pizza (repeated restaurant)", "Shell fuel",
                          "Blink Fitness day pass bought twice", "Zelle transfers", "ATM withdrawals"]


# ---------------------------------------------------------------- DE
def de():
    b = Book(44)
    r = b.rng

    def iban():
        return "DE" + "".join(str(r.randint(0, 9)) for _ in range(20))

    def mc(date, amt, name, cat, tag=None, dup=False):
        b.add(date, -amt, tag, dup, emp=name, kto="", typ="MasterCard Zahlung", vz="", cat=cat)

    def ls(date, amt, name, vz, cat, tag=None, kto=None, typ="Lastschrift"):
        d = wkd_shift(date)
        b.add(d, amt, tag, emp=name, kto=kto or iban(), typ=typ, vz=vz, cat=cat)

    ML = list(months(2026, 1, 10))
    pp_iban = "LU89751000135104200E"
    b.sub("netflix", "Netflix (via PayPal)", "monthly", True, False, False)
    b.gold["netflix"]["note"] = "Empfänger is PayPal; the real merchant only appears in Verwendungszweck."
    for y, m in ML:
        ls(mdate(y, m, 11), -12.99, "PayPal Europe S.a.r.l. et Cie S.C.A",
           f"{r.randint(10**12,10**13-1)} PP.4471.PP . NETFLIX INTERNATIONAL B.V., Ihr Einkauf bei NETFLIX INTERNATIONAL B.V.",
           "Freizeit & Unterhaltung", "netflix", kto=pp_iban)
    b.sub("spotify", "Spotify", "monthly", True, True, False)
    for y, m in ML:
        d = mdate(y, m, 5) + dt.timedelta(days=r.choice([0, 1]))
        amt = 10.99 if (y, m) < (2026, 6) else 12.99
        mc(d, amt, r.choice(["Spotify", "SPOTIFY AB", "Spotify P3A0B7E2C1"]), "Freizeit & Unterhaltung", "spotify")
        if (y, m) == (2026, 8):
            mc(d, amt, "Spotify", "Freizeit & Unterhaltung", "spotify", dup=True)
    b.sub("o2", "O2 / Telefonica mobile", "monthly", True, False, False)
    o2 = iban()
    for y, m in ML:
        ls(mdate(y, m, 2), -19.99, "Telefonica Germany GmbH & Co. OHG",
           f"Kd-Nr. 6044718823 Rg-Nr. {r.randint(10**9,10**10-1)} Ihre Rechnung vom {mdate(y, m, 1) - ONE:%d.%m.%Y}",
           "Medien & Telekom", "o2", kto=o2)
    b.sub("rundfunk", "Rundfunkbeitrag (ARD ZDF Deutschlandradio)", "quarterly", True, False, False)
    rf = iban()
    for m in [1, 4, 7, 10]:
        ls(D(2026, m, 15), -55.08, "Rundfunk ARD, ZDF, DRadio",
           f"Beitragsnummer 512 873 409 Rundfunkbeitrag {m:02d}.2026 - {m+2:02d}.2026", "Haushalt & Nebenkosten", "rundfunk", kto=rf)
    b.sub("usc", "Urban Sports Club", "monthly", False, False, False)
    usc = iban()
    for y, m in ML[:5]:
        ls(mdate(y, m, 1), -49.00, "URBAN SPORTS GMBH", f"USC Mitgliedschaft M {m:02d}/2026 Mitglied 88213907", "Gesundheit & Drogerie", "usc", kto=usc)
    b.sub("notion", "Notion (billed via Paddle)", "monthly", True, False, False)
    for y, m in ML:
        mc(mdate(y, m, 23), 9.60, r.choice(["PADDLE.NET* NOTION", "PADDLE.NET* NOTION LABS"]), "Shopping", "notion")
    b.sub("kindle", "Kindle Unlimited", "monthly", True, False, True)
    for i, (y, m) in enumerate(ML[2:]):
        mc(mdate(y, m, 17), 0.00 if i == 0 else 11.99, "AMAZON DIGITAL KINDLE UNLTD" if i % 2 else "Amazon Digital Germany GmbH", "Medien & Telekom", "kindle")
    b.sub("dticket", "Deutschlandticket (BVG)", "monthly", True, False, False)
    bvg = iban()
    for y, m in ML:
        ls(mdate(y, m, 1), -63.00, "BVG Berliner Verkehrsbetriebe", f"Deutschlandticket Abo-Nr. 7731902 {m:02d}/2026", "Transport & Auto", "dticket", kto=bvg)

    emp = iban(); mie = iban()
    for y, m in ML:
        ls(mdate(y, m, 28), 3120.55, "Lindner & Vogt Software GmbH", f"LOHN/GEHALT {m:02d}/2026", "Einkommen", kto=emp, typ="Gutschrift")
        ls(mdate(y, m, 1), -1080.00, "Katharina Brandt", f"Miete {m:02d}/2026 Whg 3 OG links", "Haushalt & Nebenkosten", kto=mie, typ="Überweisung")
    d = D(2026, 1, 3)
    while d <= D(2026, 10, 31):
        if r.random() < 0.55:
            mc(d + dt.timedelta(days=r.choice([0, 1])), round(r.uniform(24, 89), 2), "REWE Markt GmbH", "Lebensmittel")
        d += dt.timedelta(days=7)
    for _ in range(5):
        mc(D(2026, 1, 1) + dt.timedelta(days=r.randint(0, 300)), round(r.uniform(19, 41), 2), "Lieferando.de", "Restaurants & Bars")
    for _ in range(4):
        mc(D(2026, 1, 1) + dt.timedelta(days=r.randint(0, 300)), round(r.uniform(28, 55), 2), "Trattoria Il Gabbiano", "Restaurants & Bars")
    for _ in range(3):
        mc(D(2026, 1, 1) + dt.timedelta(days=r.randint(0, 300)), round(r.uniform(52, 74), 2), "ARAL Station 2841", "Transport & Auto")
    for dd in [D(2026, 6, 20), D(2026, 9, 27)]:
        mc(dd, 14.90, "McFit Tageskarte", "Gesundheit & Drogerie")
    ls(D(2026, 4, 9), -25.00, "Jonas Weber", "Geburtstagsgeschenk Lena", "Sonstiges", typ="Überweisung")

    b.tx = [t for t in b.tx if t["date"] <= D(2026, 10, 31)]
    b.tx.sort(key=lambda t: (t["date"], t["emp"]))
    with open(f"{OUT}/statements/de-n26-style.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, quoting=csv.QUOTE_ALL, lineterminator="\n")
        w.writerow(["Datum", "Empfänger", "Kontonummer", "Transaktionstyp", "Verwendungszweck", "Kategorie",
                    "Betrag (EUR)", "Betrag (Fremdwährung)", "Fremdwährung", "Wechselkurs"])
        for t in b.tx:
            w.writerow([t["date"].isoformat(), t["emp"], t["kto"], t["typ"], t["vz"], t["cat"], f"{t['amount']:.2f}", "", "", ""])
    rec, dups = b.build_gold(lambda t: f"{t['emp']} | {t['vz']}".strip(" |"))
    return b, rec, dups, ["REWE weekly shop (varying amounts)", "rent Überweisung to Katharina Brandt", "salary Lindner & Vogt",
                          "Lieferando orders", "Trattoria Il Gabbiano (repeated restaurant)", "ARAL fuel",
                          "McFit Tageskarte (day pass) bought twice", "one-off transfer to Jonas Weber"]


gold = {}
for name, fn in [("it-intesa-style.csv", italy), ("uk-monzo-style.csv", uk), ("us-chase-style.csv", us), ("de-n26-style.csv", de)]:
    b, rec, dups, ns = fn()
    gold[name] = dict(rows=len(b.tx), recurring=rec, duplicates=dups, not_subscriptions=ns)
with open(f"{OUT}/gold.json", "w", encoding="utf-8") as f:
    json.dump(gold, f, indent=2, ensure_ascii=False)
for k, v in gold.items():
    print(k, v["rows"], len(v["recurring"]), len(v["duplicates"]))
