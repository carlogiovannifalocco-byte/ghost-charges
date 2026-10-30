"""Independent check: re-parse each CSV in its bank format and verify gold.json."""
import csv, json, re, datetime as dt
from collections import defaultdict

E = "/home/claude/ghost-charges/eval"
gold = json.load(open(f"{E}/gold.json", encoding="utf-8"))


def it_num(s):
    return float(s.replace(".", "").replace(",", ".")) if s else 0.0


def load(name):
    p = f"{E}/statements/{name}"
    rows = []
    if name.startswith("it-"):
        for r in csv.DictReader(open(p, encoding="utf-8"), delimiter=";"):
            rows.append((dt.datetime.strptime(r["Data contabile"], "%d/%m/%Y").date(),
                         it_num(r["Accrediti"]) - it_num(r["Addebiti"]), r["Descrizione"]))
    elif name.startswith("uk-"):
        for r in csv.DictReader(open(p, encoding="utf-8")):
            rows.append((dt.date.fromisoformat(r["Date"]), float(r["Amount"]), f"{r['Name']} | {r['Description']}"))
    elif name.startswith("us-"):
        lines = open(p, encoding="utf-8").read().splitlines()
        hdr = lines[0].split(",")
        for row in csv.reader(lines[1:]):
            assert row[-1] == "" and len(row) == len(hdr) + 1, row  # trailing comma
            r = dict(zip(hdr, row))
            rows.append((dt.datetime.strptime(r["Posting Date"], "%m/%d/%Y").date(), float(r["Amount"]), r["Description"]))
    else:
        for r in csv.DictReader(open(p, encoding="utf-8")):
            rows.append((dt.date.fromisoformat(r["Datum"]), float(r["Betrag (EUR)"]), f"{r['Empfänger']} | {r['Verwendungszweck']}".strip(" |")))
    return rows


PAT = {
    "it-intesa-style.csv": {"Netflix": r"NETFLIX", "Spotify": r"SPOTIFY", "Fastweb": r"FASTWEB", "Iliad": r"ILIAD",
                            "Amazon Prime": r"PRIME", "Telepass": r"TELEPASS", "Disney+": r"DISNEY", "YouTube Premium": r"(?i)youtube"},
    "uk-monzo-style.csv": {"Netflix": r"(?i)netflix", "Apple iCloud+": r"APPLE.COM/BILL\s+CORK", "Apple TV+ (billed via Apple)": r"APPLE.COM/BILL\s+ITUNES",
                           "PureGym": r"PUREGYM", "Oddbox": r"ODDBOX", "Audible": r"(?i)audible", "Cursor (AI code editor, billed in USD)": r"CURSOR",
                           "Harry's razor refills": r"HARRYS", "Deliveroo Plus": r"DELIVEROO PLUS"},
    "us-chase-style.csv": {"Netflix": r"NETFLIX", "Spotify": r"(?i)spotify", "Apple iCloud+": r"APPLE.COM/BILL", "Amazon Prime": r"(?i)amazon prime",
                           "DoorDash DashPass": r"DASHPASS", "HelloFresh": r"HELLOFRESH", "Dollar Shave Club": r"DOLLAR SHAVE"},
    "de-n26-style.csv": {"Netflix (via PayPal)": r"NETFLIX", "Spotify": r"(?i)spotify", "O2 / Telefonica mobile": r"Telefonica",
                         "Rundfunkbeitrag (ARD ZDF Deutschlandradio)": r"Rundfunk", "Urban Sports Club": r"URBAN SPORTS",
                         "Notion (billed via Paddle)": r"NOTION", "Kindle Unlimited": r"AMAZON DIGITAL|Amazon Digital", "Deutschlandticket (BVG)": r"Deutschlandticket"},
}
CAD = {"weekly": (5, 9), "monthly": (26, 35), "quarterly": (85, 97), "yearly": (350, 372)}
ok = True
for name, g in gold.items():
    rows = load(name)
    assert len(rows) == g["rows"], (name, len(rows), g["rows"])
    claimed = defaultdict(int)
    for rec in g["recurring"]:
        pat = re.compile(PAT[name][rec["merchant"]])
        hits = sorted([r for r in rows if pat.search(r[2])], key=lambda r: r[0])
        dups = [d for d in g["duplicates"] if d["merchant"] == rec["merchant"]]
        for i, r in enumerate(rows):
            if pat.search(r[2]): claimed[i] += 1
        # remove duplicate rows (one per gold duplicate) then compare
        rest = list(hits)
        for d in dups:
            same = [h for h in rest if h[0].isoformat() == d["date"] and abs(h[1] + d["amount"]) < 0.005]
            assert len(same) >= 2 or (len(same) == 1 and any(abs(h[0] - same[0][0]).days <= 1 and h is not same[0] and abs(h[1] - same[0][1]) < .005 for h in rest)), (name, d)
            rest.remove(same[-1])
        amts = [round(-h[1], 2) for h in rest]
        errs = []
        if amts != rec["amounts"]: errs.append(f"amounts {amts} != {rec['amounts']}")
        if len(rest) != rec["count"]: errs.append("count")
        if rest[0][0].isoformat() != rec["first"] or rest[-1][0].isoformat() != rec["last"]: errs.append("first/last")
        gaps = [(b[0] - a[0]).days for a, b in zip(rest, rest[1:])]
        lo, hi = CAD[rec["cadence"]]
        bad = [x for x in gaps if not lo <= x <= hi]
        if rec["merchant"] == "HelloFresh": bad = [x for x in bad if x != 14]  # one paused week
        if bad: errs.append(f"gaps {bad}")
        end = max(r[0] for r in rows)
        active = (end - rest[-1][0]).days <= hi + 3
        if active != rec["active_at_end"]: errs.append("active flag")
        rise = any(b > a for a, b in zip(amts[1:], amts[2:])) or (not rec["trial_converted"] and any(b > a for a, b in zip(amts, amts[1:])))
        if "USD" in rec["merchant"]: rise = False  # FX-driven variation is not a price rise
        if rise != rec["price_rise"]: errs.append("rise flag")
        if rec["trial_converted"] != (amts[0] < amts[1] and amts[0] <= 1.99): errs.append("trial flag")
        print(f"{name:22} {rec['merchant'][:34]:34} {rec['cadence']:9} n={len(rest):2} dups={len(dups)} {'OK' if not errs else errs}")
        ok &= not errs
    multi = [k for k, v in claimed.items() if v > 1]
    if multi: print("rows matched by >1 merchant:", multi); ok = False
print("ALL OK" if ok else "FAILURES")
