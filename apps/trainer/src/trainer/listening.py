"""リスニング：ディクテーション（聞いて書き取る）

採点は AI に任せず、単語の一致で機械的に行う。日々の推移を見るので、採点のぶれを無くしたいため。
"""
import difflib
import re

from fastapi import APIRouter
from pydantic import BaseModel

from . import elevenlabs, storage
from .gemini import S, generate, level_desc
from .http import ApiError

SKILL = "listening"
router = APIRouter(prefix="/api/listening")


# ------------------------------------------------------------------ 採点 ---
def tokens(text: str) -> list[str]:
    """小文字にして単語に分ける。well-known は 2 語として扱う（ハイフンの有無で減点しないため）"""
    text = text.lower().replace("’", "'").replace("‘", "'")
    return re.findall(r"[a-z0-9]+(?:'[a-z]+)?", text)


def score_answer(reference: str, answer: str) -> dict:
    """単語単位の誤り率（WER）から正確さを出し、表示用の差分も返す

    diff の status: ok / wrong（別の語を書いた）/ missing（書き漏れ）/ extra（余計な語）
    """
    ref, ans = tokens(reference), tokens(answer)
    diff, errors = [], 0
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, ref, ans, autojunk=False).get_opcodes():
        if op == "equal":
            diff += [{"t": w, "status": "ok"} for w in ref[i1:i2]]
            continue
        r, a = ref[i1:i2], ans[j1:j2]
        errors += max(len(r), len(a))
        for k in range(max(len(r), len(a))):
            if k < len(r) and k < len(a):
                diff.append({"t": r[k], "status": "wrong", "heard": a[k]})
            elif k < len(r):
                diff.append({"t": r[k], "status": "missing"})
            else:
                diff.append({"t": "", "status": "extra", "heard": a[k]})
    accuracy = max(0.0, 1 - errors / len(ref)) if ref else 0.0
    return {"accuracy": round(accuracy, 3), "diff": diff}


# ------------------------------------------------------------------ 教材 ---
ITEMS_SCHEMA = S("OBJECT", properties={
    "title": S("STRING", description="セットの短い英語タイトル"),
    "items": S("ARRAY", items=S("OBJECT", properties={
        "text": S("STRING"),
        "ja": S("STRING", description="自然な日本語訳"),
        "points_ja": S("STRING", description="聞き取りのポイント（音の連結・脱落・弱形など）を日本語で"),
    }, required=["text", "ja", "points_ja"])),
}, required=["title", "items"])


def generate_items(level: str, topic: str, count: int) -> dict:
    prompt = (
        "Create a dictation set for a Japanese adult learner of English whose goal is everyday conversation.\n"
        "Level: %s.\n"
        "Topic: %s.\n"
        "Write %d sentences that people actually say in conversation (not textbook prose), 8-18 words each, "
        "increasing slightly in difficulty. Include natural connected speech features (linking, reductions like "
        "'going to', 'want to', weak forms). Write numbers as words. No names that are hard to spell.\n"
        "For each sentence give a natural Japanese translation (ja) and listening points in Japanese (points_ja)."
    ) % (level_desc(level), topic or "everyday life (choose a concrete situation)", count)
    return generate([{"text": prompt}], ITEMS_SCHEMA, temperature=0.9)


def update_result(s: dict) -> None:
    answered = [it for it in s["items"] if it.get("answer") is not None]
    acc = sum(it["accuracy"] for it in answered) / len(answered) if answered else None
    s["result"] = {"score": round(acc * 100) if acc is not None else None, "details": {
        "answered": len(answered), "total": len(s["items"]),
        "replays": sum(it.get("replays", 0) for it in answered)}}


def view(s: dict) -> dict:
    """答える前の問題は、英文と訳を隠して返す"""
    items = [it if it.get("answer") is not None else {"i": it["i"], "file": it["file"]} for it in s["items"]]
    return dict(s, items=items)


# --------------------------------------------------------------- endpoints --
class NewSession(BaseModel):
    level: str = "B2"
    topic: str = ""
    count: int = 5
    voice_id: str | None = None


@router.post("/sessions")
def create_session(body: NewSession):
    gen = generate_items(body.level, body.topic.strip(), max(1, min(body.count, 10)))
    s = storage.new_session(SKILL, title=gen["title"], level=body.level, topic=body.topic.strip(), items=[])
    d = storage.session_dir(SKILL, s["id"])
    d.mkdir(parents=True, exist_ok=True)
    for i, it in enumerate(gen["items"]):
        name = "item_%02d.mp3" % (i + 1)
        voice = elevenlabs.speak(d / name, it["text"], body.voice_id)
        s["items"].append({"i": i, "file": name, "voice_id": voice, **it, "answer": None})
    storage.save(s)
    return view(s)


@router.get("/sessions/{sid}")
def get_session(sid: str):
    return view(storage.load(SKILL, sid))


class AnswerBody(BaseModel):
    answer: str
    replays: int = 0


@router.post("/sessions/{sid}/items/{i}/answer")
def answer(sid: str, i: int, body: AnswerBody):
    with storage.lock:
        s = storage.load(SKILL, sid)
        if not 0 <= i < len(s["items"]):
            raise ApiError("問題が見つかりません", 404)
        it = s["items"][i]
        if it.get("answer") is not None:
            raise ApiError("この問題は回答済みです", 400)
        it.update(answer=body.answer, replays=body.replays, **score_answer(it["text"], body.answer))
        update_result(s)
        storage.save(s)
    return view(s)
