"""From a statement file to the ghosts on the page."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal

from . import ghosts, names, statement


def analyse(data: bytes, use_model: bool = True, died: date | None = None) -> dict:
    txns = statement.read(data)
    read = len(txns)
    examples: dict[str, list[str]] = defaultdict(list)
    for t in txns:
        if t.amount >= 0:
            k = ghosts.key(t.description)
            if k and len(examples[k]) < 3 and t.description not in examples[k]:
                examples[k].append(t.description)
    named, stats = ({}, None)
    if use_model and names.enabled():
        named, stats = names.name_merchants(dict(examples))
    # Rent to a landlord repeats like a subscription but is not one: when the model says a key is a
    # transfer to a person or a cash withdrawal, its payments are set aside before the search.
    aside = {k for k, v in named.items() if v["kind"] in ("transfer", "cash")}
    if aside:
        txns = [t for t in txns if t.amount < 0 or ghosts.key(t.description) not in aside]
    result = ghosts.find(txns, names.merge_map(named))
    result["set_aside"] = sorted({named[k]["merchant"] for k in aside})
    kinds = {v["merchant"]: v["kind"] for v in named.values()}
    for g in result["ghosts"]:
        g["kind"] = kinds.get(g["merchant"])
    result["model"] = {"used": bool(stats), "name": names.model_label() if stats else None,
                       "local": names.runs_locally() if stats else None, "stats": stats}
    result["transactions"] = read
    # For the account of someone who has died: what each ghost has taken since that day.
    if died:
        total = Decimal("0")
        for g in result["ghosts"]:
            after = [Decimal(c["amount"]) for c in g["charges"] if date.fromisoformat(c["day"]) > died]
            g["since_died"] = {"count": len(after), "total": f"{sum(after, Decimal('0')):.2f}"}
            total += sum(after, Decimal("0"))
        result["died"] = died.isoformat()
        result["since_died_total"] = f"{total:.2f}"
        result["since_died_ghosts"] = sum(1 for g in result["ghosts"] if g["since_died"]["count"])
    return result
