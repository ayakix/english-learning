"""スピーキング：写真を英語で描写 → 添削 → 理想文のシャドーイング → 発音評価

外部 API の呼び出しは時間がかかるため、エンドポイントは同期関数（FastAPI がスレッドプールで実行）にする。
録音の WAV を生で受け取るエンドポイントだけは Request から読む必要があるので async にし、
重い処理は run_in_threadpool に逃がしてイベントループを止めないようにする。
"""
import random
import shutil
import time

from fastapi import APIRouter, Request
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from . import elevenlabs, photos, speaking_stock, storage
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
    """進捗の集計用。シャドーイングの評価のうち、総合点が最も高い録音をその日の実力とみなす

    テスト形式のセッションは、テストの点を使う（初見の写真を時間内に説明する力を見たいので、
    その後の模範解答のシャドーイングの点で上書きしない）。
    """
    evs = [r["evaluation"] for r in s.get("recordings", []) if r.get("evaluation")]
    best = max(evs, key=lambda e: e["overall"], default=None)
    details = {"description": (s.get("correction") or {}).get("score"), "recordings": len(s.get("recordings", []))}
    if best:
        details.update({k: best[k] for k in ("pronunciation", "fluency", "intonation", "completeness")})
    score = best["overall"] if best else None
    grade = (s.get("test") or {}).get("grade")
    if grade:
        details.update(test=True, toeic=grade["toeic"], shadowing=score)
        score = grade["score"]
    s["result"] = {"score": score, "details": details}


def view(s: dict) -> dict:
    """フロントに返す形に整える

    clone 直後などで手本音声のファイルが無いときは、tts を無いものとして返して作り直しを促す。
    session.json 自体は書き換えない（タイムスタンプの情報を消さないため）。
    """
    t = s.get("test")
    if t and not t.get("grade"):
        # テストを解く前は模範解答と手本音声を返さない（先に見ると練習にならないため）
        return dict(s, tts=None, test=dict(t, model_answer=""))
    restore_tts(s)
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


# ------------------------------------------------------------ テスト形式 ---
# TOEIC Speaking の写真描写（Questions 3-4）と同じ時間配分
TEST_PREP = 45
TEST_RESPONSE = 30

GRADE_SCHEMA = S("OBJECT", properties={
    "toeic": S("INTEGER", description="TOEIC Speaking の写真描写の採点基準（0〜3）"),
    "score": S("INTEGER", description="0-100 の総合点"),
    "content": S("INTEGER", description="0-100 写真の主な要素をどれだけ正確に描写できたか"),
    "grammar": S("INTEGER"), "vocabulary": S("INTEGER"),
    "delivery": S("INTEGER", description="0-100 発音・流暢さ・時間内に話し切れたか"),
    "corrected": S("STRING", description="解答を、内容を保ったまま最小限の修正で正しい英語にしたもの"),
    "corrections": S("ARRAY", items=S("OBJECT", properties={
        "before": S("STRING"), "after": S("STRING"), "reason_ja": S("STRING")},
        required=["before", "after", "reason_ja"])),
    "key_expressions": S("ARRAY", items=S("OBJECT", properties={
        "en": S("STRING"), "ja": S("STRING")}, required=["en", "ja"])),
    "feedback_ja": S("STRING"),
}, required=["toeic", "score", "content", "grammar", "vocabulary", "delivery", "corrected", "corrections",
             "key_expressions", "feedback_ja"])


