"""教材：AI 教材の原稿と音声で、聞く → 書き取る → 読む を 1 本で通す

1. 聞く：本文を見ずに全体を聞き、内容の設問（日本語・3 問）に答える
2. 書き取る：音声から切り出した 3 文をディクテーション
3. 読む：本文を読む時間を計り（WPM）、設問（5 問）に答える

原稿・設問は Claude が書いたストック（content/generated）を使う。
以前は VOA の記事も使っていたが、長く興味にも合わなかったので 2026-10-09 にやめた。
"""
import random
import shutil
import time

from fastapi import APIRouter
from pydantic import BaseModel

from . import stock, storage
from .http import ApiError
from .listening import score_answer, tokens

SKILL = "lesson"
router = APIRouter(prefix="/api/lesson")

AUDIO = "audio.mp3"


# ------------------------------------------------------------- セッション ---
def stage(s: dict) -> str:
    if s["listening"]["answers"] is None:
        return "listening"
    if any(d["answer"] is None for d in s["dictation"]):
        return "dictation"
    if s["reading"]["answers"] is None:
        return "reading"
    return "done"


def _hide_answers(qs: list[dict]) -> list[dict]:
    return [{"q": q["q"], "options": q["options"]} for q in qs]


def view(s: dict) -> dict:
    """進み具合に応じて、まだ見せない情報（本文・正解・書き取りの英文）を隠して返す"""
    st = stage(s)
    v = dict(s, stage=st)
    if st == "listening":
        v.update(summary_ja="", listening=dict(s["listening"], questions=_hide_answers(s["listening"]["questions"])))
    if st in ("listening", "dictation"):
        # 本文は読むところまで隠す（先に読むと聞き取りの練習にならないため）
        v.update(paragraphs=[], sentences=[], glossary=[],
                 dictation=[d if d["answer"] is not None else {k: d[k] for k in ("i", "start", "end", "answer", "plays")}
                            for d in s["dictation"]])
    if st != "done":
        v["reading"] = dict(s["reading"], questions=_hide_answers(s["reading"]["questions"]))
    return v


def update_result(s: dict) -> None:
    """スコアは「聞く」の正答率と「書き取る」の一致率の平均（どちらも聞き取りの力を見るため）。
    「読む」は一度聞いた後の答え合わせに近いので、スコアには入れず WPM と正解数を記録する"""
    lis, dic, rd = s["listening"], s["dictation"], s["reading"]
    details = {}
    lis_pct = dic_pct = None
    if lis["answers"] is not None:
        details["listening"] = "%d/%d" % (lis["correct"], len(lis["questions"]))
        lis_pct = lis["correct"] / len(lis["questions"]) * 100
    done = [d for d in dic if d["answer"] is not None]
    if done:
        dic_pct = sum(d["accuracy"] for d in done) / len(done) * 100
        details.update(dictation=round(dic_pct), replays=sum(d["plays"] for d in done))
    if rd["answers"] is not None:
        details.update(reading="%d/%d" % (rd["correct"], len(rd["questions"])), wpm=rd["wpm"])
    score = round((lis_pct + dic_pct) / 2) if lis_pct is not None and len(done) == len(dic) else None
    s["result"] = {"score": score, "details": details}


def used_stock_ids() -> set[str]:
    return {(s.get("source") or {}).get("stock_id") for s in storage.load_all(SKILL)}


def restore_audio(s: dict, dest) -> None:
    """音声は git 管理外なので、clone 直後などに無ければ AI 教材のストックから取り直す"""
    topic = next(t for t in stock.load_topics()["topics"] if t["id"] == s["source"]["stock_id"])
    shutil.copyfile(stock.item_dir(topic) / "audio.mp3", dest)


# --------------------------------------------------------------- endpoints --
@router.get("/zones")
def zones():
    """AI 教材の分野の選択肢。分野ごとに、まだ使っていない本数も返す"""
    used = used_stock_ids()
    ready = stock.ready_items()
    cats = stock.load_topics()["categories"]
    return [{"key": k, "name": name, "left": sum(1 for t in ready if t["category"] == k and t["id"] not in used)}
            for k, name in cats.items()]


class NewSession(BaseModel):
    zone: str = "all"


@router.post("/sessions")
def create_session(body: NewSession):
    return create_from_stock(body.zone)


