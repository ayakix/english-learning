from fastapi.testclient import TestClient

from trainer import progress, reading, server, summary, writing

client = TestClient(server.app)

GRADE = {"task": 70, "grammar": 60, "vocabulary": 65, "coherence": 75, "overall": 68, "cefr": "B1",
         "corrections": [{"before": "I goed", "after": "I went", "reason_ja": "不規則動詞"}],
         "improved": "...", "key_expressions": [], "feedback_ja": ""}


def test_writing_flow(monkeypatch):
    monkeypatch.setattr(writing, "generate_task", lambda level, kind: {
        "title": "Reply", "task": "Reply to Tom.", "task_ja": "返信", "min_words": 60, "max_words": 100})
    monkeypatch.setattr(writing, "grade", lambda task, text, level: GRADE)
    s = client.post("/api/writing/sessions", json={"kind": "email"}).json()
    s = client.post(f"/api/writing/sessions/{s['id']}/submit",
                    json={"text": "Hi Tom, I goed to the park.", "seconds": 60}).json()
    assert s["submissions"][0]["words"] == 7 and s["submissions"][0]["wpm"] == 7.0
    assert s["result"]["score"] == 68 and s["result"]["details"]["cefr"] == "B1"
    assert "I goed → **I went**" in summary.render(s["created"][:10])


def test_reading_flow_hides_answers_until_submitted(monkeypatch):
    qs = [{"q": f"Q{i}", "options": ["a", "b", "c", "d"], "answer": i % 4, "explanation_ja": "解説"} for i in range(5)]
    monkeypatch.setattr(reading, "generate_passage", lambda level, topic: {
        "title": "T", "passage": "one two three four five six", "questions": qs, "glossary": [{"en": "x", "ja": "y"}]})
    s = client.post("/api/reading/sessions", json={}).json()
    assert "answer" not in s["questions"][0] and s["glossary"] == [] and s["words"] == 6
    assert client.post(f"/api/reading/sessions/{s['id']}/submit",
                       json={"answers": [0], "reading_seconds": 3}).status_code == 400
    s = client.post(f"/api/reading/sessions/{s['id']}/submit",
                    json={"answers": [0, 1, 2, 0, 0], "reading_seconds": 3}).json()
    assert s["questions"][0]["answer"] == 0 and s["submission"]["correct"] == 4
    assert s["result"] == {"score": 80, "details": {"correct": 4, "total": 5, "wpm": 120}}

    rows = client.get("/api/progress").json()["weeks"]
    assert rows == [{"week": progress.week_start(s["created"][:10]), "skill": "reading", "count": 1,
                     "avg": 80, "wpm": 120}]
    assert "80（1 回 / 120 wpm）" in progress.render()


def test_week_start_is_monday():
    assert progress.week_start("2026-10-03") == "2026-09-28"
