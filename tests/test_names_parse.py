from app import names


def test_answer_past_a_thinking_block_and_a_fence():
    text = '<thought>the key {FITNESS} looks like a gym</thought>\nHere you go:\n```json\n{"FITNESS": {"merchant": "Fitness Point", "kind": "subscription"}}\n```'
    assert names.parse_json(text)["FITNESS"]["merchant"] == "Fitness Point"


def test_answer_as_a_list_or_wrapped():
    assert names.parse_json('[{"key": "A", "merchant": "Acme"}]')["A"]["merchant"] == "Acme"
    assert names.parse_json('{"merchants": {"A": {"merchant": "Acme"}}}')["A"]["merchant"] == "Acme"
    assert names.parse_json('{"results": [{"key": "A", "merchant": "Acme"}]}')["A"]["merchant"] == "Acme"


def test_the_last_object_wins_over_a_draft():
    assert names.parse_json('{"A": {"merchant": "x"}} no, better: {"A": {"merchant": "Acme"}}')["A"]["merchant"] == "Acme"


def test_keys_match_whatever_their_case(monkeypatch):
    monkeypatch.setattr(names, "_chat", lambda prompt: '{"netflix com": {"merchant": "Netflix", "kind": "subscription"}}')
    named, stats = names.name_merchants({"NETFLIX COM": ["PAGAMENTO POS NETFLIX.COM"]})
    assert named["NETFLIX COM"]["merchant"] == "Netflix" and stats["named"] == 1
