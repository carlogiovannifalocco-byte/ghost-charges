"""Finds the charges that keep coming back: subscriptions, memberships, plans you forgot about.

All of it is plain code, so every claim on the page can be checked against the statement:

- a **ghost** is a payment to the same merchant at a steady rhythm (weekly, monthly, every three months,
  yearly) for a steady amount, where the amount may step up (a price rise) but does not wander like a
  grocery bill;
- a ghost is **still haunting** if its next charge is due after the statement ends;
- a **price rise** is a later block of charges at a higher amount than an earlier one;
- a **trial that turned paid** is a first charge of at most 1.00 followed by the full price;
- a **double charge** is the same merchant and the same amount twice within two days, outside a weekly rhythm.

The model only helps to read merchant names (see `names.py`); it never decides what is recurring."""

from __future__ import annotations

import re
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from .statement import Txn

CADENCES = {  # name: (typical days, accepted range of gaps, charges per year)
    "weekly": (7, (5, 9), 52),
    "monthly": (30, (25, 36), 12),
    "quarterly": (91, (80, 100), 4),
    "yearly": (365, (350, 380), 1),
}

# Payment processors and bank wording that hide the merchant's name.
_PREFIXES = [
    r"PAGAMENTO\s+TRAMITE\s+PAYPAL", r"PAGAMENTO\s+POS", r"PAGAMENTO\s+CARTA", r"PAGAMENTO\s+DIGITALE",
    r"PAGAMENTO\s+ONLINE", r"PAGAMENTO", r"ADDEBITO\s+SDD(\s+CORE)?", r"ADDEBITO\s+DIRETTO", r"ADDEBITO",
    r"ACQUISTO\s+(POS|ONLINE|CARTA)", r"OPERAZIONE\s+CARTA", r"CARTA\s+N\.?", r"PRESSO", r"PAYPAL\s*\*?",
    r"PAYPAL\s+EUROPE", r"SEPA[- ]LASTSCHRIFT", r"LASTSCHRIFT", r"KARTENZAHLUNG", r"DIRECT\s+DEBIT",
    r"CARD\s+PAYMENT(\s+TO)?", r"POS\s+PURCHASE", r"DEBIT\s+CARD\s+PURCHASE", r"RECURRING\s+PAYMENT",
    r"SQ\s*\*", r"SP\s*\*", r"TST\s*\*", r"DD\s*\*", r"PADDLE\.NET\s*\*", r"FS\s*\*", r"2CO\.COM\s*\*",
    r"GOOGLE\s*\*",
    r"PAYPAL\s*\(?EUROPE\)?\s*S\.?\s*[AÀ]\.?\s*R\.?\s*L\.?\s*ET\s+CIE,?\s*S\.?\s*C\.?\s*A\.?",
]
# Processors written as "NAME*": they hide the merchant wherever they appear, not only at the start.
_PROCESSOR = re.compile(r"\b(?:" + "|".join(p for p in _PREFIXES if p.endswith("*")) + ")", re.I)
_PREFIX = re.compile(r"^(?:\s*(?:" + "|".join(p if p.endswith("*") or p.endswith("*?") else p + r"\b" for p in _PREFIXES)
                     + r")[\s*:·-]*)+", re.I)
# Billers that hide the merchant entirely: name the biller, since that is all the statement says.
_BILLERS = [(re.compile(r"AMZN\s*MKTP|AMAZON\.\w+\*|AMZN\.COM/BILL|AMZN?\b", re.I), " AMAZON "),
            (re.compile(r"APPLE\.COM/BILL|ITUNES\.COM/BILL|APPLE\.COM", re.I), " APPLE "),
            (re.compile(r"MICROSOFT\*|MSFT\s*\*", re.I), " MICROSOFT ")]