def create_from_stock(category: str) -> dict:
    """AI 教材のストックから、まだ使っていない 1 本で練習を作る（外部 API は呼ばない）"""
    used = used_stock_ids()
    items = [t for t in stock.ready_items(None if category == "all" else category) if t["id"] not in used]
    if not items:
        raise ApiError("この分野の AI 教材は、すべて使い終わりました", 404)
    topic = random.choice(items)
    script, quiz = stock.load_item(topic)
    s = storage.new_session(SKILL, title=script["title"])
    d = storage.session_dir(SKILL, s["id"])
    d.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(stock.item_dir(topic) / "audio.mp3", d / AUDIO)
    cast = script["cast"]
    dialogue = script["format"] == "dialogue"
    sents = script["sentences"]
    n_words = sum(len(tokens(t["text"])) for t in script["turns"])
    s.update(
        source={"site": "AI 教材", "url": None, "title": script["title"], "published": script["created"][:10],
                "credit": "Script: Claude / Voice: %s (ElevenLabs)" % ", ".join(v["name"] for v in cast.values()),
                "license": "original", "audio_url": None, "zone": topic["category"], "stock_id": topic["id"],
                "level": script["level"], "format": script["format"]},
        # 会話は誰の発言か分かるよう、話者の名前を付けて段落にする
        paragraphs=[{"text": ("%s: %s" % (cast[t["speaker"]]["name"], t["text"])) if dialogue else t["text"],
                     "heading": False} for t in script["turns"]],
        glossary=[{"word": w, "definition": ""} for w in script.get("key_terms", [])],
        words=n_words, duration=round(script["duration"]), audio_wpm=script["wpm"],
        sentences=[dict(x, exact=True, match=1.0) for x in sents], summary_ja=quiz["summary_ja"],
        listening={"questions": quiz["listening"], "answers": None, "correct": None, "plays": 0},
        # 文の間に無音を入れて作った音声なので、前後の余白はその無音の中に収まる
        dictation=[{"i": i, "sentence": x["sentence"], "text": sents[x["sentence"]]["text"],
                    "start": round(max(0, sents[x["sentence"]]["start"] - 0.12), 2),
                    "end": round(sents[x["sentence"]]["end"] + 0.2, 2),
                    "ja": x["ja"], "points_ja": x["points_ja"], "answer": None, "plays": 0}
                   for i, x in enumerate(quiz["dictation"])],
        reading={"questions": quiz["reading"], "answers": None, "correct": None,
                 "reading_seconds": None, "wpm": None},
    )
    storage.save(s)
    return view(s)


@router.get("/sessions/{sid}")
def get_session(sid: str):
    return view(storage.load(SKILL, sid))


def _expect(s: dict, st: str) -> None:
    if stage(s) != st:
        raise ApiError("この段階はもう終わっているか、まだ始まっていません", 400)


def _check_answers(qs: list[dict], answers: list[int]) -> int:
    if len(answers) != len(qs):
        raise ApiError("すべての設問に答えてください", 400)
    return sum(1 for q, a in zip(qs, answers) if q["answer"] == a)


class ListeningBody(BaseModel):
    answers: list[int]
    plays: int = 0


@router.post("/sessions/{sid}/listening")
def submit_listening(sid: str, body: ListeningBody):
    with storage.lock:
        s = storage.load(SKILL, sid)
        _expect(s, "listening")
        lis = s["listening"]
        lis.update(correct=_check_answers(lis["questions"], body.answers), answers=body.answers, plays=body.plays)
        update_result(s)
        storage.save(s)
    return view(s)


class DictationBody(BaseModel):
    answer: str
    plays: int = 0


@router.post("/sessions/{sid}/dictation/{i}")
def submit_dictation(sid: str, i: int, body: DictationBody):
    with storage.lock:
        s = storage.load(SKILL, sid)
        _expect(s, "dictation")
        if not 0 <= i < len(s["dictation"]):
            raise ApiError("問題が見つかりません", 404)
        d = s["dictation"][i]
        if d["answer"] is not None:
            raise ApiError("この文は回答済みです", 400)
        d.update(answer=body.answer, plays=body.plays, **score_answer(d["text"], body.answer))
        update_result(s)
        storage.save(s)
    return view(s)


class ReadingBody(BaseModel):
    answers: list[int]
    # 読み始めてから「読み終えた」を押すまでの秒数（設問を解く時間は含めない）
    reading_seconds: float


@router.post("/sessions/{sid}/reading")
def submit_reading(sid: str, body: ReadingBody):
    with storage.lock:
        s = storage.load(SKILL, sid)
        _expect(s, "reading")
        rd = s["reading"]
        wpm = round(s["words"] / (body.reading_seconds / 60)) if body.reading_seconds > 0 else None
        rd.update(correct=_check_answers(rd["questions"], body.answers), answers=body.answers,
                  reading_seconds=round(body.reading_seconds), wpm=wpm, time=time.strftime("%H:%M:%S"))
        update_result(s)
        storage.save(s)
    return view(s)
