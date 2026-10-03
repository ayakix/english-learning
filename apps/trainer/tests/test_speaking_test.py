import json

from fastapi.testclient import TestClient

from trainer import server, speaking, speaking_stock

client = TestClient(server.app)


def _stock(tmp_path, monkeypatch):
    root = tmp_path / "speaking"
    d = root / "sp001"
    d.mkdir(parents=True)
    (d / "photo.jpg").write_bytes(b"jpg")
    (d / "model_abc.mp3").write_bytes(b"mp3")
    item = {"id": "sp001", "photo": {"source": "unsplash", "url": "https://example/p.jpg",
                                     "credit": {"name": "A", "profile": "", "link": "", "alt": "people at a cafe"}},
            "answer": "This picture was taken at a cafe.", "voice": {"name": "Sarah", "id": "v"},
            "tts": {"file": "model_abc.mp3", "text": "This picture was taken at a cafe.", "sentences": [], "words": []}}
    (root / "items.json").write_text(json.dumps([item]))
    monkeypatch.setattr(speaking_stock, "STOCK_DIR", root)
    monkeypatch.setattr(speaking_stock, "ITEMS", root / "items.json")


def test_test_hides_model_answer_until_graded(tmp_path, monkeypatch):
    _stock(tmp_path, monkeypatch)
    g = {"toeic": 2, "score": 64, "content": 60, "grammar": 65, "vocabulary": 62, "delivery": 66,
         "corrected": "People are sitting.", "corrections": [], "key_expressions": [], "feedback_ja": "よい"}
    monkeypatch.setattr(speaking, "transcribe", lambda wav: "people is sitting")
    monkeypatch.setattr(speaking, "grade_test", lambda *a: g)

    s = client.post("/api/speaking/tests").json()
    assert s["test"]["prep"] == 45 and s["test"]["response"] == 30
    # 解く前は模範解答と手本音声を返さない（先に見ると練習にならないため）
    assert s["test"]["model_answer"] == "" and s["tts"] is None
    assert client.get(f"/files/speaking/{s['id']}/photo.jpg").status_code == 200

    s = client.post(f"/api/speaking/sessions/{s['id']}/test?seconds=28.5", content=b"wav").json()
    assert s["test"]["answer"] == "people is sitting" and s["test"]["grade"]["toeic"] == 2
    assert s["correction"]["ideal"] == "This picture was taken at a cafe." and s["tts"]["file"] == "model_abc.mp3"
    assert s["result"]["score"] == 64
    # 一度解いた問題は出ない
    assert client.post("/api/speaking/tests").status_code == 404
    assert client.post(f"/api/speaking/sessions/{s['id']}/test", content=b"wav").status_code == 400