_NOISE = [
    re.compile(r"\b(DEL|DATA|ORE|DATE|AM|ON)\s+\d[\d/.:-]*", re.I),
    re.compile(r"\b\d{1,2}[/.-]\d{1,2}([/.-]\d{2,4})?\b"),
    re.compile(r"\b\d{1,2}:\d{2}(:\d{2})?\b"),
    re.compile(r"\b[X*]{2,}\d*\b|\*{2,}\d+", re.I),
    re.compile(r"\+?\d[\d\s-]{6,}\d"),
    re.compile(r"\b(MANDATO|MANDATE|RIF|REF|CID|ID|CRO|TRN|NR|N)\b[.:]?\s*[\w-]*\d[\w-]*", re.I),
    re.compile(r"\b\w*\d{3,}\w*\b"),
    re.compile(r"\b(?=\w*\d)(?=\w*[A-Z])\w{4,}\b", re.I),  # order codes such as 2K3LP1H90
    re.compile(r"\b\d+[.,]\d{2}\b(?![.,/]\d)"),  # the amount repeated in the text: "PAGAMENTO POS 15,99 EUR"
    re.compile(r"\bWWW\.|\.(COM|NET|IT|CO\.UK|DE|IO|AI|APP|TV|FM)\b", re.I),
]
_STOP = {"THE", "AND", "LTD", "LIMITED", "INC", "LLC", "SRL", "SPA", "S.P.A", "GMBH", "BV", "AB", "SA", "SARL", "EU",
         "EUROPE", "SARL", "CO", "COM", "IT", "UK", "US", "USA", "DE", "IE", "NL", "LU", "BILL", "PAYMENT", "ITALIA",
         "INTERNATIONAL", "SERVICES", "CARTA", "CARD", "VISA", "MASTERCARD", "MKTP", "MARKETPLACE", "DIGITAL", "ONLINE", "STORE", "SUBSCRIPTION", "ABBONAMENTO", "MEMBERSHIP",
         "EUR", "USD", "GBP", "CHF", "PP", "ET", "CIE", "SCA"}
_PLACES = {"AMSTERDAM", "DUBLIN", "LONDON", "LUXEMBOURG", "MILANO", "MILAN", "ROMA", "ROME", "BERLIN", "MUNCHEN",
           "MUNICH", "PARIS", "STOCKHOLM", "CA", "NY", "WA", "TX", "FL", "IL", "MA", "SAN", "FRANCISCO", "SEATTLE",
           "CUPERTINO", "LOS", "GATOS", "MOUNTAIN", "VIEW", "NEW", "YORK", "HAMBURG", "MADRID", "BARCELONA", "TORINO",
           "NAPOLI", "FIRENZE", "BOLOGNA", "ITA", "GBR", "DEU", "IRL", "NLD", "LUX"}


def clean(description: str) -> str:
    """The part of a bank's description that names the merchant, as far as code can tell.
    "PAGAMENTO POS NETFLIX.COM 866-579-7172 AMSTERDAM CARTA N. ****1234 DEL 03/10/2026" → "NETFLIX"."""
    best = ""
    for part in description.split(" · "):
        s = part.upper().replace("’", "'")
        for rx, name in _BILLERS:
            s = rx.sub(name, s)
        s = _PROCESSOR.sub(" ", _PREFIX.sub("", s.strip()))
        for rx in _NOISE:
            s = rx.sub(" ", s)
        s = _PREFIX.sub("", s.strip(" *·-:"))
        words = [w for w in re.findall(r"[A-ZÀ-Ü][A-ZÀ-Ü'&+]*", s) if w not in _STOP and w not in _PLACES and len(w) > 1]
        candidate = " ".join(words[:3])
        if len(candidate) > len(best) or (candidate and not best):
            best = candidate if not best else best
    return best


def key(description: str) -> str:
    """Charges with the same key are treated as the same merchant: the first word of the cleaned name, or
    the first two when the first is a generic word."""
    words = clean(description).split()
    if not words:
        return ""
    if len(words) > 1 and (len(words[0]) <= 3 or words[0] in {"MY", "THE", "AMAZON", "APPLE", "GOOGLE", "MICROSOFT"}):
        return " ".join(words[:2])
    return words[0]


