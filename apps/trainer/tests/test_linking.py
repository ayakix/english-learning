import json

from fastapi.testclient import TestClient

from trainer import linking, server

client = TestClient(server.app)


def test_lists_items_with_audio_and_serves_only_known_files(tmp_path, monkeypatch):
    root = tmp_path / "linking"
    (root / "lk001").mkdir(parents=True)
    (root / "lk001" / "model_a.mp3").write_bytes(b"a")
    (root / "lk001" / "model_b.mp3").write_bytes(b"b")
    (root / "lk001" / "secret.txt").write_text("x")
    item = {"id": "lk001", "type": "flap-t", "phrase": "get‿it", "text": "get it", "kana": "ゲリッ(ト)",
            "sentence": "I don't get‿it.", "sentence_text": "I don't get it.", "voice": {"name": "Sarah", "id": "v"},
            "tts": {"file": "model_a.mp3"}, "tts_sentence": {"file": "model_b.mp3"}}
    # 音声がまだ無い例題は一覧に出さない
    todo = {**item, "id": "lk002", "tts": None, "tts_sentence": None}
    (root / "items.json").write_text(json.dumps({"types": [{"key": "flap-t", "name": "t", "description_ja": "",
                                                            "example": ""}], "items": [item, todo]}))
    monkeypatch.setattr(linking, "STOCK_DIR", root)
    monkeypatch.setattr(linking, "ITEMS", root / "items.json")

    d = client.get("/api/linking").json()
    assert [it["id"] for it in d["items"]] == ["lk001"]
    assert d["items"][0]["audio"] == "model_a.mp3" and d["items"][0]["audio_sentence"] == "model_b.mp3"
    assert client.get("/api/linking/audio/lk001/model_b.mp3").content == b"b"
    assert client.get("/api/linking/audio/lk001/secret.txt").status_code == 404
    assert client.get("/api/linking/audio/lk009/model_a.mp3").status_code == 404


def test_drills_serve_items_with_audio_only(tmp_path, monkeypatch):
    from trainer import drills

    d = tmp_path / "drills" / "minimal-pairs"
    (d / "mp001").mkdir(parents=True)
    (d / "mp001" / "model_a.mp3").write_bytes(b"a")
    (d / "mp001" / "model_b.mp3").write_bytes(b"b")
    ok = {"id": "mp001", "type": "l-r", "a": "light", "b": "right",
          "audio": {"a": {"text": "light", "file": "model_a.mp3"}, "b": {"text": "right", "file": "model_b.mp3"}}}
    todo = {"id": "mp002", "type": "l-r", "a": "lock", "b": "rock",
            "audio": {"a": {"text": "lock"}, "b": {"text": "rock"}}}
    (d / "items.json").write_text(json.dumps({"name": "ミニマルペア", "voices": "us", "types": [], "items": [ok, todo]}))
    monkeypatch.setattr(drills, "STOCK_DIR", tmp_path / "drills")

    assert [it["id"] for it in client.get("/api/drills/minimal-pairs").json()["items"]] == ["mp001"]
    assert client.get("/api/drills/minimal-pairs/audio/mp001/model_b.mp3").content == b"b"
    assert client.get("/api/drills/minimal-pairs/audio/mp001/items.json").status_code == 404
    assert client.get("/api/drills/secret").status_code == 404
