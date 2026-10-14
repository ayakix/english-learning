import json
import time

import pytest
from fastapi.testclient import TestClient

from trainer import drills, progress, server, storage, summary

client = TestClient(server.app)


@pytest.fixture(autouse=True)
def stock(tmp_path, monkeypatch):
    root = tmp_path / "drills"
    rp = [{"id": "rp001", "text": "I like tea.", "level": 1, "audio": {"main": {"text": "I like tea."}}},
          {"id": "rp141", "text": "She runs every morning before work.", "level": 3,
           "audio": {"main": {"text": "x"}}}]
    sa = [{"id": "sa001", "question": "What color is the sky?", "answers": ["blue"], "audio": {"main": {"text": "x"}}}]
    for kind, items in (("repeats", rp), ("short-answers", sa)):
        (root / kind).mkdir(parents=True)
        (root / kind / "items.json").write_text(json.dumps({"items": items}))
    monkeypatch.setattr(drills, "STOCK_DIR", root)


def test_marks_create_one_session_per_mode_and_day_only_when_marked():
    # 開いただけでは記録を作らない（空の記録が残らないように）
    assert client.get("/api/versant/marks/repeats").json() == {"marks": {}}
    assert storage.load_all("versant") == []

    client.put("/api/versant/marks/repeats/rp001", json={"ok": True})
    client.put("/api/versant/marks/repeats/rp141", json={"ok": True})
    # 付け直すと上書きされる
    r = client.put("/api/versant/marks/repeats/rp141", json={"ok": False}).json()
    assert r == {"marks": {"rp001": True, "rp141": False}}
    assert client.get("/api/versant/marks/repeats").json() == r

    [s] = storage.load_all("versant")
    assert s["mode"] == "repeats" and s["title"] == "復唱"
    assert s["result"] == {"score": 50, "details": {"ok": 1, "total": 2}}
    assert s["marks"]["rp141"] == {"ok": False, "kind": "repeats", "level": 3}


def test_review_is_recorded_but_not_scored():
    client.put("/api/versant/marks/review/rp001", json={"ok": True})
    client.put("/api/versant/marks/review/sa001", json={"ok": False})
    [s] = storage.load_all("versant")
    assert s["result"] == {"score": None, "details": {"ok": 1, "total": 2}}
    # 進捗の平均には入れない
    assert [p for p in progress.points() if p["skill"] == "versant"] == []


def test_rejects_unknown_mode_and_item():
    assert client.put("/api/versant/marks/minimal-pairs/rp001", json={"ok": True}).status_code == 404
    # 即答のモードで復唱の ID は付けられない
    assert client.put("/api/versant/marks/short-answers/rp001", json={"ok": True}).status_code == 404
    assert storage.load_all("versant") == []


def test_summary_lists_missed_items_with_text(monkeypatch):
    # ID は秒単位の時刻なので、テストでは同じ秒に 2 つ目の session を作ると重なる。別の ID を振る
    day = time.strftime("%Y%m%d")
    ids = iter([day + "-220000", day + "-220001"])
    monkeypatch.setattr(storage, "new_id", lambda: next(ids))
    client.put("/api/versant/marks/repeats/rp001", json={"ok": True})
    client.put("/api/versant/marks/repeats/rp141", json={"ok": False})
    client.put("/api/versant/marks/review/sa001", json={"ok": False})
    [s] = [s for s in storage.load_all("versant") if s["mode"] == "repeats"]
    md = summary.render(s["created"][:10])
    assert "## Versant" in md
    assert "- 言えた 1 / 2（レベル 1・3）" in md
    assert "  - 言えなかった：rp141 She runs every morning before work." in md
    assert "  - 言えなかった：sa001 What color is the sky?（答え：blue）" in md
