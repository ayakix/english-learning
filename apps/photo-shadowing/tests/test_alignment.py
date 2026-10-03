from photo_shadowing.elevenlabs import split_alignment


def alignment(text: str, step: float = 0.1) -> dict:
    return {
        "characters": list(text),
        "character_start_times_seconds": [i * step for i in range(len(text))],
        "character_end_times_seconds": [(i + 1) * step for i in range(len(text))],
    }


def test_splits_words_and_sentences():
    sentences, words = split_alignment(alignment("Hi there. Look at Dr. Lee! Ok"))
    assert [s["text"] for s in sentences] == ["Hi there.", "Look at Dr. Lee!", "Ok"]
    assert [w["t"] for w in words if w["i"] == 1] == ["Look", "at", "Dr.", "Lee!"]
    assert words[0] == {"t": "Hi", "s": 0.0, "e": 0.2, "i": 0}
    assert sentences[0]["end"] == words[1]["e"]


def test_empty_alignment():
    assert split_alignment({}) == ([], [])
