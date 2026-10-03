import pytest
from fastapi.testclient import TestClient

from photo_shadowing import elevenlabs, gemini, photos, server, storage, summary

client = TestClient(server.app)


@pytest.fixture
def session(monkeypatch):
    monkeypatch.setattr(photos, "pick", lambda q: {"source": "picsum", "url": "https://example.com/p.jpg", "credit": {}})
    monkeypatch.setattr(photos, "download", lambda url, dest: dest.write_bytes(b"jpg"))
    r = client.post("/api/sessions", json={"query": "cafe"})
    assert r.status_code == 200
    return r.json()


def test_create_session_saves_under_year_month(session, practice_dir):
    sid = session["id"]
    assert (practice_dir / sid[:4] / sid[4:6] / sid / "session.json").exists()
    assert client.get("/api/sessions").json()[0]["id"] == sid


def test_full_flow(session, monkeypatch):
    sid = session["id"]
    monkeypatch.setattr(gemini, "transcribe", lambda wav: "This is a cafe.")
    monkeypatch.setattr(gemini, "correct", lambda photo, text, level, n: {
        "corrected": text, "corrections": [{"before": "a", "after": "the", "reason_ja": "理由"}],
        "ideal": "This is a cafe.", "key_expressions": [], "feedback_ja": "", "score": 70})

    def fake_tts(d, text, voice_id, stability, previous):
        (d / "model_x.mp3").write_bytes(b"mp3")
        return {"file": "model_x.mp3", "text": text, "sentences": [], "words": []}

    monkeypatch.setattr(elevenlabs, "synthesize", fake_tts)
    monkeypatch.setattr(gemini, "evaluate", lambda wav, ref, mode: {
        "overall": 80, "pronunciation": 1, "fluency": 2, "intonation": 3, "completeness": 4,
        "word_issues": [{"word": "cafe", "problem_ja": "p", "tip_ja": "t"}]})

    assert client.post(f"/api/sessions/{sid}/transcribe", content=b"wav").json() == {"text": "This is a cafe."}
    s = client.post(f"/api/sessions/{sid}/correct", json={"text": "This is cafe."}).json()
    assert s["attempts"][0]["score"] == 70 and s["tts"] is None
    assert client.post(f"/api/sessions/{sid}/tts", json={}).json()["file"] == "model_x.mp3"
    rec = client.post(f"/api/sessions/{sid}/recordings?seg=0&mode=repeat&reference=This%20is%20a%20cafe.",
                      content=b"wav").json()
    assert rec["n"] == 1 and rec["file"] == "rec_001.wav"
    assert client.post(f"/api/sessions/{sid}/recordings/1/evaluate").json()["overall"] == 80

    s = client.get(f"/api/sessions/{sid}").json()
    assert s["recordings"][0]["evaluation"]["overall"] == 80
    assert client.get(f"/files/{sid}/rec_001.wav").content == b"wav"

    md = summary.render(s["created"][:10])
    assert "a → **the**" in md and "#1 文1 リピート：総合 80" in md and "**cafe**" in md


def test_missing_tts_file_is_hidden(session):
    s = storage.load(session["id"])
    s["tts"] = {"file": "model_gone.mp3", "text": "x", "sentences": [], "words": []}
    storage.save(s)
    assert client.get(f"/api/sessions/{s['id']}").json()["tts"] is None


def test_missing_photo_is_refetched(session, monkeypatch):
    sid = session["id"]
    storage.file_path(sid, "photo.jpg").unlink()
    monkeypatch.setattr(photos, "download", lambda url, dest: dest.write_bytes(b"again"))
    assert client.get(f"/files/{sid}/photo.jpg").content == b"again"


@pytest.mark.parametrize("path", ["/api/sessions/../etc", "/api/sessions/abc", "/files/20261003-120000/..%2Fx"])
def test_rejects_bad_paths(path):
    assert client.get(path).status_code in (400, 404)
