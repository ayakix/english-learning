"""VOA：実際の記事と音声で、聞く → 書き取る → 読む を 1 本で通す

1. 聞く：本文を見ずに全体を聞き、内容の設問（日本語・3 問）に答える
2. 書き取る：音声から切り出した 3 文をディクテーション
3. 読む：本文を読む時間を計り（WPM）、設問（5 問）に答える

AI が作った文ではなく人が読んだ音声を使うのは、音のつながりや弱く発音される語（of the, for a など）を
練習するため。書き取りの区間は Scribe の単語タイムスタンプを本文に合わせて決める。
"""
import difflib
import random
import re
import shutil
import time

from fastapi import APIRouter
from pydantic import BaseModel

from . import elevenlabs, http, stock, storage
from .gemini import S, generate
from .http import ApiError
from .listening import score_answer, tokens
from .sources import voa as source

SKILL = "voa"
router = APIRouter(prefix="/api/voa")

LEARNER = "a Japanese adult learner of English (around CEFR B1) whose goal is everyday conversation"
DICTATION_COUNT = 3
AUDIO = "audio.mp3"


# ------------------------------------------------------- 本文と音声の対応 ---
# 略語と名前の頭文字（Pearl S. Buck）の後では文を切らない
ABBREV_RE = re.compile(r"\b(Mr|Mrs|Ms|Dr|St|Jr|Sr|U\.S|e\.g|i\.e|[A-Z])\.$")


def split_sentences(paragraphs: list[dict]) -> list[str]:
    """小見出しは音声で読まれないので除き、段落を文に分ける"""
    out = []
    for p in paragraphs:
        if p["heading"]:
            continue
        buf = ""
        for part in re.split(r"(?:(?<=[.!?])|(?<=[.!?][”\"’']))\s+(?=[“\"‘'A-Z0-9])", p["text"]):
            buf = (buf + " " + part).strip()
            if not ABBREV_RE.search(buf):
                out.append(buf)
                buf = ""
        if buf:
            out.append(buf)
    return out


def align(sentences: list[str], words: list[dict]) -> list[dict]:
    """本文の文ごとに、音声での開始・終了秒を求める

    Scribe の書き起こしは数字の書き方（40 / forty）などが本文と違うことがあるので、
    単語列の一致部分だけを手がかりにする。文の最初と最後の語が一致したものを exact とし、
    書き取りにはそれだけを使う（区間がずれると、文の一部が切れて聞こえるため）。
    """
    art, art_sent = [], []
    for si, s in enumerate(sentences):
        for t in tokens(s):
            art.append(t)
            art_sent.append(si)
    stt, stt_word = [], []
    for wi, w in enumerate(words):
        for t in tokens(w["text"]):
            stt.append(t)
            stt_word.append(wi)
    mapping = {}
    for a, b, n in difflib.SequenceMatcher(None, art, stt, autojunk=False).get_matching_blocks():
        for k in range(n):
            mapping[a + k] = stt_word[b + k]

    out, pos = [], 0
    for si, s in enumerate(sentences):
        n = len(tokens(s))
        idx = range(pos, pos + n)
        pos += n
        hit = [i for i in idx if i in mapping]
        if not hit:
            out.append({"text": s, "start": None, "end": None, "exact": False, "match": 0.0})
            continue
        out.append({"text": s, "start": words[mapping[hit[0]]]["start"], "end": words[mapping[hit[-1]]]["end"],
                    "exact": hit[0] == idx[0] and hit[-1] == idx[-1], "match": round(len(hit) / n, 2)})
    return out


def dictation_candidates(aligned: list[dict]) -> list[int]:
    """書き取りに向く文：区間が正確・数字なし（書き方の違いで減点しないため）・長すぎず短すぎない"""
    return [i for i, a in enumerate(aligned)
            if a["exact"] and a["match"] >= 0.9 and 7 <= len(tokens(a["text"])) <= 22
            and not re.search(r"\d", a["text"])]


# ------------------------------------------------------------------ 設問 ---
QUESTION = S("OBJECT", properties={
    "q": S("STRING"),
    "options": S("ARRAY", items=S("STRING")),
    "answer": S("INTEGER", description="正解の options の添字（0 始まり）"),
    "explanation_ja": S("STRING"),
}, required=["q", "options", "answer", "explanation_ja"])

EXERCISE_SCHEMA = S("OBJECT", properties={
    "summary_ja": S("STRING"),
    "listening_questions": S("ARRAY", items=QUESTION),
    "dictation": S("ARRAY", items=S("OBJECT", properties={
        "sentence": S("INTEGER", description="候補の文番号"),
        "ja": S("STRING"),
        "points_ja": S("STRING"),
    }, required=["sentence", "ja", "points_ja"])),
    "reading_questions": S("ARRAY", items=QUESTION),
}, required=["summary_ja", "listening_questions", "dictation", "reading_questions"])


