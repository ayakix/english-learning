import json
import time

import pytest
from fastapi.testclient import TestClient

from trainer import drills, progress, server, storage, summary

client = TestClient(server.app)


@pytest.fixture(autouse=True)
def stock(tmp_path, monkeypatch):
    root = tmp_path / "drills"
    (root / "vocab" / "vc001").mkdir(parents=True)
    (root / "vocab" / "vc001" / "model_a.mp3").write_bytes(b"a")
    (root / "vocab" / "items.json").write_text(json.dumps({"themes": [{"key": "kitchen", "name": "台所"}], "items": [
        {"id": "vc001", "theme": "kitchen", "en": "yolk", "ja": "卵の黄身", "example": "I only eat the yolk.",
         "audio": {"main": {"text": "yolk", "file": "model_a.mp3"}}},
        {"id": "vc002", "theme": "kitchen", "en": "oven", "ja": "オーブン", "example": "Bake it in the oven.",
         "audio": {"main": {"text": "oven"}}}]}))
    monkeypatch.setattr(drills, "STOCK_DIR", root)


def test_lists_words():
    d = client.get("/api/vocab").json()
    assert [t["key"] for t in d["themes"]] == ["kitchen"]
    # 音声がまだ無い単語も意味の確認には使えるので出す（再生だけできない）
    assert [(it["en"], it["audio_file"]) for it in d["items"]] == [("yolk", "model_a.mp3"), ("oven", None)]
    assert client.get("/api/drills/vocab/audio/vc001/model_a.mp3").content == b"a"


def test_marks_are_kept_per_direction(monkeypatch):
    # ID は秒単位の時刻なので、同じ秒に 2 つ目の session を作ると重なる。別の ID を振る
    day = time.strftime("%Y%m%d")
    ids = iter([day + "-230000", day + "-230001"])
    monkeypatch.setattr(storage, "new_id", lambda: next(ids))
    assert client.get("/api/vocab/marks/ja-en").json() == {"marks": {}}
    assert storage.load_all("vocab") == []

    client.put("/api/vocab/marks/ja-en/vc001", json={"ok": False})
    client.put("/api/vocab/marks/ja-en/vc002", json={"ok": True})
    client.put("/api/vocab/marks/en-ja/vc001", json={"ok": True})
    assert client.get("/api/vocab/marks/ja-en").json() == {"marks": {"vc001": False, "vc002": True}}

    by_mode = {s["mode"]: s for s in storage.load_all("vocab")}
    assert by_mode["ja-en"]["result"] == {"score": 50, "details": {"ok": 1, "total": 2}}
    assert by_mode["en-ja"]["result"]["score"] == 100
    assert {p["score"] for p in progress.points() if p["skill"] == "vocab"} == {50, 100}

    md = summary.render(time.strftime("%Y-%m-%d"))
    assert "## 単語" in md
    assert "- 単語 日→英：言えた 1 / 2" in md
    assert "  - 言えなかった：vc001 yolk（卵の黄身）" in md


def test_rejects_unknown_mode_and_word():
    assert client.put("/api/vocab/marks/en-fr/vc001", json={"ok": True}).status_code == 404
    assert client.put("/api/vocab/marks/en-ja/vc999", json={"ok": True}).status_code == 404
    assert storage.load_all("vocab") == []
