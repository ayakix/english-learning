"""ライティング：お題に英文で答える → 添削と観点別の採点

会話が目標なので、お題は「話すように書く」ものを中心にする（メール・意見・出来事の説明）。
書き直して何度でも提出でき、最新の提出をそのセッションの結果にする。
"""
import re
import time

from fastapi import APIRouter
from pydantic import BaseModel

from .gemini import S, generate, level_desc
from .http import ApiError
from . import storage

SKILL = "writing"
router = APIRouter(prefix="/api/writing")

KINDS = {
    "email": "a short email or chat message to a friend or colleague (reply, request, invitation, apology, etc.)",
    "opinion": "a short opinion on an everyday or work-related question, with reasons and an example",
    "story": "a description of a past personal experience or what happened recently",
}

TASK_SCHEMA = S("OBJECT", properties={
    "title": S("STRING", description="短い英語タイトル"),
    "task": S("STRING", description="英語のお題（状況と書くべき内容）"),
    "task_ja": S("STRING", description="お題の日本語訳"),
    "min_words": S("INTEGER"),
    "max_words": S("INTEGER"),
}, required=["title", "task", "task_ja", "min_words", "max_words"])

GRADE_SCHEMA = S("OBJECT", properties={
    "task": S("INTEGER", description="0-100 お題への応答の的確さ"),
    "grammar": S("INTEGER", description="0-100 文法の正確さ"),
    "vocabulary": S("INTEGER", description="0-100 語彙の幅と適切さ"),
    "coherence": S("INTEGER", description="0-100 構成・つながり"),
    "overall": S("INTEGER"),
    "cefr": S("STRING", description="A2 / B1 / B2 / C1 のいずれか"),
    "corrections": S("ARRAY", items=S("OBJECT", properties={
        "before": S("STRING"), "after": S("STRING"), "reason_ja": S("STRING")},
        required=["before", "after", "reason_ja"])),
    "improved": S("STRING", description="学習者の内容を活かした、自然で模範的な書き直し"),
    "key_expressions": S("ARRAY", items=S("OBJECT", properties={
        "en": S("STRING"), "ja": S("STRING")}, required=["en", "ja"])),
    "feedback_ja": S("STRING"),
}, required=["task", "grammar", "vocabulary", "coherence", "overall", "cefr",
             "corrections", "improved", "key_expressions", "feedback_ja"])


def generate_task(level: str, kind: str) -> dict:
    prompt = (
        "Create one writing task for a Japanese adult learner of English whose goal is everyday conversation.\n"
        "Level: %s.\nTask type: %s.\n"
        "Make the situation concrete and realistic. Choose a word range that fits the level "
        "(about 60-100 words for B1, 100-150 for B2)."
    ) % (level_desc(level), KINDS.get(kind, KINDS["email"]))
    return generate([{"text": prompt}], TASK_SCHEMA, temperature=1.0)


def grade(task: str, text: str, level: str) -> dict:
    prompt = (
        "You are an experienced English writing examiner for a Japanese adult learner (target level: %s).\n"
        "Task:\n\"\"\"\n%s\n\"\"\"\n\nLearner's answer:\n\"\"\"\n%s\n\"\"\"\n\n"
        "Score each criterion 0-100 (be calibrated: 90+ means near-native, 60 means understandable with clear errors): "
        "task (did it answer the task fully), grammar, vocabulary, coherence. overall = weighted overall score.\n"
        "cefr: the CEFR level this answer shows.\n"
        "corrections: each meaningful error (before → after) with a concise Japanese explanation (reason_ja). "
        "Skip punctuation-only changes.\n"
        "improved: rewrite the answer naturally, keeping the learner's ideas.\n"
        "key_expressions: 3-5 useful phrases from the improved version with Japanese meanings.\n"
        "feedback_ja: 2-4 sentences in Japanese (good points + top priority to improve)."
    ) % (level_desc(level), task, text.strip())
    return generate([{"text": prompt}], GRADE_SCHEMA, temperature=0.2)


def word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9']+", text))


def update_result(s: dict) -> None:
    last = s["submissions"][-1] if s["submissions"] else None
    if not last:
        return
    g = last["grade"]
    s["result"] = {"score": g["overall"], "details": {
        **{k: g[k] for k in ("task", "grammar", "vocabulary", "coherence", "cefr")},
        "words": last["words"], "wpm": last["wpm"], "submissions": len(s["submissions"])}}


# --------------------------------------------------------------- endpoints --
class NewSession(BaseModel):
    level: str = "B2"
    kind: str = "email"


@router.post("/sessions")
def create_session(body: NewSession):
    t = generate_task(body.level, body.kind)
    s = storage.new_session(SKILL, title=t["title"], level=body.level, kind=body.kind,
                            task=t, submissions=[])
    storage.save(s)
    return s


@router.get("/sessions/{sid}")
def get_session(sid: str):
    return storage.load(SKILL, sid)


class SubmitBody(BaseModel):
    text: str
    # 書き始めてから提出までの秒数（書く速さの推移を見るため）
    seconds: float = 0


@router.post("/sessions/{sid}/submit")
def submit(sid: str, body: SubmitBody):
    text = body.text.strip()
    if not text:
        raise ApiError("英文が空です", 400)
    s = storage.load(SKILL, sid)
    g = grade(s["task"]["task"], text, s.get("level", "B2"))
    words = word_count(text)
    with storage.lock:
        s = storage.load(SKILL, sid)
        s["submissions"].append({
            "time": time.strftime("%H:%M:%S"), "text": text, "words": words,
            "seconds": round(body.seconds),
            "wpm": round(words / (body.seconds / 60), 1) if body.seconds > 0 else None,
            "grade": g,
        })
        update_result(s)
        storage.save(s)
    return s
