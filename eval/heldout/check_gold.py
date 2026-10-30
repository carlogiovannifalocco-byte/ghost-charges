#!/usr/bin/env python3
"""Independently re-parse each held-out CSV in its own bank format and verify gold.json.

Does not import generate.py. Each gold merchant is matched with a hand-written regex
(plus an amount filter where one biller carries two subscriptions).
"""
import csv
import datetime as dt
import io
import json
import os
import re
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
STMT = os.path.join(HERE, "statements")
errors = []


def err(f, msg):
    errors.append(f"{f}: {msg}")


def eu(s):  # '2 412,37' / '1.985,40' / '-9,99' / '3105,62'
    s = s.replace(" ", "").replace(" ", "").replace(".", "").replace(",", ".")
    return float(s)


# Each parser returns list of rows: dict(date, amount (signed), desc, ok)
def parse_fr(text):
    lines = text.split("\n")
    i = next(k for k, l in enumerate(lines) if l.startswith("Date;Libellé;"))
    rows = []
    for r in csv.reader(io.StringIO("\n".join(lines[i + 1:])), delimiter=";"):
        if not r or not r[0]:
            continue
        d = dt.datetime.strptime(r[0], "%d/%m/%Y").date()
        amt = -eu(r[2]) if r[2] else eu(r[3])
        rows.append(dict(date=d, amount=amt, desc=r[1], ok=True))
    return rows


def parse_es(text):
    lines = text.split("\n")
    i = next(k for k, l in enumerate(lines) if l.startswith("Fecha Operación;"))
    rows = []
    for r in csv.reader(io.StringIO("\n".join(lines[i + 1:])), delimiter=";"):
        if not r:
            continue
        rows.append(dict(date=dt.datetime.strptime(r[0], "%d/%m/%Y").date(), amount=eu(r[3]), desc=r[2], ok=True))
    return rows


def parse_rev(text):
    rows = []
    for r in csv.DictReader(io.StringIO(text)):
        rows.append(dict(date=dt.date.fromisoformat(r["Started Date"][:10]), amount=float(r["Amount"]),
                         desc=r["Description"], ok=r["State"] == "COMPLETED", typ=r["Type"]))
    return rows


def parse_nl(text):
    rows = []
    for r in csv.DictReader(io.StringIO(text), delimiter=";"):
        a = eu(r["Bedrag (EUR)"])
        rows.append(dict(date=dt.datetime.strptime(r["Datum"], "%Y%m%d").date(),
                         amount=-a if r["Af Bij"] == "Af" else a,
                         desc=r["Naam / Omschrijving"] + " | " + r["Mededelingen"], ok=True))
    return rows


