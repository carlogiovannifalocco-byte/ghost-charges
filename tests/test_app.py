import json
from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient

from app import letters, main, names, service

DEMO = main.DEMO.read_bytes()


def fake_model(monkeypatch, answer):
    monkeypatch.delenv("GHOST_NO_MODEL", raising=False)
    monkeypatch.setattr(names, "_chat", lambda prompt: answer(prompt) if callable(answer) else answer)


def test_demo_rules_only(monkeypatch):
    monkeypatch.setenv("GHOST_NO_MODEL", "1")
    r = service.analyse(DEMO, died=date(2026, 5, 12))
    assert r["model"]["used"] is False
    assert len(r["ghosts"]) == 9
    assert r["since_died_total"] == "857.97"
    assert [d["merchant"] for d in r["duplicates"]] == ["Netflix"]
    netflix = next(g for g in r["ghosts"] if g["merchant"] == "Netflix")
    assert netflix["price_changes"] == [{"day": "2026-03-03", "from": "13.49", "to": "15.49"}]


def test_model_names_are_checked_against_the_statement(monkeypatch):
    def answer(prompt):
        keys = [line.split(": ", 1)[0] for line in prompt.split("\n\n")[-1].splitlines()]
        out = {k: {"merchant": k.title(), "kind": "subscription"} for k in keys}
        if "NETFLIX" in out:
            out["NETFLIX"] = {"merchant": "Disney+", "kind": "subscription"}  # made up: not in the descriptions
        if "AUDIBLE" in out:
            out["AUDIBLE"] = {"merchant": "Audible", "kind": "transfer"}
        return json.dumps(out)
    fake_model(monkeypatch, answer)
    r = service.analyse(DEMO)
    merchants = {g["merchant"] for g in r["ghosts"]}
    assert "Disney+" not in merchants and "Netflix" in merchants
    assert r["model"]["stats"]["dropped_unsupported"] >= 1
    assert r["set_aside"] == ["Audible"] and "Audible" not in merchants


def test_model_failure_falls_back_to_rules(monkeypatch):
    def boom(prompt):
        raise ValueError("no json")
    fake_model(monkeypatch, boom)
    r = service.analyse(DEMO)
    assert len(r["ghosts"]) == 9 and r["model"]["stats"]["errors"] > 0


def test_letter_rejects_facts_from_the_model(monkeypatch):
    fake_model(monkeypatch, "Please close the account. We were charged €15.49 on 3 June.")
    out = letters.write("Netflix", "Walter Brenner", date(2026, 5, 12),
                        [(date(2026, 4, 3), Decimal("15.49")), (date(2026, 6, 3), Decimal("15.49"))], "Anna", "daughter", "en")
    assert out["written_by"] == "template"
    assert out["charges_since"] == 1 and out["total_since"] == "15.49"
    assert "2026-06-03  €15.49" in out["text"] and "2026-04-03" not in out["text"]


def test_letter_keeps_a_clean_model_body(monkeypatch):
    body = "I am writing on behalf of my late father's family. Please close his subscription and refund what was taken after he died."
    fake_model(monkeypatch, body)
    out = letters.write("Netflix", "Walter Brenner", date(2026, 5, 12), [], "Anna", "daughter", "it")
    assert out["written_by"] == names.model_label() and body in out["text"]
    assert out["text"].startswith("Gentile servizio clienti di Netflix,")


def test_web(monkeypatch):
    monkeypatch.setenv("GHOST_NO_MODEL", "1")
    c = TestClient(main.app)
    assert c.get("/").status_code == 200
    assert c.get("/api/config").json()["model"] is None
    r = c.post("/api/demo?died=2026-05-12").json()
    assert r["since_died_ghosts"] == 9
    bad = c.post("/api/analyse", files={"file": ("x.csv", b"hello,world\n1,2\n")})
    assert bad.status_code == 422
    big = c.post("/api/analyse", files={"file": ("x.csv", b"a" * (main.MAX_BYTES + 1))})
    assert big.status_code == 413
    letter = c.post("/api/letter", json={"merchant": "Netflix", "holder": "W", "died": "2026-05-12", "language": "de",
                                          "charges": [{"day": "2026-06-03", "amount": "15.49"}]}).json()
    assert "Sehr geehrtes Netflix-Team," in letter["text"] and letter["total_since"] == "15.49"


def test_currency_comes_from_the_file():
    assert service.currency("Date,Amount,Currency\n2026-01-01,-5.00,GBP\n".encode()) == "GBP"
    # A few dollar charges on a euro account do not make it a dollar account: the header decides.
    header = "Date;Libellé;Débit euros;Crédit euros\n"
    rows = "".join(f"0{i}/01/2026;OPENAI 20 USD;18,50;\n" for i in range(1, 9))
    assert service.currency((header + rows).encode()) == "EUR"