def merge_by_prefix(keys: set[str]) -> dict[str, str]:
    """Code's own guess at which keys are one merchant: "SPOTIFYAB" and "SPOTIFY", "NOTIONLABS" and
    "NOTION". A shorter key of five letters or more that starts a longer one absorbs it, unless it is a
    biller that sells many things ("AMAZON" must not swallow "AMAZON PRIME")."""
    out: dict[str, str] = {}
    for k in sorted(keys, key=len):
        flat = k.replace(" ", "")
        target = next((r for r in sorted(set(out.values()), key=len)
                       if r not in _BILLER_NAMES and len(r.replace(" ", "")) >= 5 and flat.startswith(r.replace(" ", ""))), k)
        out[k] = target
    return out


_BILLER_NAMES = {"AMAZON", "APPLE", "GOOGLE", "MICROSOFT", "PAYPAL"}


@dataclass
class Ghost:
    merchant: str
    key: str
    cadence: str
    charges: list[Txn]
    amount: Decimal                      # the latest regular amount
    active: bool
    next_due: date | None
    price_changes: list[tuple[date, Decimal, Decimal]] = field(default_factory=list)
    trial: Txn | None = None
    per_year: Decimal = Decimal("0")
    paid_in_period: Decimal = Decimal("0")

    def as_dict(self) -> dict:
        return {
            "merchant": self.merchant, "key": self.key, "cadence": self.cadence, "amount": str(self.amount),
            "active": self.active, "next_due": self.next_due.isoformat() if self.next_due else None,
            "per_year": str(self.per_year), "paid_in_period": str(self.paid_in_period),
            "first": self.charges[0].day.isoformat(), "last": self.charges[-1].day.isoformat(),
            "count": len(self.charges),
            "price_changes": [{"day": d.isoformat(), "from": str(a), "to": str(b)} for d, a, b in self.price_changes],
            "trial": {"day": self.trial.day.isoformat(), "amount": str(self.trial.amount)} if self.trial else None,
            "charges": [{"day": t.day.isoformat(), "amount": str(t.amount), "description": t.description, "row": t.row}
                        for t in self.charges],
        }


def _cadence(days: list[date]) -> str | None:
    if len(days) < 2:
        return None
    gaps = [(b - a).days for a, b in zip(days, days[1:])]
    med = statistics.median(gaps)
    for name, (_, (lo, hi), _) in CADENCES.items():
        if lo <= med <= hi:
            inside = sum(1 for g in gaps if lo <= g <= hi or (name != "weekly" and lo * 2 - 3 <= g <= hi * 2 + 3))
            if inside >= max(1, round(0.75 * len(gaps))):
                return name
    return None


def _blocks(amounts: list[Decimal]) -> list[tuple[int, Decimal]]:
    """Runs of about the same amount, as (index of the first charge, typical amount). A charge joins the
    current run when it is within 6% of the run's median: a foreign-currency charge converted at a
    different rate each month wobbles, a price rise steps."""
    blocks: list[tuple[int, list[Decimal]]] = []
    for i, a in enumerate(amounts):
        if blocks:
            mid = statistics.median(blocks[-1][1])
            if abs(a - mid) <= mid * Decimal("0.06"):
                blocks[-1][1].append(a)
                continue
        blocks.append((i, [a]))
    return [(i, statistics.median(run)) for i, run in blocks]