I = re.I
FILES = {
    "fr-credit-agricole-style.csv": (parse_fr, {
        "Canal+": (r"^PRLV SEPA (GROUPE )?CANAL ?\+", None),
        "Free Mobile": (r"^PRLV SEPA FREE MOBILE", None),
        "Deezer": (r"^CB DEEZER", None),
        "Apple iCloud+": (r"^CB APPLE\.COM", 2.99),
        "Apple Music": (r"^CB APPLE\.COM", 10.99),
        "Amazon Prime": (r"^CB (AMAZON|AMZ) PRIME", None),
        "Basic-Fit": (r"BASIC FIT", None),
        "ChatGPT Plus (OpenAI, billed in USD)": (r"OPENAI|CHATGPT", None),
    }, ["ON AIR FITNESS", "PHARMACIE DU PARC", "LOYER .* GARNIER", "PRLV SEPA ENGIE"]),
    "es-santander-style.csv": (parse_es, {
        "Movistar (Telefonica)": (r"Recibo Telefonica De Espana", None),
        "Filmin": (r"filmin", None),
        "Google One": (r"Google (\*google (one|storage)|One,)", 1.99),
        "Duolingo Super (via Google Play)": (r"Google (\*duolingo|Play Apps|\*google Play)", 6.99),
        "PlayStation Plus": (r"playstation|sony interactive|psn\*", None),
        "Glovo Prime": (r"glovo", 5.99),
        "HBO Max": (r"hbo", None),
        "El Pais (digital subscription)": (r"el pais|prisa|elpais", None),
    }, ["Altafit Entrada Dia", "Farmacia", "Alquiler", "Iberdrola"]),
    "ie-revolut-style.csv": (parse_rev, {
        "HelloFresh": (r"hellofresh|hllfrsh", None),
        "Uber One": (r"^uber ?\*? ?one", None),
        "Midjourney (billed in USD)": (r"midjourney", None),
        "Xbox Game Pass": (r"microsoft\*(xbox|ultimate)|^msft \* e0400", None),
        "Microsoft 365 Personal": (r"microsoft\*(microsoft 365|store)|^msft \* microsoft 365", None),
        "Revolut Premium plan": (r"^premium plan fee$", None),
        "Strava": (r"strava", None),
    }, ["Flyefit Day Pass", "^Boots$", "Aoife Brennan", "Electric Ireland"]),
    "nl-ing-style.csv": (parse_nl, {
        "Ziggo": (r"^ziggo", None),
        "Odido mobile": (r"^odido", None),
        "Videoland": (r"^RTL Nederland", None),
        "Disney+ (via PayPal)": (r"^PayPal Europe", 8.99),
        "Nintendo Switch Online": (r"nintendo", None),
        "Storytel": (r"^storytel", None),
        "Patreon (billed in USD)": (r"patreon", None),
    }, ["SportCity Dagpas", "Apotheek", "J\\. de Vries", "Eneco"]),
}
GAP = {"weekly": (6, 8), "monthly": (26, 35), "quarterly": (85, 97), "yearly": (350, 380)}


def step_rise(a):
    """True if amounts are a constant a then a constant b > a."""
    for k in range(1, len(a)):
        if len(set(a[:k])) == 1 and len(set(a[k:])) == 1 and a[k] > a[0]:
            return True
    return False


