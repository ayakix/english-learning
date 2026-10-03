"""AI で作るリスニング教材のストック（原稿と音声）

content/generated/topics.json の題材ごとに、Claude（Claude Code の会話中）が約 2 分の原稿を
script.json の turns に書き、このモジュールが ElevenLabs で音声にして文ごとの区間を足す。
原稿を Gemini で自動生成しないのは、題材に合った内容と自然さを Claude が確認しながら書くため。
練習のたびに作らずまとめて作っておくのは、題材の重なりを防ぎ、TTS の割引期間にまとめて作るため。
設問は練習するときに Gemini で作る（安く、後からプロンプトを直せるため）。

保存先：content/generated/<分野>/<id>/
  script.json … 原稿・話者・文ごとの区間（git 管理する。AI が書いた文章なので公開してよい）
  audio.mp3   … 音声（容量が大きいので git 管理外）

文の間・話者の切り替わりに無音を足すため、TTS は PCM で受け取り、つないでから ffmpeg で mp3 にする。
v4 の TTS は速さの指定が効かないので、間を足して聞き取りやすくしている（音を引き伸ばすと不自然になる）。
TTS の結果は .cache/stock/ に残し、間の長さを調整して作り直すときにクレジットを使わないようにする。
"""
import base64
import hashlib
import json
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import elevenlabs, http
from .config import REPO_ROOT, settings

STOCK_DIR = REPO_ROOT / "content" / "generated"
TOPICS = STOCK_DIR / "topics.json"
MODEL = "eleven_v4_turbo"
CACHE_DIR = REPO_ROOT / ".cache" / "stock"
# 16bit・モノラルの PCM（Starter プランで使える最大のサンプリング周波数）
SAMPLE_RATE = 24000
OUTPUT_FORMAT = "pcm_%d" % SAMPLE_RATE
# 足す無音の秒数（2026-10-03 の試作で「話者の切り替わりに間がほしい」「もう少しゆっくり」と言われたため）
SENTENCE_GAP = 0.35
PARAGRAPH_GAP = 0.6
TURN_GAP = 0.8
# Starter プランは同時 3 本まで。他の練習の分を空けておく
TTS_WORKERS = 2


def load_topics() -> dict:
    return json.loads(TOPICS.read_text(encoding="utf-8"))


def item_dir(topic: dict) -> Path:
    return STOCK_DIR / topic["category"] / topic["id"]


