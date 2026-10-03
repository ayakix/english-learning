"""Gemini：音声の文字起こし / 英文添削 / 発音評価

音声を直接入力できるため、文字起こしと発音評価の両方を Gemini に任せている。
"""
import base64
import json
import re

from . import http
from .config import settings
from .http import ApiError

API = "https://generativelanguage.googleapis.com/v1beta"

# 実際に使えたモデル名。存在しないモデル名を指定されたときのフォールバック先を覚えておく
_model_cache: dict[str, str | None] = {"name": None}


def current_model() -> str:
    return _model_cache["name"] or settings.gemini_model


def _pick_fallback_model() -> str | None:
    raw = http.request("GET", API + "/models", headers={"x-goog-api-key": settings.gemini_key},
                       params={"pageSize": 200}).json()
    names = [m["name"].split("/")[-1] for m in raw.get("models", [])
             if "generateContent" in m.get("supportedGenerationMethods", [])]
    flash = [n for n in names if "flash" in n and "lite" not in n and "image" not in n
             and "tts" not in n and "live" not in n and "audio" not in n]

    def ver(n):
        m = re.search(r"gemini-(\d+(?:\.\d+)?)", n)
        return (float(m.group(1)) if m else 0, "preview" not in n and "exp" not in n)

    flash.sort(key=ver, reverse=True)
    return flash[0] if flash else (names[0] if names else None)