def main():
    gold = json.load(open(os.path.join(HERE, "gold.json"), encoding="utf-8"))
    if set(gold) != set(FILES):
        err("gold", f"file set mismatch {sorted(gold)}")
    for fname, (parser, matchers, nonsub_pats) in FILES.items():
        g = gold[fname]
        text = open(os.path.join(STMT, fname), encoding="utf-8").read()
        rows = parser(text)
        if len(rows) != g["rows"]:
            err(fname, f"rows {len(rows)} != gold {g['rows']}")
        if not 120 <= len(rows) <= 200:
            err(fname, f"rows {len(rows)} outside 120-200")
        if not 6 <= len(g["recurring"]) <= 9:
            err(fname, "recurring count outside 6-9")
        end = max(r["date"] for r in rows)
        months = (end - min(r["date"] for r in rows)).days / 30.4
        if not 9.5 <= months <= 12.5:
            err(fname, f"period {months:.1f} months")
        if set(m["merchant"] for m in g["recurring"]) != set(matchers):
            err(fname, "merchant set mismatch")
        if len(g["duplicates"]) != 1:
            err(fname, "must have exactly one duplicate")
        descs = set(r["desc"] for r in rows)
        claimed = {}
        for rec in g["recurring"]:
            name = rec["merchant"]
            pat, amt = matchers[name]
            hits = sorted([r for r in rows if r["ok"] and r["amount"] < 0 and re.search(pat, r["desc"], I)
                           and (amt is None or abs(-r["amount"] - amt) < 0.005)], key=lambda r: r["date"])
            for h in hits:
                key = id(h)
                if key in claimed:
                    err(fname, f"row claimed by {claimed[key]} and {name}: {h['desc']!r}")
                claimed[key] = name
            dups = [d for d in g["duplicates"] if d["merchant"] == name]
            charges = list(hits)
            for d in dups:
                dd = dt.date.fromisoformat(d["date"])
                m = [h for h in charges if h["date"] == dd and abs(-h["amount"] - d["amount"]) < 0.005 and h["desc"] == d["descriptor"]]
                if len(m) != 1:
                    err(fname, f"duplicate row for {name} on {dd} not found exactly once")
                    continue
                charges.remove(m[0])
                orig = [h for h in charges if 0 <= (dd - h["date"]).days <= 2 and abs(h["amount"] - m[0]["amount"]) < 0.005]
                if len(orig) != 1:
                    err(fname, f"duplicate for {name} on {dd} has no single original 0-2 days earlier")
            amounts = [round(-h["amount"], 2) for h in charges]
            if amounts != rec["amounts"]:
                err(fname, f"{name}: amounts {amounts} != gold {rec['amounts']}")
            if len(charges) != rec["count"] or rec["count"] != len(rec["amounts"]):
                err(fname, f"{name}: count {len(charges)} vs gold {rec['count']}")
            if not charges:
                continue
            if charges[0]["date"].isoformat() != rec["first"] or charges[-1]["date"].isoformat() != rec["last"]:
                err(fname, f"{name}: first/last {charges[0]['date']}/{charges[-1]['date']} vs gold {rec['first']}/{rec['last']}")
            gaps = [(b["date"] - a["date"]).days for a, b in zip(charges, charges[1:])]
            lo, hi = GAP[rec["cadence"]]
            if not gaps or not all(lo <= x <= hi for x in gaps):
                err(fname, f"{name}: gaps {gaps} not {rec['cadence']}")
            active = (end - charges[-1]["date"]).days <= hi * 1.2
            if active != rec["active_at_end"]:
                err(fname, f"{name}: active_at_end {active} vs gold {rec['active_at_end']}")
            if not active and (end - charges[-1]["date"]).days < 2 * hi:
                err(fname, f"{name}: cancellation not clear (stopped only {(end - charges[-1]['date']).days} days before end)")
            trial = len(amounts) > 2 and amounts[0] < 0.6 * statistics.median(amounts[1:]) and len(set(amounts[1:])) == 1
            if trial != rec["trial_converted"]:
                err(fname, f"{name}: trial {trial} vs gold {rec['trial_converted']}")
            rise = step_rise(amounts[1:] if trial else amounts)
            if rise != rec["price_rise"]:
                err(fname, f"{name}: price_rise {rise} vs gold {rec['price_rise']}")
            if len(set(amounts)) > 2:  # FX wobble: must stay within a few percent and be flagged in a note
                med = statistics.median(amounts)
                if (max(amounts) - min(amounts)) / med > 0.12 or "USD" not in rec.get("note", ""):
                    err(fname, f"{name}: wobble too large or not a noted FX subscription")
            # no accidental extra duplicates among real charges
            for a, b in zip(charges, charges[1:]):
                if (b["date"] - a["date"]).days <= 2 and abs(a["amount"] - b["amount"]) < 0.005:
                    err(fname, f"{name}: unexpected same-amount pair {a['date']} {b['date']}")
            for ex in rec["descriptor_examples"]:
                if ex not in descs:
                    err(fname, f"{name}: descriptor example not in file: {ex!r}")
        for p in nonsub_pats:
            n = sum(1 for r in rows if re.search(p, r["desc"], I))
            if n < 3:
                err(fname, f"non-subscription pattern {p!r} appears only {n} times")
        print(f"{fname}: {len(rows)} rows, {len(g['recurring'])} recurring, dup={g['duplicates'][0]['merchant']}")
    # cross-file coverage of hard cases
    allrec = [r for v in gold.values() for r in v["recurring"]]
    need = {
        "weekly": any(r["cadence"] == "weekly" for r in allrec),
        "quarterly": any(r["cadence"] == "quarterly" for r in allrec),
        "yearly": any(r["cadence"] == "yearly" for r in allrec),
        "price_rise": any(r["price_rise"] for r in allrec),
        "trial": any(r["trial_converted"] for r in allrec),
        "cancelled": any(not r["active_at_end"] for r in allrec),
    }
    for k, v in need.items():
        if not v:
            err("set", f"missing hard case {k}")
    if errors:
        print("\n".join("FAIL " + e for e in errors))
        sys.exit(1)
    print("ALL OK")


if __name__ == "__main__":
    main()
