import json

from fastapi.testclient import TestClient

from trainer import elevenlabs, server, voa
from trainer.sources import voa as source

client = TestClient(server.app)

PAGE = """
<h1>A Short Story</h1>
"datePublished":"2025-02-25 22:05:00Z"
<a href="https://voa-audio.voanews.eu/vle/2025/02/19/abc_hq.mp3">MP3</a>
<div class="wsw">
<p>No media source currently available</p>
<p>The year was 1931. Pearl S. Buck wrote a <strong>novel</strong>.</p>
<p><strong>Early life</strong></p>
<p>She lived in China for many years with her family.</p>
<p><em>Jim Tedder wrote this story for VOA Learning English.</em></p>
<h2 class="wsw__h2">Words in This Story</h2>
<p><strong>novel</strong> <em>– n.</em> an invented story</p>
</div>
"""


def test_parse_extracts_body_heading_credit_and_glossary():
    a = source.parse("https://example/a", PAGE)
    assert a["title"] == "A Short Story" and a["published"] == "2025-02-25"
    assert a["audio_url"].endswith("_hq.mp3")
    assert [p["text"] for p in a["paragraphs"]] == [
        "The year was 1931. Pearl S. Buck wrote a novel.", "Early life", "She lived in China for many years with her family."]
    assert [p["heading"] for p in a["paragraphs"]] == [False, True, False]
    assert a["credit"] == "Jim Tedder wrote this story for VOA Learning English."
    assert a["glossary"] == [{"word": "novel", "definition": "n. an invented story"}]


def test_wire_stories_are_not_original():
    assert source.is_original("Jim Tedder wrote this story for VOA Learning English.")
    assert not source.is_original("Rod McGuirk reported this story for the Associated Press. Jill Robbins adapted it for Learning English.")
    assert not source.is_original("Kiyoko Metzler reported this story for AFP. Anna Matteo adapted it for VOA Learning English.")
    assert not source.is_original("")


def test_split_skips_headings_and_keeps_initials():
    a = source.parse("x", PAGE)
    assert voa.split_sentences(a["paragraphs"]) == [
        "The year was 1931.", "Pearl S. Buck wrote a novel.", "She lived in China for many years with her family."]


def _words(text: str, start: float = 0.0) -> list[dict]:
    return [{"text": w, "start": start + i, "end": start + i + 0.5} for i, w in enumerate(text.split())]


def test_align_uses_matching_words_and_marks_exact():
    sentences = ["The year was 1931.", "She lived in China for many years with her family."]
    # Scribe は数字を単語で書くことがある（1931 → nineteen thirty-one）
    words = _words("The year was nineteen thirty-one. She lived in China for many years with her family.")
    al = voa.align(sentences, words)
    assert al[0]["exact"] is False and al[0]["start"] == 0
    assert al[1]["exact"] is True and al[1]["start"] == 5 and al[1]["end"] == 14.5
    assert voa.dictation_candidates(al) == [1]


def test_flow_reveals_step_by_step(monkeypatch):
    sents = ["She lived in China for many years with her family.",
             "They worked very hard together and finally bought a farm.",
             "Her books told people about the lives of poor farmers.",
             "She talked to young people about the importance of education."]
    article = {"url": "https://example/a", "title": "Buck", "published": "2025-02-25", "site": source.NAME,
               "paragraphs": [{"text": s, "heading": False} for s in sents], "glossary": [],
               "credit": "Jim Tedder wrote this story for VOA Learning English.", "license": "public-domain",
               "commit_text": True, "audio_url": "https://example/a.mp3"}
    q = {"q": "?", "options": ["a", "b", "c", "d"], "answer": 1, "explanation_ja": "理由"}
    monkeypatch.setattr(source, "find_article", lambda zone, exclude: article)
    monkeypatch.setattr(voa, "download_audio", lambda url, dest: dest.parent.mkdir(parents=True, exist_ok=True)
                        or dest.write_bytes(b"mp3"))
    monkeypatch.setattr(elevenlabs, "transcribe", lambda path: _words(" ".join(sents)))
    monkeypatch.setattr(voa, "generate_exercise", lambda title, s, c: {
        "summary_ja": "要約", "listening_questions": [q] * 3, "reading_questions": [q] * 5,
        "dictation": [{"sentence": i, "ja": "訳", "points_ja": "ポイント"} for i in (0, 1, 3)]})

    s = client.post("/api/voa/sessions", json={"zone": "all"}).json()
    sid = s["id"]
    # 聞く：本文・書き取りの英文・正解は隠れている
    assert s["stage"] == "listening" and s["paragraphs"] == [] and s["summary_ja"] == ""
    assert "answer" not in s["listening"]["questions"][0] and "text" not in s["dictation"][0]
    assert s["dictation"][0]["start"] == 0 and s["dictation"][1]["start"] == 10 - 0.15

    s = client.post(f"/api/voa/sessions/{sid}/listening", json={"answers": [1, 1, 0], "plays": 2}).json()
    assert s["stage"] == "dictation" and s["listening"]["correct"] == 2 and s["paragraphs"] == []
    assert client.post(f"/api/voa/sessions/{sid}/reading", json={"answers": [1] * 5, "reading_seconds": 60}).status_code == 400

    for i, d in enumerate(s["dictation"]):
        s = client.post(f"/api/voa/sessions/{sid}/dictation/{i}", json={"answer": sents[(0, 1, 3)[i]], "plays": 1}).json()
    # 聞く 2/3（67%）と書き取り 100% の平均
    assert s["stage"] == "reading" and s["result"]["score"] == 83
    assert len(s["paragraphs"]) == 4 and "answer" not in s["reading"]["questions"][0]

    s = client.post(f"/api/voa/sessions/{sid}/reading", json={"answers": [1] * 5, "reading_seconds": 30}).json()
    assert s["stage"] == "done" and s["reading"]["correct"] == 5
    assert s["reading"]["wpm"] == round(s["words"] * 2) and s["result"]["details"]["wpm"] == s["reading"]["wpm"]


