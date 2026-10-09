import json

import pytest
from fastapi.testclient import TestClient

from trainer import server, stock

client = TestClient(server.app)

SENTS = ["Gravel drains water very well in the vineyard.", "Clay keeps the soil cool and holds water.",
         "Merlot likes cooler soil than Cabernet does.", "So the two banks make different wines."]


@pytest.fixture
def wine_stock(monkeypatch, tmp_path):
    """AI 教材のストックを 1 本だけ用意する（外部 API は呼ばない）"""
    root = tmp_path / "stock"
    d = root / "wine" / "wn001"
    d.mkdir(parents=True)
    (root / "topics.json").write_text(json.dumps({"categories": {"wine": "ワイン"}, "voices": [], "topics": [
        {"id": "wn001", "category": "wine", "title": "Soils", "format": "dialogue", "level": "B1+", "key_terms": ["clay"]}]}))
    (d / "script.json").write_text(json.dumps({
        "id": "wn001", "title": "Soils", "format": "dialogue", "level": "B1+", "key_terms": ["clay"], "created": "2026-10-04 01:00",
        "cast": {"A": {"name": "Matilda"}, "B": {"name": "George"}},
        "turns": [{"speaker": "A", "text": " ".join(SENTS[:2])}, {"speaker": "B", "text": " ".join(SENTS[2:])}],
        "sentences": [{"text": t, "start": i * 4.0, "end": i * 4.0 + 3, "turn": i // 2, "speaker": "AB"[i // 2]}
                      for i, t in enumerate(SENTS)],
        "duration": 16.0, "wpm": 120}))
    (d / "audio.mp3").write_bytes(b"mp3")
    q = {"q": "?", "options": ["a", "b", "c", "d"], "answer": 1, "explanation_ja": "理由"}
    (d / "quiz.json").write_text(json.dumps({"summary_ja": "要約", "listening": [q] * 3, "reading": [q] * 5,
                                             "dictation": [{"sentence": i, "ja": "訳", "points_ja": "p"} for i in (0, 1, 3)]}))
    monkeypatch.setattr(stock, "STOCK_DIR", root)
    monkeypatch.setattr(stock, "TOPICS", root / "topics.json")


def test_flow_reveals_step_by_step(wine_stock):
    assert client.get("/api/lesson/zones").json() == [{"key": "wine", "name": "ワイン", "left": 1}]
    s = client.post("/api/lesson/sessions", json={"zone": "wine"}).json()
    sid = s["id"]
    # 聞く：本文・書き取りの英文・正解は隠れている
    assert s["stage"] == "listening" and s["source"]["stock_id"] == "wn001"
    assert s["paragraphs"] == [] and s["summary_ja"] == ""
    assert "answer" not in s["listening"]["questions"][0] and "text" not in s["dictation"][0]
    assert s["dictation"][2]["start"] == 12 - 0.12

    s = client.post(f"/api/lesson/sessions/{sid}/listening", json={"answers": [1, 1, 0], "plays": 2}).json()
    assert s["stage"] == "dictation" and s["listening"]["correct"] == 2 and s["paragraphs"] == []
    assert client.post(f"/api/lesson/sessions/{sid}/reading",
                       json={"answers": [1] * 5, "reading_seconds": 60}).status_code == 400

    for i, n in enumerate((0, 1, 3)):
        s = client.post(f"/api/lesson/sessions/{sid}/dictation/{i}", json={"answer": SENTS[n], "plays": 1}).json()
    # 聞く 2/3（67%）と書き取り 100% の平均
    assert s["stage"] == "reading" and s["result"]["score"] == 83
    assert len(s["paragraphs"]) == 2 and "answer" not in s["reading"]["questions"][0]

    s = client.post(f"/api/lesson/sessions/{sid}/reading", json={"answers": [1] * 5, "reading_seconds": 30}).json()
    assert s["stage"] == "done" and s["reading"]["correct"] == 5
    assert s["reading"]["wpm"] == round(s["words"] * 2) and s["result"]["details"]["wpm"] == s["reading"]["wpm"]


def test_used_lesson_is_not_picked_again(wine_stock):
    client.post("/api/lesson/sessions", json={"zone": "wine"})
    assert client.post("/api/lesson/sessions", json={"zone": "wine"}).status_code == 404
    assert client.get("/api/lesson/zones").json()[0]["left"] == 0
