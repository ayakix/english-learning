"""ElevenLabs：手本音声の生成（単語ごとのタイムスタンプ付き）

タイムスタンプがあると、再生中の単語のハイライトと、文ごとの区間再生ができる。
"""
import base64
import hashlib
import re
import time
from pathlib import Path

from . import http
from .config import settings
from .http import ApiError

API = "https://api.elevenlabs.io/v1"

_voices_cache: dict = {"t": 0.0, "v": None}


def _require_key():
    if not settings.eleven_key:
        raise ApiError("ELEVENLABS_API_KEY が .env に設定されていません", 400)


def list_voices() -> list[dict]:
    _require_key()
    if _voices_cache["v"] and time.time() - _voices_cache["t"] < 3600:
        return _voices_cache["v"]
    raw = http.request("GET", API + "/voices", headers={"xi-api-key": settings.eleven_key}).json()
    vs = []
    for v in raw.get("voices", []):
        labels = v.get("labels") or {}
        vs.append({"id": v["voice_id"], "name": v.get("name", ""),
                   "desc": ", ".join(x for x in [labels.get("accent"), labels.get("gender"), labels.get("age"),
                                                 labels.get("description") or labels.get("descriptive")] if x),
                   "category": v.get("category", "")})
    _voices_cache.update(t=time.time(), v=vs)
    return vs


ABBREV_RE = re.compile(r"(Mr|Mrs|Ms|Dr|St|e\.g|i\.e)\.")


def split_alignment(al: dict) -> tuple[list[dict], list[dict]]:
    """文字単位のタイムスタンプ → 単語・文の区間"""
    chars = al.get("characters", [])
    st = al.get("character_start_times_seconds", [])
    en = al.get("character_end_times_seconds", [])
    words, cur = [], None
    for i, ch in enumerate(chars):
        if ch.isspace():
            if cur:
                words.append(cur)
                cur = None
            continue
        if cur is None:
            cur = {"text": "", "start": st[i], "end": en[i]}
        cur["text"] += ch
        cur["end"] = en[i]
    if cur:
        words.append(cur)
    sentences, buf = [], []
    for w in words:
        buf.append(w)
        if re.search(r"[.!?][\"')\]]*$", w["text"]) and not ABBREV_RE.fullmatch(w["text"]):
            sentences.append(buf)
            buf = []
    if buf:
        sentences.append(buf)
    out_s, out_w = [], []
    for si, sw in enumerate(sentences):
        for w in sw:
            out_w.append({"t": w["text"], "s": round(w["start"], 3), "e": round(w["end"], 3), "i": si})
        out_s.append({"text": " ".join(w["text"] for w in sw),
                      "start": round(sw[0]["start"], 3), "end": round(sw[-1]["end"], 3)})
    return out_s, out_w


def _voice(voice_id: str | None) -> str:
    """指定がなければ .env の既定、それもなければアカウントの最初のボイスを使う"""
    _require_key()
    voice_id = voice_id or settings.eleven_voice
    if not voice_id:
        vs = list_voices()
        if not vs:
            raise ApiError("ElevenLabs のボイスが見つかりません", 400)
        voice_id = vs[0]["id"]
    return voice_id


def speak(dest: Path, text: str, voice_id: str | None = None) -> str:
    """タイムスタンプなしで音声だけを作る（リスニング問題用）。使ったボイス ID を返す"""
    voice_id = _voice(voice_id)
    r = http.request("POST", "%s/text-to-speech/%s" % (API, voice_id),
                     headers={"xi-api-key": settings.eleven_key},
                     params={"output_format": "mp3_44100_128"},
                     json={"text": text, "model_id": settings.eleven_model}, timeout=120)
    dest.write_bytes(r.content)
    return voice_id


def synthesize(dest_dir: Path, text: str, voice_id: str | None = None, stability: float = 0.5,
               previous: dict | None = None) -> dict:
    """手本音声を dest_dir に保存し、session.json に入れる tts 情報を返す

    ファイル名に条件のハッシュを含めるのは、同じ文章・声で作り直したときにクレジットを消費しないため。
    previous（今の session.json の tts）が同じ条件で、音声ファイルも残っていればそれを使い回す。
    """
    voice_id = _voice(voice_id)
    model_id = settings.eleven_model
    key = hashlib.sha1(("%s|%s|%s|%s" % (text, voice_id, model_id, stability)).encode()).hexdigest()[:12]
    name = "model_%s.mp3" % key
    if previous and previous.get("file") == name and (dest_dir / name).exists():
        return previous
    res =http.request("POST", "%s/text-to-speech/%s/with-timestamps" % (API, voice_id),
                       headers={"xi-api-key": settings.eleven_key},
                       params={"output_format": "mp3_44100_128"},
                       json={"text": text, "model_id": model_id,
                             "voice_settings": {"stability": stability, "similarity_boost": 0.75}},
                       timeout=180).json()
    (dest_dir / name).write_bytes(base64.b64decode(res["audio_base64"]))
    sentences, words = split_alignment(res.get("alignment") or res.get("normalized_alignment") or {})
    return {"file": name, "text": text, "voice_id": voice_id, "model_id": model_id,
            "stability": stability, "sentences": sentences, "words": words}


def transcribe(path: Path, language: str = "en") -> list[dict]:
    """Scribe で文字起こしし、単語ごとのタイムスタンプを返す（[{"text", "start", "end"}]）

    人が読んだ音声（VOA など）から 1 文ずつの区間を切り出すために使う。
    """
    _require_key()
    with path.open("rb") as f:
        res = http.request("POST", API + "/speech-to-text", headers={"xi-api-key": settings.eleven_key},
                           data={"model_id": "scribe_v2", "language_code": language},
                           files={"file": (path.name, f, "audio/mpeg")}, timeout=600).json()
    return [{"text": w["text"], "start": w["start"], "end": w["end"]}
            for w in res.get("words", []) if w.get("type") == "word"]
