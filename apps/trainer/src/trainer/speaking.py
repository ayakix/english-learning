"""スピーキング：写真を英語で描写 → 添削 → 理想文のシャドーイング → 発音評価

外部 API の呼び出しは時間がかかるため、エンドポイントは同期関数（FastAPI がスレッドプールで実行）にする。
録音の WAV を生で受け取るエンドポイントだけは Request から読む必要があるので async にし、
重い処理は run_in_threadpool に逃がしてイベントループを止めないようにする。
"""
import time

from fastapi import APIRouter, Request
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from . import elevenlabs, photos, storage
from .gemini import S, generate, inline, level_desc
from .http import ApiError

SKILL = "speaking"
router = APIRouter(prefix="/api/speaking")


# ------------------------------------------------------------------ Gemini --
def transcribe(wav: bytes) -> str:
    parts = [
        {"text": "Transcribe this English speech by a Japanese learner verbatim. "
                 "Keep the speaker's grammar mistakes exactly as spoken (do NOT correct them). "
                 "Omit filler sounds like 'uh', 'um'. Output only the transcript text."},
        inline("audio/wav", wav),
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


def correct_text(photo: bytes, text: str, level: str = "B2", sentences: int = 5) -> dict:
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
    ) % (text.strip(), int(sentences), level_desc(level))
    return generate([{"text": prompt}, inline("image/jpeg", photo)], CORRECTION_SCHEMA, temperature=0.5)


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


def evaluate_audio(wav: bytes, reference: str, mode: str) -> dict:
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
    return generate([{"text": prompt}, inline("audio/wav", wav)], EVAL_SCHEMA, temperature=0.2)


# ------------------------------------------------------------------ result --
def update_result(s: dict) -> None:
    """進捗の集計用。シャドーイングの評価のうち、総合点が最も高い録音をその日の実力とみなす"""
    evs = [r["evaluation"] for r in s.get("recordings", []) if r.get("evaluation")]
    best = max(evs, key=lambda e: e["overall"], default=None)
    details = {"description": (s.get("correction") or {}).get("score"), "recordings": len(s.get("recordings", []))}
    if best:
        details.update({k: best[k] for k in ("pronunciation", "fluency", "intonation", "completeness")})
    s["result"] = {"score": best["overall"] if best else None, "details": details}


def view(s: dict) -> dict:
    """フロントに返す形に整える

    clone 直後などで手本音声のファイルが無いときは、tts を無いものとして返して作り直しを促す。
    session.json 自体は書き換えない（タイムスタンプの情報を消さないため）。
    """
    tts = s.get("tts")
    if tts and not storage.file_path(SKILL, s["id"], tts["file"]).exists():
        s = dict(s, tts=None)
    return s


# --------------------------------------------------------------- endpoints --
@router.get("/sessions/{sid}")
def get_session(sid: str):
    return view(storage.load(SKILL, sid))


class NewSession(BaseModel):
    query: str = ""


@router.post("/sessions")
def create_session(body: NewSession):
    query = body.query.strip()
    photo = photos.pick(query)
    s = storage.new_session(
        SKILL,
        title=photo["credit"].get("alt") or query or "写真描写",
        query=query,
        photo=photo,
        attempts=[],       # 自分の説明（複数回可）
        correction=None,   # 最新の添削結果
        tts=None,          # 手本音声
        recordings=[],     # シャドーイング録音
    )
    d = storage.session_dir(SKILL, s["id"])
    d.mkdir(parents=True, exist_ok=True)
    photos.download(photo["url"], d / "photo.jpg")
    storage.save(s)
    return s


@router.post("/sessions/{sid}/transcribe")
async def transcribe_description(sid: str, request: Request):
    wav = await request.body()
    d = storage.session_dir(SKILL, sid)
    if not d.exists():
        raise ApiError("session not found", 404)
    n = len(list(d.glob("describe_*.wav"))) + 1
    (d / ("describe_%02d.wav" % n)).write_bytes(wav)
    return {"text": await run_in_threadpool(transcribe, wav)}


class CorrectBody(BaseModel):
    text: str
    level: str = "B2"
    sentences: int = 5


@router.post("/sessions/{sid}/correct")
def correct(sid: str, body: CorrectBody):
    text = body.text.strip()
    if not text:
        raise ApiError("説明文が空です", 400)
    photo = storage.file_path(SKILL, sid, "photo.jpg").read_bytes()
    res = correct_text(photo, text, body.level, body.sentences)
    with storage.lock:
        s = storage.load(SKILL, sid)
        s["attempts"].append({"time": time.strftime("%H:%M:%S"), "text": text, "score": res.get("score")})
        s["correction"] = dict(res, original=text, level=body.level)
        s["tts"] = None
        update_result(s)
        storage.save(s)
    return view(s)


class IdealBody(BaseModel):
    ideal: str


@router.put("/sessions/{sid}/ideal")
def update_ideal(sid: str, body: IdealBody):
    """理想文を手動編集"""
    with storage.lock:
        s = storage.load(SKILL, sid)
        if not s.get("correction"):
            raise ApiError("先に添削してください", 400)
        s["correction"]["ideal"] = body.ideal.strip()
        s["tts"] = None
        storage.save(s)
    return view(s)


class TtsBody(BaseModel):
    voice_id: str | None = None
    stability: float = 0.5


@router.post("/sessions/{sid}/tts")
def make_tts(sid: str, body: TtsBody):
    s = storage.load(SKILL, sid)
    text = ((s.get("correction") or {}).get("ideal") or "").strip()
    if not text:
        raise ApiError("読み上げる文章がありません", 400)
    tts = elevenlabs.synthesize(storage.session_dir(SKILL, sid), text, body.voice_id, body.stability, s.get("tts"))
    with storage.lock:
        s = storage.load(SKILL, sid)
        s["tts"] = tts
        storage.save(s)
    return tts


@router.post("/sessions/{sid}/recordings")
async def add_recording(sid: str, request: Request, seg: str = "all", mode: str = "overlap", reference: str = ""):
    wav = await request.body()
    with storage.lock:
        s = storage.load(SKILL, sid)
        n = max((r["n"] for r in s["recordings"]), default=0) + 1
        name = "rec_%03d.wav" % n
        storage.file_path(SKILL, sid, name).write_bytes(wav)
        rec = {"n": n, "file": name, "seg": seg, "mode": mode, "reference": reference,
               "time": time.strftime("%H:%M:%S"), "evaluation": None}
        s["recordings"].append(rec)
        update_result(s)
        storage.save(s)
    return rec


@router.post("/sessions/{sid}/recordings/{n}/evaluate")
def evaluate(sid: str, n: int):
    s = storage.load(SKILL, sid)
    rec = next((r for r in s["recordings"] if r["n"] == n), None)
    if not rec:
        raise ApiError("録音が見つかりません", 404)
    if not rec.get("reference"):
        raise ApiError("手本テキストがありません", 400)
    wav = storage.file_path(SKILL, sid, rec["file"]).read_bytes()
    ev = evaluate_audio(wav, rec["reference"], rec.get("mode", "overlap"))
    with storage.lock:
        s = storage.load(SKILL, sid)
        for r in s["recordings"]:
            if r["n"] == n:
                r["evaluation"] = ev
        update_result(s)
        storage.save(s)
    return ev
