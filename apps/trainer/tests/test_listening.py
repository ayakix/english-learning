from fastapi.testclient import TestClient

from trainer import elevenlabs, listening, server

client = TestClient(server.app)


def test_score_exact_match_ignores_case_and_punctuation():
    r = listening.score_answer("I'm going to the store, okay?", "i'm going to the store okay")
    assert r["accuracy"] == 1.0 and all(d["status"] == "ok" for d in r["diff"])


def test_score_counts_wrong_missing_and_extra():
    r = listening.score_answer("I want to go there", "I wanna go there now")
    # want→wanna（wrong）、to（missing）、now（extra）で誤り 3 / 5 語
    assert r["accuracy"] == 0.4
    statuses = [d["status"] for d in r["diff"]]
    assert statuses.count("wrong") == 1 and statuses.count("missing") == 1 and statuses.count("extra") == 1


def test_score_never_negative():
    assert listening.score_answer("Hi", "this is completely different")["accuracy"] == 0.0


def test_flow_hides_text_until_answered(monkeypatch):
    monkeypatch.setattr(listening, "generate_items", lambda level, topic, n: {"title": "Cafe", "items": [
        {"text": "Can I get a coffee?", "ja": "コーヒーをください", "points_ja": "Can I が繋がる"},
        {"text": "See you later.", "ja": "またね", "points_ja": "-"}]})
    monkeypatch.setattr(elevenlabs, "speak", lambda dest, text, voice: dest.write_bytes(b"mp3") or "v1")
    s = client.post("/api/listening/sessions", json={}).json()
    assert s["items"][0] == {"i": 0, "file": "item_01.mp3"}
    s = client.post(f"/api/listening/sessions/{s['id']}/items/0/answer",
                    json={"answer": "can i get coffee", "replays": 2}).json()
    assert s["items"][0]["text"] == "Can I get a coffee?" and s["items"][0]["accuracy"] == 0.8
    assert "text" not in s["items"][1]
    assert s["result"] == {"score": 80, "details": {"answered": 1, "total": 2, "replays": 2}}
    assert client.post(f"/api/listening/sessions/{s['id']}/items/0/answer", json={"answer": "x"}).status_code == 400