def pick_voices(topic: dict, index: int, voices: list[dict]) -> dict[str, dict]:
    """topics.json での順番で声を順番に割り当てる（偏りなく、作り直しても同じ声になるように）。
    会話のもう 1 人は、聞き分けやすいよう性別の違う声から選ぶ"""
    a = voices[index % len(voices)]
    if topic["format"] != "dialogue":
        return {"A": a}
    others = [v for v in voices if v["gender"] != a["gender"]] or [v for v in voices if v is not a]
    return {"A": a, "B": others[(index // len(voices)) % len(others)]}


def tts(text: str, voice_id: str) -> tuple[bytes, list[dict], int]:
    """1 区切り分の音声 → (PCM, 文ごとの区間, 消費クレジット)。同じ条件の結果が残っていればそれを使う"""
    key = hashlib.sha1(("%s|%s|%s|%s" % (text, voice_id, MODEL, OUTPUT_FORMAT)).encode()).hexdigest()[:16]
    pcm_path, meta_path = CACHE_DIR / (key + ".pcm"), CACHE_DIR / (key + ".json")
    if pcm_path.exists() and meta_path.exists():
        return pcm_path.read_bytes(), json.loads(meta_path.read_text()), 0
    r = http.request("POST", "%s/text-to-speech/%s/with-timestamps" % (elevenlabs.API, voice_id),
                     headers={"xi-api-key": settings.eleven_key}, params={"output_format": OUTPUT_FORMAT},
                     json={"text": text, "model_id": MODEL}, timeout=180)
    res = r.json()
    sentences, _ = elevenlabs.split_alignment(res.get("alignment") or res.get("normalized_alignment") or {})
    pcm = base64.b64decode(res["audio_base64"])
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    pcm_path.write_bytes(pcm)
    meta_path.write_text(json.dumps(sentences))
    return pcm, sentences, int(r.headers.get("character-cost") or 0)


def assemble(parts: list[tuple[bytes, list[dict]]], turn_gap: float) -> tuple[bytes, list[dict]]:
    """区切りごとの PCM を、文の間・区切りの間に無音を入れてつなぎ、つないだ後の文の区間を返す

    文の切れ目は「前の文の終わり」と「次の文の始まり」の中間で切る（語尾・語頭を削らないため）。
    返す文の区間には turn（何番目の区切りか）を付ける。
    """
    bps = SAMPLE_RATE * 2
    silence = lambda sec: b"\0" * (int(sec * SAMPLE_RATE) * 2)
    out, sentences = bytearray(), []
    for ti, (pcm, sents) in enumerate(parts):
        cuts = [0.0] + [(a["end"] + b["start"]) / 2 for a, b in zip(sents, sents[1:])] + [len(pcm) / bps]
        for si, s in enumerate(sents):
            begin, end = int(cuts[si] * SAMPLE_RATE) * 2, int(cuts[si + 1] * SAMPLE_RATE) * 2
            base = len(out) / bps - cuts[si]
            sentences.append({"text": s["text"], "start": round(s["start"] + base, 3), "end": round(s["end"] + base, 3),
                              "turn": ti})
            out += pcm[begin:end]
            if si < len(sents) - 1:
                out += silence(SENTENCE_GAP)
        if ti < len(parts) - 1:
            out += silence(turn_gap)
    return bytes(out), sentences


def encode_mp3(pcm: bytes, dest: Path) -> None:
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg が必要です（brew install ffmpeg）")
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "s16le", "-ar", str(SAMPLE_RATE), "-ac", "1",
                    "-i", "pipe:0", "-b:a", "96k", str(dest)], input=pcm, check=True)


def is_built(topic: dict) -> bool:
    return (item_dir(topic) / "audio.mp3").exists()


def build(topic: dict, index: int, voices: list[dict]) -> dict:
    """原稿（script.json の turns）を音声にして保存し、script.json の中身を返す"""
    d = item_dir(topic)
    draft = json.loads((d / "script.json").read_text(encoding="utf-8"))
    cast = pick_voices(topic, index, voices)
    turns = [t for t in draft["turns"] if t["text"].strip()]
    if topic["format"] != "dialogue":
        turns = [dict(t, speaker="A") for t in turns]
    parts, credits = [], 0
    for t in turns:
        pcm, sents, cost = tts(t["text"], cast[t["speaker"]]["id"])
        parts.append((pcm, sents))
        credits += cost
    pcm, sentences = assemble(parts, TURN_GAP if topic["format"] == "dialogue" else PARAGRAPH_GAP)
    for s in sentences:
        s["speaker"] = turns[s["turn"]]["speaker"]
    offset = len(pcm) / (SAMPLE_RATE * 2)
    words = sum(len(t["text"].split()) for t in turns)
    script = {
        "id": topic["id"], "author": draft.get("author", "claude"), "category": topic["category"], "title": topic["title"], "level": topic["level"],
        "format": topic["format"], "key_terms": topic["key_terms"],
        "cast": {k: {"name": v["name"], "id": v["id"], "accent": v["accent"]} for k, v in cast.items()},
        "turns": turns, "sentences": sentences, "words": words, "duration": round(offset, 1),
        "wpm": round(words / (offset / 60)) if offset else None,
        "tts_model": MODEL, "credits": credits, "created": time.strftime("%Y-%m-%d %H:%M"),
    }
    encode_mp3(pcm, d / "audio.mp3")
    (d / "script.json").write_text(json.dumps(script, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return script


def build_many(ids: list[str] | None = None, limit: int | None = None) -> list[dict]:
    data = load_topics()
    order = {t["id"]: i for i, t in enumerate(data["topics"])}
    topics = [t for t in data["topics"] if not ids or t["id"] in ids]
    # 原稿があってまだ音声にしていないものだけ（作り直してクレジットを無駄にしないため）
    todo = [t for t in topics if (item_dir(t) / "script.json").exists() and not is_built(t)][:limit]

    def one(t):
        try:
            s = build(t, order[t["id"]], data["voices"])
            print("%s %-50s %4ds %3d wpm %4d credits" % (t["id"], t["title"][:50], s["duration"], s["wpm"] or 0,
                                                         s["credits"]), flush=True)
            return s
        except Exception as e:  # 1 本の失敗で全体を止めない（後で同じコマンドを流せば残りだけ作る）
            print("%s 失敗: %s" % (t["id"], str(e)[:200]), flush=True)
            return None

    with ThreadPoolExecutor(TTS_WORKERS) as ex:
        done = [s for s in ex.map(one, todo) if s]
    print("作成 %d 本 / 消費 %d クレジット" % (len(done), sum(s["credits"] for s in done)))
    return done


# ------------------------------------------------------------- 練習で使う ---
def ready_items(category: str | None = None) -> list[dict]:
    """原稿・音声・設問（quiz.json）がそろっていて練習に使える題材"""
    data = load_topics()
    return [t for t in data["topics"] if (not category or t["category"] == category)
            and is_built(t) and (item_dir(t) / "quiz.json").exists()]


def load_item(topic: dict) -> tuple[dict, dict]:
    d = item_dir(topic)
    return (json.loads((d / "script.json").read_text(encoding="utf-8")),
            json.loads((d / "quiz.json").read_text(encoding="utf-8")))
