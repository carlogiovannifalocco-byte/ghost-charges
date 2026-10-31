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


def test_a_refused_batch_is_tried_again_on_hosted_endpoints(monkeypatch):
    calls = []

    def chat(prompt):
        calls.append(1)
        if len(calls) == 1:
            raise names.httpx.HTTPError("429")
        return '{"NETFLIX": {"merchant": "Netflix", "kind": "subscription"}}'

    monkeypatch.setattr(names, "_chat", chat)
    monkeypatch.setenv("LLM_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("LLM_RETRY_WAIT", "0")
    named, stats = names.name_merchants({"NETFLIX": ["NETFLIX.COM"]})
    assert named["NETFLIX"]["merchant"] == "Netflix" and stats["errors"] == 0 and len(calls) == 2