def grade_test(photo: bytes, wav: bytes, transcript: str, seconds: float, model_answer: str) -> dict:
    prompt = (
        "You are an experienced TOEIC Speaking rater. Task: Describe a picture (Questions 3-4). "
        "The test taker, a Japanese adult learner, had %d seconds to prepare and %d seconds to speak.\n"
        "Transcript of the response (spoken in %.0f seconds):\n\"\"\"\n%s\n\"\"\"\n"
        "The attached audio is the actual response and the image is the picture.\n"
        "A model answer is given only for your reference. Do NOT require the same content or wording:\n"
        "\"\"\"\n%s\n\"\"\"\n\n"
        "toeic: rate on the official 0-3 scale. 3 = describes the main features of the picture; delivery is "
        "generally intelligible; vocabulary and structures are appropriate. 2 = relevant to the picture but meaning "
        "is sometimes unclear because of delivery, vocabulary or structure. 1 = loosely related; very limited. "
        "0 = no response or not related to the picture.\n"
        "score, content, grammar, vocabulary, delivery: 0-100, calibrated (90+ means near-native).\n"
        "corrected / corrections: minimal fixes of the response with concise Japanese explanations (reason_ja). "
        "Skip trivial changes.\n"
        "key_expressions: 4-6 useful phrases from the model answer with Japanese meanings.\n"
        "feedback_ja: 2-4 sentences in Japanese: what was good, what was missing from the picture, and the top "
        "priority for next time (e.g. structure: place -> main person -> surroundings -> background).\n"
        "If the response is silent or unintelligible, give 0 and say so."
    ) % (TEST_PREP, TEST_RESPONSE, seconds, transcript.strip() or "(empty)", model_answer.strip())
    return generate([{"text": prompt}, inline("image/jpeg", photo), inline("audio/wav", wav)],
                    GRADE_SCHEMA, temperature=0.2)


def used_stock_ids() -> set[str]:
    return {(s.get("test") or {}).get("stock_id") for s in storage.load_all(SKILL)}


def restore_tts(s: dict) -> None:
    """手本音声は git 管理外なので、clone 直後などに無ければストックからコピーし直す"""
    stock_id = (s.get("test") or {}).get("stock_id")
    tts = s.get("tts")
    if not stock_id or not tts or storage.file_path(SKILL, s["id"], tts["file"]).exists():
        return
    item = next((it for it in speaking_stock.load_items() if it["id"] == stock_id), None)
    src = item and speaking_stock.item_dir(item) / tts["file"]
    if src and src.exists():
        shutil.copyfile(src, storage.file_path(SKILL, s["id"], tts["file"]))


@router.post("/tests")
def create_test():
    """ストック（Claude が選んだ写真と模範解答）から、まだ解いていない 1 問でテストを作る"""
    used = used_stock_ids()
    items = [it for it in speaking_stock.load_items() if it["id"] not in used and speaking_stock.ensure_audio(it)]
    if not items:
        raise ApiError("テスト用の写真をすべて使い終わりました", 404)
    item = random.choice(items)
    s = storage.new_session(
        SKILL, title=item["photo"]["credit"].get("alt") or "スピーキングテスト", query="", photo=item["photo"],
        attempts=[], correction=None, tts=item["tts"], recordings=[],
        test={"stock_id": item["id"], "prep": TEST_PREP, "response": TEST_RESPONSE, "model_answer": item["answer"],
              "answer": None, "seconds": None, "grade": None},
    )
    d = storage.session_dir(SKILL, s["id"])
    d.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(speaking_stock.ensure_photo(item), d / "photo.jpg")
    shutil.copyfile(speaking_stock.item_dir(item) / item["tts"]["file"], d / item["tts"]["file"])
    storage.save(s)
    return view(s)


@router.post("/sessions/{sid}/test")
async def submit_test(sid: str, request: Request, seconds: float = 0):
    wav = await request.body()
    s = storage.load(SKILL, sid)
    t = s.get("test")
    if not t:
        raise ApiError("テストのセッションではありません", 400)
    if t.get("grade"):
        raise ApiError("このテストは採点済みです", 400)
    storage.file_path(SKILL, sid, "test.wav").write_bytes(wav)
    photo = storage.file_path(SKILL, sid, "photo.jpg").read_bytes()
    transcript = (await run_in_threadpool(transcribe, wav)).strip()
    g = await run_in_threadpool(grade_test, photo, wav, transcript, seconds, t["model_answer"])
    with storage.lock:
        s = storage.load(SKILL, sid)
        s["test"].update(answer=transcript, seconds=round(seconds, 1), grade=g)
        s["attempts"].append({"time": time.strftime("%H:%M:%S"), "text": transcript, "score": g["score"]})
        # 採点後は通常の練習と同じ画面（添削 → 模範解答のシャドーイング）で復習できるようにする
        s["correction"] = {"corrected": g["corrected"], "corrections": g["corrections"], "ideal": t["model_answer"],
                           "key_expressions": g["key_expressions"], "feedback_ja": g["feedback_ja"],
                           "score": g["score"], "original": transcript, "level": "TOEIC"}
        update_result(s)
        storage.save(s)
    return view(s)