def _steady(amounts: list[Decimal]) -> bool:
    """A subscription's amount is flat, or steps up (or down) a few times and stays there. A grocery bill
    wanders."""
    return len(_blocks(amounts)) <= max(2, len(amounts) // 4 + 1)


def _series(txns: list[Txn], end: date) -> Ghost | None:
    txns = sorted(txns, key=lambda t: t.day)
    trial = None
    if len(txns) >= 3 and txns[0].amount <= Decimal("2.00") and txns[0].amount * 2 <= txns[1].amount:
        trial, txns = txns[0], txns[1:]
    amounts = [t.amount for t in txns]
    cadence = _cadence([t.day for t in txns])
    if cadence is None or not _steady(amounts):
        return None
    if len(txns) < (2 if cadence == "yearly" else 3):
        return None
    if trial is not None and (txns[0].day - trial.day).days > CADENCES[cadence][1][1] + 5:
        txns, trial = [trial] + txns, None
    blocks = _blocks(amounts)
    changes = [(txns[j].day, txns[j - 1].amount, txns[j].amount) for _, (j, _) in zip(blocks, blocks[1:])]
    typical, (_, hi), per_year = CADENCES[cadence]
    next_due = txns[-1].day + timedelta(days=typical)
    active = txns[-1].day + timedelta(days=hi + 3) >= end
    amount = txns[-1].amount
    return Ghost(merchant="", key="", cadence=cadence, charges=txns, amount=amount, active=active,
                 next_due=next_due if active else None, price_changes=changes, trial=trial,
                 per_year=(amount * per_year).quantize(Decimal("0.01")),
                 paid_in_period=sum((t.amount for t in txns), Decimal("0")) + (trial.amount if trial else 0))


def find(txns: list[Txn], names: dict[str, str] | None = None) -> dict:
    """Every ghost in the statement, the double charges, and the totals. `names` maps a key to a verified
    merchant name; keys that map to the same name are one merchant (see names.py)."""
    names = names or {}
    debits = [t for t in txns if t.amount >= 0]
    if not debits:
        return {"ghosts": [], "duplicates": [], "start": None, "end": None}
    start, end = txns[0].day, txns[-1].day
    groups: dict[str, list[Txn]] = defaultdict(list)
    keys = {key(t.description) for t in debits} - {""}
    merged = merge_by_prefix(keys)
    for t in debits:
        k = key(t.description)
        if k:
            groups[names.get(k) or merged[k]].append(t)

    ghosts: list[Ghost] = []
    duplicates: list[dict] = []
    for merchant, items in groups.items():
        items.sort(key=lambda t: t.day)
        # A double charge is listed apart and kept out of the rhythm, so it does not hide a monthly series.
        doubles = [b for a, b in zip(items, items[1:]) if a.amount == b.amount and a.amount > 0 and (b.day - a.day).days <= 2]
        regular = [t for t in items if t not in doubles]
        found = _series(regular, end)
        series = [found] if found else []
        if not found:
            # One merchant can bill two plans (Apple, Google, Amazon): try each amount on its own.
            by_amount: dict[Decimal, list[Txn]] = defaultdict(list)
            for t in regular:
                by_amount[t.amount].append(t)
            series = [g for g in (_series(v, end) for v in by_amount.values() if len(v) >= 2) if g]
        for g in series:
            g.merchant = merchant if merchant in names.values() else merchant.title()
            g.key = merchant
            ghosts.append(g)
        if not any(g.cadence == "weekly" for g in series):
            for b in doubles:
                a = items[items.index(b) - 1]
                duplicates.append({"merchant": series[0].merchant if series else merchant.title(),
                                   "day": b.day.isoformat(), "amount": str(b.amount), "rows": [a.row, b.row],
                                   "descriptions": [a.description, b.description]})
    ghosts.sort(key=lambda g: (not g.active, -g.per_year))
    haunting = [g for g in ghosts if g.active]
    return {
        "start": start.isoformat(), "end": end.isoformat(),
        "ghosts": [g.as_dict() for g in ghosts],
        "duplicates": duplicates,
        "per_year": str(sum((g.per_year for g in haunting), Decimal("0"))),
        "per_month": str((sum((g.per_year for g in haunting), Decimal("0")) / 12).quantize(Decimal("0.01"))),
        "haunting": len(haunting),
        "price_rises": sum(1 for g in ghosts for _, a, b in g.price_changes if b > a),
        "trials": sum(1 for g in ghosts if g.trial),
        "keys": sorted({key(t.description) for t in debits if key(t.description)}),
    }