def generate(parts: list, schema: dict | None = None, temperature: float = 0.4):
    if not settings.gemini_key:
        raise ApiError("GEMINI_API_KEY が .env に設定されていません", 400)
    body = {"contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"temperature": temperature}}
    if schema:
        body["generationConfig"]["responseMimeType"] = "application/json"
        body["generationConfig"]["responseSchema"] = schema
    model = current_model()
    for attempt in range(2):
        try:
            res = http.request("POST", "%s/models/%s:generateContent" % (API, model),
                               headers={"x-goog-api-key": settings.gemini_key}, json=body, timeout=120).json()
            _model_cache["name"] = model
            break
        except ApiError as e:
            if e.status == 404 and attempt == 0:
                fb = _pick_fallback_model()
                if fb and fb != model:
                    print("[gemini] model %s not found → %s を使用" % (model, fb))
                    model = fb
                    continue
            raise
    try:
        cparts = res["candidates"][0]["content"]["parts"]
    except (KeyError, IndexError):
        raise ApiError("Gemini から応答がありません: " + json.dumps(res)[:500], 502)
    text = "".join(p.get("text", "") for p in cparts if not p.get("thought"))
    if schema:
        t = re.sub(r"^```(?:json)?|```$", "", text.strip()).strip()
        return json.loads(t)
    return text.strip()


def _inline(mime: str, data: bytes) -> dict:
    return {"inline_data": {"mime_type": mime, "data": base64.b64encode(data).decode("ascii")}}


def S(t, **kw):
    d = {"type": t}
    d.update(kw)
    return d


def transcribe(wav: bytes) -> str:
    parts = [
        {"text": "Transcribe this English speech by a Japanese learner verbatim. "
                 "Keep the speaker's grammar mistakes exactly as spoken (do NOT correct them). "
                 "Omit filler sounds like 'uh', 'um'. Output only the transcript text."},
        _inline("audio/wav", wav),
    ]
    return generate(parts, temperature=0.0)


CORRECTION_SCHEMA = S("OBJECT", properties={
    "corrected": S("STRING", description="学習者の文章を、意味と構成を保ったまま最小限の修正で正しい英語にしたもの"),
    "corrections": S("ARRAY", items=S("OBJECT", properties={
        "before": S("STRING"), "after": S("STRING"), "reason_ja": S("STRING")},
        required=["before", "after", "reason_ja"])),
    "ideal": S("STRING", description="写真を描写する理想的な英文（シャドーイング用）"),
    "key_expressions": S("ARRAY", items=S("OBJECT", properties={
        "en": S("STRING"), "ja": S("STRING")}, required=["en", "ja"])),
    "feedback_ja": S("STRING", description="全体への日本語コメント（良い点と次の課題）"),
    "score": S("INTEGER", description="0-100 の総合点（文法・語彙・描写の的確さ）"),
}, required=["corrected", "corrections", "ideal", "key_expressions", "feedback_ja", "score"])

LEVELS = {
    "B1": "CEFR B1 (simple, clear sentences, common vocabulary)",
    "B2": "CEFR B2 (natural, varied sentences, some idiomatic phrases)",
    "C1": "CEFR C1 (sophisticated, vivid, natively fluent)",
}


def correct(photo: bytes, text: str, level: str = "B2", sentences: int = 5) -> dict:
    prompt = (
        "You are an expert English teacher for a Japanese adult learner.\n"
        "The learner looked at the attached photo and described it in English (spoken, then transcribed).\n\n"
        "Learner's description:\n\"\"\"\n%s\n\"\"\"\n\n"
        "Tasks:\n"
        "1. corrected: fix grammar/word choice minimally, keeping the learner's content and structure.\n"
        "2. corrections: list each meaningful change (before → after) with a concise Japanese explanation (reason_ja). "
        "Skip trivial punctuation-only changes.\n"
        "3. ideal: write an ideal spoken-style description of THIS photo in about %d sentences at %s. "
        "Build on the learner's ideas, add accurate visual details from the photo, use natural spoken rhythm suitable "
        "for shadowing practice. Plain text only, no lists, no quotes.\n"
        "4. key_expressions: 4-6 useful phrases from the ideal text with Japanese meanings.\n"
        "5. feedback_ja: 2-4 sentences in Japanese (good points + what to work on next).\n"
        "6. score: 0-100.\n"
    ) % (text.strip(), int(sentences), LEVELS.get(level, LEVELS["B2"]))
    return generate([{"text": prompt}, _inline("image/jpeg", photo)], CORRECTION_SCHEMA, temperature=0.5)


EVAL_SCHEMA = S("OBJECT", properties={
    "heard": S("STRING", description="録音から実際に聞き取れた英文"),
    "overall": S("INTEGER"), "pronunciation": S("INTEGER"), "fluency": S("INTEGER"),
    "intonation": S("INTEGER"), "completeness": S("INTEGER"),
    "word_issues": S("ARRAY", items=S("OBJECT", properties={
        "word": S("STRING"), "problem_ja": S("STRING"), "tip_ja": S("STRING")},
        required=["word", "problem_ja", "tip_ja"])),
    "good_points_ja": S("ARRAY", items=S("STRING")),
    "improvements_ja": S("ARRAY", items=S("STRING")),
    "summary_ja": S("STRING"),
}, required=["heard", "overall", "pronunciation", "fluency", "intonation", "completeness",
             "word_issues", "good_points_ja", "improvements_ja", "summary_ja"])

MODE_DESC = {
    "overlap": "overlapping shadowing (speaking simultaneously with a model recording heard through headphones; "
               "faint bleed of the model voice may be present — evaluate only the learner's voice)",
    "repeat": "repeating after the model (the learner speaks alone)",
}


def evaluate(wav: bytes, reference: str, mode: str) -> dict:
    prompt = (
        "You are a strict but encouraging English pronunciation coach for a Japanese learner (target: natural American English).\n"
        "Practice type: %s.\n"
        "Reference text the learner was trying to say:\n\"\"\"\n%s\n\"\"\"\n\n"
        "Listen carefully to the attached recording and evaluate:\n"
        "- pronunciation: individual sounds (typical Japanese issues: L/R, TH, V/B, F/H, vowel insertion after consonants, "
        "schwa, final consonants, /æ/ vs /ʌ/)\n"
        "- fluency: smoothness, linking (連結), reductions, pauses, keeping up with the model pace\n"
        "- intonation: stress timing, sentence stress, pitch contour, rhythm\n"
        "- completeness: how much of the reference was actually said\n"
        "Scores 0-100 (be calibrated: 90+ means near-native). overall = weighted overall score.\n"
        "word_issues: up to 8 most important problem words/phrases, with problem_ja (何が違って聞こえたか) and tip_ja "
        "(口・舌の具体的な動かし方やコツ, カタカナ表記に頼りすぎない).\n"
        "good_points_ja: 1-3 items. improvements_ja: the top 3 actionable priorities for the next attempt.\n"
        "summary_ja: 2-3 sentences in Japanese.\n"
        "If the recording is silent or unintelligible, give low scores and say so in summary_ja."
    ) % (MODE_DESC.get(mode, "shadowing"), reference.strip())
    return generate([{"text": prompt}, _inline("audio/wav", wav)], EVAL_SCHEMA, temperature=0.2)