def generate_exercise(title: str, sentences: list[str], candidates: list[int]) -> dict:
    numbered = "\n".join("[%d] %s" % (i, s) for i, s in enumerate(sentences))
    prompt = (
        "You are making an exercise from a real VOA Learning English article for %s.\n"
        "Title: %s\nArticle (numbered sentences):\n%s\n\n"
        "summary_ja: a 2-3 sentence summary in Japanese.\n"
        "listening_questions: exactly 3 multiple-choice questions in Japanese (question and 4 options in Japanese), "
        "answered after listening to the audio once or twice WITHOUT seeing the text. "
        "1) the main topic, 2) the order of events or what happened at a specific time (follow time expressions "
        "like 'In 1910', 'After ...', 'Later'), 3) an important detail signaled by words like 'but', 'also', "
        "'because'. Make wrong options plausible by using things mentioned elsewhere in the article.\n"
        "dictation: choose exactly %d sentences ONLY from these candidate numbers: %s. Spread them across the "
        "article and prefer sentences with connected speech (linking, weak forms like 'of the', 'for a'). "
        "ja: natural Japanese translation. points_ja: listening points in Japanese (which sounds link or weaken).\n"
        "reading_questions: exactly 5 multiple-choice questions in Japanese (4 options each): main idea, two "
        "details, inference, and vocabulary in context (quote the English phrase). Vary the correct position.\n"
        "explanation_ja: why the answer is correct, in Japanese, quoting the relevant English sentence. "
        "Refer to the correct option by its content, never by a number or letter. "
        "The sentence numbers are only for choosing dictation sentences: never mention them in questions or "
        "explanations (the learner does not see them)."
    ) % (LEARNER, title, numbered, DICTATION_COUNT, ", ".join(map(str, candidates)))
    return generate([{"text": prompt}], EXERCISE_SCHEMA, temperature=0.5)


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


def used_urls() -> set[str]:
    return {(s.get("source") or {}).get("url") for s in storage.load_all(SKILL)}


def used_stock_ids() -> set[str]:
    return {(s.get("source") or {}).get("stock_id") for s in storage.load_all(SKILL)}


def download_audio(url: str, dest) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(http.request("GET", url, headers=source.HEADERS, timeout=120).content)


def restore_audio(s: dict, dest) -> None:
    """音声は git 管理外なので、clone 直後などに無ければ元から取り直す"""
    src = s["source"]
    if src.get("stock_id"):
        topic = next(t for t in stock.load_topics()["topics"] if t["id"] == src["stock_id"])
        shutil.copyfile(stock.item_dir(topic) / "audio.mp3", dest)
    else:
        download_audio(src["audio_url"], dest)


# --------------------------------------------------------------- endpoints --
@router.get("/zones")
def zones():
    """教材の取得元ごとの選択肢。AI 教材は分野ごとに、まだ使っていない本数も返す"""
    used = used_stock_ids()
    ready = stock.ready_items()
    cats = stock.load_topics()["categories"]
    return {"voa": [{"key": k, "name": name} for k, (_, name) in source.ZONES.items()],
            "ai": [{"key": k, "name": name, "left": sum(1 for t in ready if t["category"] == k and t["id"] not in used)}
                   for k, name in cats.items()]}


class NewSession(BaseModel):
    # voa：VOA の記事を探して設問を Gemini で作る / ai：Claude が書いたストック（設問も作成済み）を使う
    source: str = "voa"
    zone: str = "all"


@router.post("/sessions")
def create_session(body: NewSession):
    if body.source == "ai":
        return create_from_stock(body.zone)
    a = source.find_article(body.zone, used_urls())
    s = storage.new_session(SKILL, title=a["title"])
    d = storage.session_dir(SKILL, s["id"])
    try:
        build(s, a, body.zone)
    except Exception:
        # 途中で失敗したとき、session.json の無い音声だけのフォルダを残さない
        shutil.rmtree(d, ignore_errors=True)
        raise
    storage.save(s)
    return view(s)


def build(s: dict, a: dict, zone: str) -> None:
    """記事から音声の取得・区間の対応・設問の生成までを行い、s を埋める"""
    d = storage.session_dir(SKILL, s["id"])
    download_audio(a["audio_url"], d / AUDIO)
    words = elevenlabs.transcribe(d / AUDIO)
    sentences = split_sentences(a["paragraphs"])
    aligned = align(sentences, words)
    candidates = dictation_candidates(aligned)
    if len(candidates) < DICTATION_COUNT:
        raise ApiError("この記事は書き取りに使える文が少ないため、もう一度試してください", 502)
    ex = generate_exercise(a["title"], sentences, candidates)

    picks = [x for x in ex["dictation"] if x["sentence"] in candidates][:DICTATION_COUNT]
    picks.sort(key=lambda x: x["sentence"])
    duration = words[-1]["end"] if words else 0
    n_words = sum(len(tokens(x)) for x in sentences)
    s.update(
        source={k: a[k] for k in ("site", "url", "title", "published", "credit", "license", "audio_url")}
        | {"zone": zone},
        paragraphs=a["paragraphs"], glossary=a["glossary"], words=n_words,
        duration=round(duration), audio_wpm=round(n_words / (duration / 60)) if duration else None,
        sentences=aligned, summary_ja=ex["summary_ja"],
        listening={"questions": ex["listening_questions"], "answers": None, "correct": None, "plays": 0},
        # 区間の前後に少し余白を取り、語頭・語尾が切れて聞こえないようにする
        dictation=[{"i": i, "sentence": x["sentence"], "text": aligned[x["sentence"]]["text"],
                    "start": round(max(0, aligned[x["sentence"]]["start"] - 0.15), 2),
                    "end": round(aligned[x["sentence"]]["end"] + 0.3, 2),
                    "ja": x["ja"], "points_ja": x["points_ja"], "answer": None, "plays": 0}
                   for i, x in enumerate(picks)],
        reading={"questions": ex["reading_questions"], "answers": None, "correct": None,
                 "reading_seconds": None, "wpm": None},
    )
    if len(s["dictation"]) < DICTATION_COUNT:
        raise ApiError("書き取りの文を選べませんでした。もう一度試してください", 502)


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
