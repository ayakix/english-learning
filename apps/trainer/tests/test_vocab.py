import json
import time

import pytest
from fastapi.testclient import TestClient

from trainer import drills, server, storage

client = TestClient(server.app)


@pytest.fixture(autouse=True)
def stock(tmp_path, monkeypatch):
    root = tmp_path / "drills" / "vocab"
    root.mkdir(parents=True)
    items = [{"id": "vc001", "theme": "kitchen", "en": "stove", "ja": "コンロ", "example": "x", "audio": {"main": {"text": "stove"}}},
             {"id": "vc002", "theme": "kitchen", "en": "kettle", "ja": "やかん", "example": "x", "audio": {"main": {"text": "kettle"}}},
             {"id": "vc003", "theme": "home", "en": "neat", "ja": "きちんとした", "example": "x", "audio": {"main": {"text": "neat"}}}]
    (root / "items.json").write_text(json.dumps({"themes": [{"key": "kitchen", "name": "台所"}], "items": items}))
    monkeypatch.setattr(drills, "STOCK_DIR", tmp_path / "drills")
    return root


def _session(day: str, mode: str, marks: dict[str, bool], sid_suffix: str = "220000"):
    """過去の記録を直接書く（API は今日の session にしか付けられないため）"""
    s = storage.new_session("vocab", title="単語", mode=mode, marks={i: {"ok": ok} for i, ok in marks.items()})
    s["id"] = day.replace("-", "") + "-" + sid_suffix
    s["created"] = day + " 22:00"
    storage.save(s)


def test_review_lists_words_whose_latest_mark_is_ng():
    _session("2026-10-20", "ja-en", {"vc001": False, "vc002": False, "vc003": False})
    # 翌日に vc001 は言えた → 外れる。vc003 は付け直していないので 10/20 の × のまま残る
    _session("2026-10-21", "ja-en", {"vc001": True, "vc002": False}, "220001")
    r = client.get("/api/vocab/review/ja-en").json()
    assert [(it["id"], it["reason"]) for it in r["items"]] == [("vc002", "2026-10-21 ×"), ("vc003", "2026-10-20 ×")]
    # 向きごとに別。英→日では何も付けていない
    assert client.get("/api/vocab/review/en-ja").json()["items"] == []


def test_review_includes_manual_ids_without_marks(stock):
    (stock / "review.json").write_text(json.dumps({"updated": "2026-10-24", "ids": ["vc003"]}))
    r = client.get("/api/vocab/review/en-ja").json()
    assert r["updated"] == "2026-10-24"
    assert [(it["id"], it["reason"]) for it in r["items"]] == [("vc003", "復習")]


def test_review_rejects_unknown_mode():
    assert client.get("/api/vocab/review/review").status_code == 404


def test_marks_today_show_up_in_review_after_reload():
    client.put("/api/vocab/marks/ja-en/vc002", json={"ok": False})
    r = client.get("/api/vocab/review/ja-en").json()
    assert [it["id"] for it in r["items"]] == ["vc002"]
    assert r["items"][0]["reason"] == time.strftime("%Y-%m-%d") + " ×"
