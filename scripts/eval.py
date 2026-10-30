"""Scores Ghost Charges against the hand-checked answers in eval/gold.json.

    python3 scripts/eval.py            # rules only (no model)
    python3 scripts/eval.py --model    # with the model in LLM_BASE_URL / LLM_MODEL (default: Gemma in Ollama)

A found ghost matches a real subscription when it has the same cadence and at least two of its charges
fall inside the subscription's dates at one of its amounts. Then, for each subscription:
  found     one ghost matches it
  split     more than one ghost matches it (the same subscription shown twice)
  named     the ghost's name shares a word with the real merchant's name
  status    still charging or stopped, price rise and trial are all right
A ghost that matches nothing real is a false alarm. Doubles are scored separately."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import service  # noqa: E402

EVAL = ROOT / "eval"
_SKIP = {"via", "billed", "the", "and", "inc", "plus", "subs", "mobile", "code", "editor", "refills", "razor"}


def words(name: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", name.lower()) if len(w) >= 3 and w not in _SKIP} or \
        {w for w in re.findall(r"[a-z0-9]+", name.lower())}


def same_name(a: str, b: str) -> bool:
    """"Rundfunk" names "Rundfunkbeitrag"; "Apple" names "Apple iCloud+" (if loosely)."""
    return any(x == y or (min(len(x), len(y)) >= 5 and (x.startswith(y) or y.startswith(x))) for x in words(a) for y in words(b))


def score(gold: dict, ghost: dict) -> int:
    if ghost["cadence"] != gold["cadence"]:
        return 0
    lo, hi = date.fromisoformat(gold["first"]) - timedelta(days=3), date.fromisoformat(gold["last"]) + timedelta(days=3)
    amounts = gold["amounts"]
    return sum(1 for c in ghost["charges"] if lo <= date.fromisoformat(c["day"]) <= hi
               and any(abs(float(c["amount"]) - a) <= 0.05 * a + 0.01 for a in amounts))


def check(file: str, gold: dict, use_model: bool) -> dict:
    t0 = time.time()
    result = service.analyse((EVAL / "statements" / file).read_bytes(), use_model=use_model)
    seconds = time.time() - t0
    owner: dict[int, list[int]] = {}  # gold index -> ghost indexes
    false_alarms = []
    for gi, g in enumerate(result["ghosts"]):
        scores = [score(r, g) for r in gold["recurring"]]
        # Two subscriptions can share a cadence and a price (Disney+ and Iliad, both 9.99 a month): the name
        # only breaks the tie, it never makes a match on its own.
        best = max(range(len(scores)), key=lambda i: (scores[i], same_name(g["merchant"], gold["recurring"][i]["merchant"]))) if scores else None
        if best is None or scores[best] < 2:
            false_alarms.append(f'{g["merchant"]} ({g["cadence"]}, {g["amount"]})')
        else:
            owner.setdefault(best, []).append(gi)
    rows = []
    for ri, r in enumerate(gold["recurring"]):
        mine = [result["ghosts"][i] for i in owner.get(ri, [])]
        g = max(mine, key=lambda x: x["count"]) if mine else None
        rows.append({
            "merchant": r["merchant"], "found": bool(g), "split": len(mine) > 1,
            "as": g["merchant"] if g else None,
            "named": bool(g) and same_name(g["merchant"], r["merchant"]),
            "active": bool(g) and g["active"] == r["active_at_end"],
            "rise": bool(g) and bool([p for p in g["price_changes"] if float(p["to"]) > float(p["from"])]) == r["price_rise"],
            "trial": bool(g) and bool(g["trial"]) == r["trial_converted"],
        })
    dupes_found = sum(1 for d in gold["duplicates"] if any(
        x["day"] == d["date"] and abs(float(x["amount"]) - d["amount"]) < 0.01 for x in result["duplicates"]))
    return {"file": file, "rows": rows, "false_alarms": false_alarms, "duplicates": len(gold["duplicates"]),
            "duplicates_found": dupes_found, "duplicates_reported": len(result["duplicates"]),
            "model": result["model"], "seconds": round(seconds, 1)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", action="store_true", help="use the configured model to name merchants")
    ap.add_argument("--json", type=Path, help="also write the full results here")
    args = ap.parse_args()
    if not args.model:
        import os
        os.environ["GHOST_NO_MODEL"] = "1"
    gold = json.loads((EVAL / "gold.json").read_text())
    out = [check(f, g, args.model) for f, g in gold.items()]
    total = {k: 0 for k in ("subs", "found", "split", "named", "active", "rise", "trial", "false", "dup", "dup_found", "dup_reported")}
    for o in out:
        print(f'\n{o["file"]}  ({o["seconds"]}s)')
        for r in o["rows"]:
            marks = " ".join(k for k in ("split",) if r[k]) + " ".join(f"wrong-{k}" for k in ("named", "active", "rise", "trial") if r["found"] and not r[k])
            print(f'  {"✓" if r["found"] else "✗"} {r["merchant"]:<42} {("as " + r["as"]) if r["as"] else "missed":<28} {marks}')
        for f in o["false_alarms"]:
            print(f"  ! false alarm: {f}")
        print(f'  doubles: {o["duplicates_found"]}/{o["duplicates"]} found, {o["duplicates_reported"]} reported')
        rs = o["rows"]
        total["subs"] += len(rs)
        for k in ("found", "split", "named", "active", "rise", "trial"):
            total[k] += sum(1 for r in rs if r[k])
        total["false"] += len(o["false_alarms"])
        total["dup"] += o["duplicates"]; total["dup_found"] += o["duplicates_found"]; total["dup_reported"] += o["duplicates_reported"]
    t = total
    label = out[0]["model"]["name"] if args.model and out[0]["model"]["used"] else "rules only"
    print(f"\n== {label} ==")
    print(f'subscriptions found   {t["found"]}/{t["subs"]}')
    print(f'shown twice (split)   {t["split"]}')
    print(f'named right           {t["named"]}/{t["found"]}')
    print(f'active/stopped right  {t["active"]}/{t["found"]}')
    print(f'price rise right      {t["rise"]}/{t["found"]}')
    print(f'trial right           {t["trial"]}/{t["found"]}')
    print(f'false alarms          {t["false"]}')
    print(f'doubles found         {t["dup_found"]}/{t["dup"]} ({t["dup_reported"]} reported)')
    if args.json:
        args.json.write_text(json.dumps({"label": label, "total": t, "files": out}, indent=2))


if __name__ == "__main__":
    main()
