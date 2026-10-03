"""リーディング：AI が作った文章を読む → 設問に答える

正答率に加えて、読む速さ（WPM：1 分あたりの語数）も記録する。
会話では相手の話を即座に理解する必要があり、速く正確に読めることがその土台になるため。
"""
import re
import time

from fastapi import APIRouter
from pydantic import BaseModel

from . import storage
from .gemini import S, generate, level_desc
from .http import ApiError

SKILL = "reading"
router = APIRouter(prefix="/api/reading")

PASSAGE_SCHEMA = S("OBJECT", properties={
    "title": S("STRING"),
    "passage": S("STRING", description="段落は空行で区切る"),
    "questions": S("ARRAY", items=S("OBJECT", properties={
        "q": S("STRING"),
        "options": S("ARRAY", items=S("STRING")),
        "answer": S("INTEGER", description="正解の options の添字（0 始まり）"),
        "explanation_ja": S("STRING"),
    }, required=["q", "options", "answer", "explanation_ja"])),
    "glossary": S("ARRAY", items=S("OBJECT", properties={
        "en": S("STRING"), "ja": S("STRING")}, required=["en", "ja"])),
}, required=["title", "passage", "questions", "glossary"])


def generate_passage(level: str, topic: str) -> dict:
    prompt = (
        "Create a reading exercise for a Japanese adult learner of English.\n"
        "Level: %s.\nTopic: %s.\n"
        "passage: 250-350 words, an engaging article, blog post, or story written for adults. "
        "Use natural, modern English.\n"
        "questions: 5 multiple-choice questions with 4 options each, testing main idea, details, inference, "
        "and vocabulary in context. Vary the position of the correct answer.\n"
        "explanation_ja: why the answer is correct, in Japanese, citing the relevant part. "
        "Refer to the correct option by its content, never by a number or letter.\n"
        "glossary: 5-8 words or phrases from the passage that may be difficult, with Japanese meanings."
    ) % (level_desc(level), topic or "a surprising everyday topic (choose one)")
    return generate([{"text": prompt}], PASSAGE_SCHEMA, temperature=0.9)


def word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9']+", text))


def view(s: dict) -> dict:
    """提出前は、正解と解説を隠して返す"""
    if s.get("submission"):
        return s
    qs = [{"q": q["q"], "options": q["options"]} for q in s["questions"]]
    return dict(s, questions=qs, glossary=[])


# --------------------------------------------------------------- endpoints --
class NewSession(BaseModel):
    level: str = "B2"
    topic: str = ""


@router.post("/sessions")
def create_session(body: NewSession):
    p = generate_passage(body.level, body.topic.strip())
    s = storage.new_session(SKILL, title=p["title"], level=body.level, topic=body.topic.strip(),
                            passage=p["passage"], words=word_count(p["passage"]),
                            questions=p["questions"], glossary=p["glossary"], submission=None)
    storage.save(s)
    return view(s)


@router.get("/sessions/{sid}")
def get_session(sid: str):
    return view(storage.load(SKILL, sid))


class SubmitBody(BaseModel):
    answers: list[int]
    # 読み始めてから「読み終えた」を押すまでの秒数（設問を解く時間は含めない）
    reading_seconds: float


@router.post("/sessions/{sid}/submit")
def submit(sid: str, body: SubmitBody):
    with storage.lock:
        s = storage.load(SKILL, sid)
        if s.get("submission"):
            raise ApiError("提出済みです", 400)
        qs = s["questions"]
        if len(body.answers) != len(qs):
            raise ApiError("すべての設問に答えてください", 400)
        correct = sum(1 for q, a in zip(qs, body.answers) if q["answer"] == a)
        wpm = round(s["words"] / (body.reading_seconds / 60)) if body.reading_seconds > 0 else None
        s["submission"] = {"time": time.strftime("%H:%M:%S"), "answers": body.answers,
                           "correct": correct, "reading_seconds": round(body.reading_seconds), "wpm": wpm}
        s["result"] = {"score": round(correct / len(qs) * 100),
                       "details": {"correct": correct, "total": len(qs), "wpm": wpm}}
        storage.save(s)
    return view(s)
