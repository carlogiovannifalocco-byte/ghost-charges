"""Reads the merchant's name out of a bank's description, with an open-weight model, and checks it.

"PAYPAL *SPOTIFYAB 35314369", "SEPA-Lastschrift Spotify AB P1A2B3" and "SPOTIFY P0E8F3C1A" are the same
monthly charge. Code alone can strip the noise, but it cannot know that "DD *DOORDASH DASHPASS" is a
subscription and "SQ *BLUE BOTTLE" a coffee. Gemma reads the descriptions and names the merchant.

The model's answer is only used if the name can be found in the descriptions themselves: every name must
share a word with what the bank wrote, or be an expansion of an abbreviation the bank wrote ("AMZN" →
"Amazon"). A name the model makes up is dropped and the code's own name is kept."""

from __future__ import annotations

import json
import os
import re
import time

import httpx

KINDS = ("subscription", "utility", "insurance", "shopping", "food", "transport", "transfer", "cash", "other")

PROMPT = """These are merchant descriptions from a bank statement, grouped by a key. For each key, name the
merchant the way a person would say it (for example "Spotify", "YouTube Premium", "DoorDash DashPass",
"Enel Energia"), and say what kind of payment it usually is: {kinds}. A payment to a private person
(rent to a landlord, money to a friend) or a paper check is "transfer".
Use only what the descriptions say. If you cannot tell who the merchant is, use null for the name.
Reply with JSON only: {{"KEY": {{"merchant": "...", "kind": "..."}}, ...}}

{items}"""


def config() -> dict:
    return {
        "base_url": os.getenv("LLM_BASE_URL", "http://localhost:11434/v1").rstrip("/"),
        "model": os.getenv("LLM_MODEL", "gemma3:4b"),
        "api_key": os.getenv("LLM_API_KEY", "ollama"),
        # On a laptop with no GPU one batch takes minutes, and the first call also loads the model.
        "timeout": float(os.getenv("LLM_TIMEOUT", "600")),
        "min_interval": float(os.getenv("LLM_MIN_INTERVAL", "0")),
        "batch": int(os.getenv("LLM_BATCH", "10")),
        "retry_wait": float(os.getenv("LLM_RETRY_WAIT", "20")),
    }


def enabled() -> bool:
    return os.getenv("GHOST_NO_MODEL", "") not in ("1", "true", "yes")


def runs_locally() -> bool:
    host = httpx.URL(config()["base_url"]).host or ""
    return host in ("localhost", "127.0.0.1", "0.0.0.0", "::1") or host.endswith(".local")


def model_label() -> str:
    return config()["model"]


_last = [0.0]


def _chat(prompt: str) -> str:
    cfg = config()
    wait = _last[0] + cfg["min_interval"] - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    _last[0] = time.monotonic()
    body = {"model": cfg["model"], "temperature": 0, "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"}}
    headers = {"Authorization": f"Bearer {cfg['api_key']}"}
    r = httpx.post(f"{cfg['base_url']}/chat/completions", headers=headers, json=body, timeout=cfg["timeout"])
    if r.status_code == 400:  # some endpoints refuse JSON mode: ask again without it
        del body["response_format"]
        r = httpx.post(f"{cfg['base_url']}/chat/completions", headers=headers, json=body, timeout=cfg["timeout"])
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"] or ""


def parse_json(text: str) -> dict:
    """The JSON object in a model's reply, past any thinking block, code fence or sentence around it.
    An answer given as a list ([{"key": ..., "merchant": ...}]) is turned into the same {key: ...} shape."""
    text = re.sub(r"<(think|thought|thinking)>.*?</\1>", "", text, flags=re.S | re.I)
    decoder, best, i = json.JSONDecoder(), None, 0
    while True:
        starts = [p for p in (text.find("{", i), text.find("[", i)) if p >= 0]
        if not starts:
            break
        i = min(starts)
        try:
            value, end = decoder.raw_decode(text, i)
        except json.JSONDecodeError:
            i += 1
            continue
        if value and isinstance(value, (dict, list)):
            best = value  # the last one wins: earlier ones are drafts
        i = end
    if isinstance(best, list):
        return {str(x.get("key")): x for x in best if isinstance(x, dict) and x.get("key")}
    if isinstance(best, dict) and len(best) == 1 and isinstance(next(iter(best.values())), (dict, list)):
        only = next(iter(best.values()))  # {"merchants": {...}} or {"results": [...]}
        if isinstance(only, list):
            return {str(x.get("key")): x for x in only if isinstance(x, dict) and x.get("key")}
        if only and all(isinstance(v, dict) for v in only.values()):
            return only
    return best if isinstance(best, dict) else {}


def _letters(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.casefold())


def _subsequence(short: str, long: str) -> bool:
    it = iter(long)
    return all(c in it for c in short)


def supported(name: str, descriptions: list[str]) -> bool:
    """True if the bank's own text backs the name: one of the name's words (3+ letters) appears in a
    description, or a word the bank wrote is an abbreviation of the name ("AMZN" in "Amazon")."""
    text = _letters(" ".join(descriptions))
    words = [_letters(w) for w in re.findall(r"[\w'&+]+", name)]
    if any(len(w) >= 3 and w in text for w in words):
        return True
    full = _letters(name)
    for raw in re.findall(r"[A-Za-z]{3,}", " ".join(descriptions)):
        w = raw.casefold()
        if len(w) >= 3 and w[0] == full[:1] and _subsequence(w, full):
            return True
    return False


def name_merchants(groups: dict[str, list[str]]) -> tuple[dict[str, dict], dict]:
    """{key: {"merchant": name, "kind": kind}} for the keys the model named in a way the descriptions
    support, and stats on what was kept and dropped."""
    cfg = config()
    keys = sorted(groups)
    named: dict[str, dict] = {}
    stats = {"asked": len(keys), "named": 0, "dropped_unsupported": 0, "no_answer": 0, "errors": 0}
    for i in range(0, len(keys), cfg["batch"]):
        chunk = keys[i:i + cfg["batch"]]
        items = "\n".join(f"{k}: " + " | ".join(groups[k][:3]) for k in chunk)
        answer = None
        for attempt in range(2):  # free hosted tiers refuse a burst: wait once and try the batch again
            try:
                answer = parse_json(_chat(PROMPT.format(kinds=", ".join(KINDS), items=items)))
                break
            except (httpx.HTTPError, KeyError, ValueError):
                if attempt == 0 and not runs_locally():
                    time.sleep(cfg["retry_wait"])
        if answer is None:
            stats["errors"] += len(chunk)
            continue
        folded = {_letters(str(a)): v for a, v in answer.items()}  # keys come back in another case or spacing
        for k in chunk:
            got = answer.get(k) or folded.get(_letters(k))
            if not isinstance(got, dict) or not isinstance(got.get("merchant"), str) or not got["merchant"].strip():
                stats["no_answer"] += 1
                continue
            name = re.sub(r"\s+", " ", got["merchant"]).strip()[:60]
            if not supported(name, groups[k]):
                stats["dropped_unsupported"] += 1
                continue
            kind = got.get("kind") if got.get("kind") in KINDS else "other"
            named[k] = {"merchant": name, "kind": kind}
            stats["named"] += 1
    return named, stats


def merge_map(named: dict[str, dict]) -> dict[str, str]:
    """Keys the model gave the same name are one merchant: {key: "Spotify", ...}."""
    canonical: dict[str, str] = {}
    out = {}
    for k, v in named.items():
        n = v["merchant"]
        canonical.setdefault(n.casefold(), n)
        out[k] = canonical[n.casefold()]
    return out