def test_failed_build_leaves_no_folder(monkeypatch, practice_dir):
    monkeypatch.setattr(source, "find_article", lambda zone, exclude: {
        "url": "u", "title": "t", "paragraphs": [], "audio_url": "a"})

    def boom(url, dest):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"mp3")
        raise RuntimeError("network")

    monkeypatch.setattr(voa, "download_audio", boom)
    try:
        client.post("/api/voa/sessions", json={})
    except RuntimeError:
        pass
    assert not list(practice_dir.glob("voa/*/*/*"))


def test_ai_stock_session_needs_no_external_api(monkeypatch, tmp_path):
    from trainer import stock

    root = tmp_path / "stock"
    d = root / "wine" / "wn001"
    d.mkdir(parents=True)
    (root / "topics.json").write_text(json.dumps({"categories": {"wine": "ワイン"}, "voices": [], "topics": [
        {"id": "wn001", "category": "wine", "title": "Soils", "format": "dialogue", "level": "B1+", "key_terms": ["clay"]}]}))
    sents = ["Gravel drains water very well in the vineyard.", "Clay keeps the soil cool and holds water.",
             "Merlot likes cooler soil than Cabernet does.", "So the two banks make different wines."]
    (d / "script.json").write_text(json.dumps({
        "id": "wn001", "title": "Soils", "format": "dialogue", "level": "B1+", "key_terms": ["clay"], "created": "2026-10-04 01:00",
        "cast": {"A": {"name": "Matilda"}, "B": {"name": "George"}},
        "turns": [{"speaker": "A", "text": " ".join(sents[:2])}, {"speaker": "B", "text": " ".join(sents[2:])}],
        "sentences": [{"text": t, "start": i * 4.0, "end": i * 4.0 + 3, "turn": i // 2, "speaker": "AB"[i // 2]}
                      for i, t in enumerate(sents)],
        "duration": 16.0, "wpm": 120}))
    (d / "audio.mp3").write_bytes(b"mp3")
    q = {"q": "?", "options": ["a", "b", "c", "d"], "answer": 2, "explanation_ja": "理由"}
    (d / "quiz.json").write_text(json.dumps({"summary_ja": "要約", "listening": [q] * 3, "reading": [q] * 5,
                                             "dictation": [{"sentence": i, "ja": "訳", "points_ja": "p"} for i in (0, 1, 3)]}))
    monkeypatch.setattr(stock, "STOCK_DIR", root)
    monkeypatch.setattr(stock, "TOPICS", root / "topics.json")

    zones = client.get("/api/voa/zones").json()
    assert zones["ai"] == [{"key": "wine", "name": "ワイン", "left": 1}]
    s = client.post("/api/voa/sessions", json={"source": "ai", "zone": "wine"}).json()
    assert s["stage"] == "listening" and s["source"]["stock_id"] == "wn001" and s["paragraphs"] == []
    assert s["dictation"][2]["start"] == 12 - 0.12
    s = client.post(f"/api/voa/sessions/{s['id']}/listening", json={"answers": [2, 2, 2], "plays": 1}).json()
    assert s["listening"]["correct"] == 3
    # 一度使った教材は選ばれない
    assert client.post("/api/voa/sessions", json={"source": "ai", "zone": "wine"}).status_code == 404
    assert client.get("/api/voa/zones").json()["ai"][0]["left"] == 0
