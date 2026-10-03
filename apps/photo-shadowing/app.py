#!/usr/bin/env python3
"""
英語 写真説明 & シャドーイング練習アプリ（ローカルサーバー）

依存ライブラリなし（Python 3.8+ 標準ライブラリのみ）。
  python3 app.py  →  http://localhost:8765 を開く

使用API:
  - Unsplash   : 写真をランダム取得
  - Gemini     : 音声の文字起こし / 英文添削 / 発音評価
  - ElevenLabs : 手本音声の生成（単語ごとのタイムスタンプ付き）
"""
import base64
import hashlib
import json
import mimetypes
import os
import re
import ssl
import sys
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(ROOT, "static")
DATA_DIR = os.path.join(ROOT, "data", "sessions")
ENV_PATH = os.path.join(ROOT, ".env")


# ---------------------------------------------------------------- config ---
def load_env():
    env = {}
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    for k in list(env):
        if os.environ.get(k):
            env[k] = os.environ[k]
    return env


ENV = load_env()


def cfg(key, default=""):
    return os.environ.get(key) or ENV.get(key) or default


GEMINI_KEY = cfg("GEMINI_API_KEY")
ELEVEN_KEY = cfg("ELEVENLABS_API_KEY")
UNSPLASH_KEY = cfg("UNSPLASH_ACCESS_KEY")
GEMINI_MODEL = cfg("GEMINI_MODEL", "gemini-flash-latest")
ELEVEN_MODEL = cfg("ELEVENLABS_MODEL", "eleven_multilingual_v2")
ELEVEN_VOICE = cfg("ELEVENLABS_VOICE_ID", "")
PORT = int(cfg("PORT", "8765"))

os.makedirs(DATA_DIR, exist_ok=True)


def _ssl_context():
    try:
        import certifi  # type: ignore

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


SSL_CTX = _ssl_context()


class ApiError(Exception):
    def __init__(self, msg, status=500):
        super().__init__(msg)
        self.status = status


def http_request(url, method="GET", headers=None, body=None, timeout=90):
    data = None
    headers = dict(headers or {})
    if body is not None:
        if isinstance(body, (dict, list)):
            data = json.dumps(body).encode("utf-8")
            headers.setdefault("Content-Type", "application/json")
        else:
            data = body
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX) as r:
            return r.status, r.headers, r.read()
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:800]
        raise ApiError("%s %s → HTTP %s: %s" % (method, url.split("?")[0], e.code, detail), e.code)
    except urllib.error.URLError as e:
        raise ApiError("接続エラー (%s): %s" % (url.split("?")[0], e.reason), 502)


# --------------------------------------------------------------- storage ---
_lock = threading.Lock()


def session_dir(sid):
    if not re.fullmatch(r"[0-9A-Za-z_\-]+", sid or ""):
        raise ApiError("invalid session id", 400)
    return os.path.join(DATA_DIR, sid)


def load_session(sid):
    p = os.path.join(session_dir(sid), "session.json")
    if not os.path.exists(p):
        raise ApiError("session not found", 404)
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save_session(s):
    d = session_dir(s["id"])
    os.makedirs(d, exist_ok=True)
    tmp = os.path.join(d, "session.json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)
    os.replace(tmp, os.path.join(d, "session.json"))


def list_sessions():
    out = []
    for sid in sorted(os.listdir(DATA_DIR), reverse=True):
        p = os.path.join(DATA_DIR, sid, "session.json")
        if os.path.exists(p):
            try:
                with open(p, encoding="utf-8") as f:
                    s = json.load(f)
                evs = [r.get("evaluation", {}).get("overall") for r in s.get("recordings", []) if r.get("evaluation")]
                out.append({
                    "id": s["id"],
                    "created": s.get("created"),
                    "photo": "/data/%s/photo.jpg" % s["id"],
                    "has_ideal": bool(s.get("correction")),
                    "recordings": len(s.get("recordings", [])),
                    "best": max([e for e in evs if isinstance(e, (int, float))], default=None),
                })
            except Exception:
                pass
    return out


# ---------------------------------------------------------------- Unsplash --
def new_session(query=""):
    sid = time.strftime("%Y%m%d-%H%M%S")
    d = session_dir(sid)
    os.makedirs(d, exist_ok=True)
    credit = {}
    if UNSPLASH_KEY:
        params = {"orientation": "landscape", "content_filter": "high"}
        if query:
            params["query"] = query
        url = "https://api.unsplash.com/photos/random?" + urllib.parse.urlencode(params)
        _, _, raw = http_request(url, headers={"Authorization": "Client-ID " + UNSPLASH_KEY, "Accept-Version": "v1"})
        p = json.loads(raw)
        img_url = p["urls"]["raw"] + "&w=1600&q=80&fm=jpg&fit=max"
        credit = {
            "name": p.get("user", {}).get("name", ""),
            "profile": (p.get("user", {}).get("links", {}).get("html", "")) + "?utm_source=eigo_shadowing&utm_medium=referral",
            "link": p.get("links", {}).get("html", "") + "?utm_source=eigo_shadowing&utm_medium=referral",
            "alt": p.get("alt_description") or p.get("description") or "",
        }
        # Unsplash API ガイドライン: 利用時に download エンドポイントを叩く
        try:
            dl = p.get("links", {}).get("download_location")
            if dl:
                http_request(dl, headers={"Authorization": "Client-ID " + UNSPLASH_KEY}, timeout=10)
        except Exception:
            pass
    else:
        # キー未設定時のフォールバック（Lorem Picsum）
        img_url = "https://picsum.photos/1600/1067?random=%d" % int(time.time() * 1000)
        credit = {"name": "Lorem Picsum", "profile": "https://picsum.photos", "link": "https://picsum.photos", "alt": ""}
    _, _, img = http_request(img_url, timeout=60)
    with open(os.path.join(d, "photo.jpg"), "wb") as f:
        f.write(img)
    s = {
        "id": sid,
        "created": time.strftime("%Y-%m-%d %H:%M"),
        "query": query,
        "credit": credit,
        "attempts": [],       # 自分の説明（複数回可）
        "correction": None,   # 最新の添削結果
        "tts": None,          # 手本音声
        "recordings": [],     # シャドーイング録音
    }
    save_session(s)
    return s


# ------------------------------------------------------------------ Gemini --
_model_cache = {"name": None}


def _pick_fallback_model():
    url = "https://generativelanguage.googleapis.com/v1beta/models?pageSize=200"
    _, _, raw = http_request(url, headers={"x-goog-api-key": GEMINI_KEY})
    names = [m["name"].split("/")[-1] for m in json.loads(raw).get("models", [])
             if "generateContent" in m.get("supportedGenerationMethods", [])]
    flash = [n for n in names if "flash" in n and "lite" not in n and "image" not in n
             and "tts" not in n and "live" not in n and "audio" not in n]
    def ver(n):
        m = re.search(r"gemini-(\d+(?:\.\d+)?)", n)
        return (float(m.group(1)) if m else 0, "preview" not in n and "exp" not in n)
    flash.sort(key=ver, reverse=True)
    return flash[0] if flash else (names[0] if names else None)


def gemini(parts, schema=None, temperature=0.4):
    if not GEMINI_KEY:
        raise ApiError("GEMINI_API_KEY が .env に設定されていません", 400)
    body = {"contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"temperature": temperature}}
    if schema:
        body["generationConfig"]["responseMimeType"] = "application/json"
        body["generationConfig"]["responseSchema"] = schema
    model = _model_cache["name"] or GEMINI_MODEL
    for attempt in range(2):
        url = "https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent" % model
        try:
            _, _, raw = http_request(url, "POST", {"x-goog-api-key": GEMINI_KEY}, body, timeout=120)
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
    res = json.loads(raw)
    try:
        cparts = res["candidates"][0]["content"]["parts"]
    except (KeyError, IndexError):
        raise ApiError("Gemini から応答がありません: " + json.dumps(res)[:500], 502)
    text = "".join(p.get("text", "") for p in cparts if not p.get("thought"))
    if schema:
        t = text.strip()
        t = re.sub(r"^```(?:json)?|```$", "", t).strip()
        return json.loads(t)
    return text.strip()


def b64(data):
    return base64.b64encode(data).decode("ascii")


def S(t, **kw):
    d = {"type": t}
    d.update(kw)
    return d


def transcribe(wav):
    parts = [
        {"text": "Transcribe this English speech by a Japanese learner verbatim. "
                 "Keep the speaker's grammar mistakes exactly as spoken (do NOT correct them). "
                 "Omit filler sounds like 'uh', 'um'. Output only the transcript text."},
        {"inline_data": {"mime_type": "audio/wav", "data": b64(wav)}},
    ]
    return gemini(parts, temperature=0.0)


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


def correct(sid, text, level="B2", sentences=5):
    d = session_dir(sid)
    with open(os.path.join(d, "photo.jpg"), "rb") as f:
        img = f.read()
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
    parts = [{"text": prompt}, {"inline_data": {"mime_type": "image/jpeg", "data": b64(img)}}]
    return gemini(parts, CORRECTION_SCHEMA, temperature=0.5)


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


def evaluate(wav, reference, mode):
    mode_desc = {
        "overlap": "overlapping shadowing (speaking simultaneously with a model recording heard through headphones; "
                   "faint bleed of the model voice may be present — evaluate only the learner's voice)",
        "repeat": "repeating after the model (the learner speaks alone)",
    }.get(mode, "shadowing")
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
    ) % (mode_desc, reference.strip())
    parts = [{"text": prompt}, {"inline_data": {"mime_type": "audio/wav", "data": b64(wav)}}]
    return gemini(parts, EVAL_SCHEMA, temperature=0.2)


# -------------------------------------------------------------- ElevenLabs --
_voices_cache = {"t": 0, "v": None}


def list_voices():
    if not ELEVEN_KEY:
        raise ApiError("ELEVENLABS_API_KEY が .env に設定されていません", 400)
    if _voices_cache["v"] and time.time() - _voices_cache["t"] < 3600:
        return _voices_cache["v"]
    _, _, raw = http_request("https://api.elevenlabs.io/v1/voices", headers={"xi-api-key": ELEVEN_KEY})
    vs = []
    for v in json.loads(raw).get("voices", []):
        labels = v.get("labels") or {}
        vs.append({"id": v["voice_id"], "name": v.get("name", ""),
                   "desc": ", ".join(x for x in [labels.get("accent"), labels.get("gender"), labels.get("age"),
                                                 labels.get("description") or labels.get("descriptive")] if x),
                   "category": v.get("category", "")})
    _voices_cache.update(t=time.time(), v=vs)
    return vs


def split_alignment(text, al):
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
        if re.search(r"[.!?][\"')\]]*$", w["text"]) and not re.fullmatch(r"(Mr|Mrs|Ms|Dr|St|e\.g|i\.e)\.", w["text"]):
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


def tts(sid, text, voice_id=None, model_id=None, stability=0.5):
    if not ELEVEN_KEY:
        raise ApiError("ELEVENLABS_API_KEY が .env に設定されていません", 400)
    voice_id = voice_id or ELEVEN_VOICE
    if not voice_id:
        vs = list_voices()
        if not vs:
            raise ApiError("ElevenLabs のボイスが見つかりません", 400)
        voice_id = vs[0]["id"]
    model_id = model_id or ELEVEN_MODEL
    key = hashlib.sha1(("%s|%s|%s|%s" % (text, voice_id, model_id, stability)).encode()).hexdigest()[:12]
    d = session_dir(sid)
    mp3 = os.path.join(d, "model_%s.mp3" % key)
    meta = os.path.join(d, "model_%s.json" % key)
    if not (os.path.exists(mp3) and os.path.exists(meta)):
        url = "https://api.elevenlabs.io/v1/text-to-speech/%s/with-timestamps?output_format=mp3_44100_128" % voice_id
        body = {"text": text, "model_id": model_id,
                "voice_settings": {"stability": stability, "similarity_boost": 0.75}}
        _, _, raw = http_request(url, "POST", {"xi-api-key": ELEVEN_KEY}, body, timeout=180)
        res = json.loads(raw)
        with open(mp3, "wb") as f:
            f.write(base64.b64decode(res["audio_base64"]))
        al = res.get("alignment") or res.get("normalized_alignment") or {}
        sentences, words = split_alignment(text, al)
        with open(meta, "w", encoding="utf-8") as f:
            json.dump({"sentences": sentences, "words": words, "voice_id": voice_id, "model_id": model_id},
                      f, ensure_ascii=False)
    with open(meta, encoding="utf-8") as f:
        m = json.load(f)
    m.update({"audio": "/data/%s/%s" % (sid, os.path.basename(mp3)), "text": text})
    return m


# ------------------------------------------------------------------ server --
class Handler(BaseHTTPRequestHandler):
    server_version = "EigoShadowing/1.0"

    def log_message(self, fmt, *args):
        if "/api/" in (args[0] if args else ""):
            sys.stderr.write("[%s] %s\n" % (time.strftime("%H:%M:%S"), fmt % args))

    # -- helpers
    def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n) if n else b""

    def _json(self):
        raw = self._body()
        return json.loads(raw) if raw else {}

    def _file(self, path):
        if not os.path.isfile(path):
            return self._send(404, {"error": "not found"})
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        size = os.path.getsize(path)
        rng = self.headers.get("Range")
        with open(path, "rb") as f:
            if rng and rng.startswith("bytes="):
                a, _, b = rng[6:].partition("-")
                a = int(a or 0)
                b = int(b) if b else size - 1
                f.seek(a)
                data = f.read(b - a + 1)
                self.send_response(206)
                self.send_header("Content-Range", "bytes %d-%d/%d" % (a, b, size))
            else:
                data = f.read()
                self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _safe_join(self, base, rel):
        p = os.path.realpath(os.path.join(base, rel))
        if not p.startswith(os.path.realpath(base) + os.sep):
            raise ApiError("forbidden", 403)
        return p

    # -- routing
    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        try:
            u = urllib.parse.urlparse(self.path)
            p = u.path
            if p in ("/", "/index.html"):
                return self._file(os.path.join(STATIC_DIR, "index.html"))
            if p.startswith("/static/"):
                return self._file(self._safe_join(STATIC_DIR, p[len("/static/"):]))
            if p.startswith("/data/"):
                return self._file(self._safe_join(DATA_DIR, urllib.parse.unquote(p[len("/data/"):])))
            if p == "/api/config":
                return self._send(200, {
                    "gemini": bool(GEMINI_KEY), "elevenlabs": bool(ELEVEN_KEY), "unsplash": bool(UNSPLASH_KEY),
                    "gemini_model": _model_cache["name"] or GEMINI_MODEL, "eleven_model": ELEVEN_MODEL,
                    "default_voice": ELEVEN_VOICE})
            if p == "/api/voices":
                return self._send(200, list_voices())
            if p == "/api/sessions":
                return self._send(200, list_sessions())
            m = re.fullmatch(r"/api/session/([\w\-]+)", p)
            if m:
                return self._send(200, load_session(m.group(1)))
            return self._send(404, {"error": "not found"})
        except ApiError as e:
            return self._send(e.status if 400 <= e.status < 600 else 500, {"error": str(e)})
        except Exception as e:
            traceback.print_exc()
            return self._send(500, {"error": repr(e)})

    def do_POST(self):
        try:
            u = urllib.parse.urlparse(self.path)
            p, q = u.path, urllib.parse.parse_qs(u.query)
            if p == "/api/session/new":
                body = self._json()
                return self._send(200, new_session(body.get("query", "").strip()))

            m = re.fullmatch(r"/api/session/([\w\-]+)/(\w+)", p)
            if not m:
                return self._send(404, {"error": "not found"})
            sid, action = m.group(1), m.group(2)
            d = session_dir(sid)

            if action == "transcribe":
                wav = self._body()
                n = len([f for f in os.listdir(d) if f.startswith("describe_")]) + 1
                with open(os.path.join(d, "describe_%02d.wav" % n), "wb") as f:
                    f.write(wav)
                return self._send(200, {"text": transcribe(wav)})

            if action == "correct":
                body = self._json()
                text = (body.get("text") or "").strip()
                if not text:
                    raise ApiError("説明文が空です", 400)
                res = correct(sid, text, body.get("level", "B2"), body.get("sentences", 5))
                with _lock:
                    s = load_session(sid)
                    s["attempts"].append({"time": time.strftime("%H:%M:%S"), "text": text, "score": res.get("score")})
                    s["correction"] = dict(res, original=text, level=body.get("level", "B2"))
                    s["tts"] = None
                    save_session(s)
                return self._send(200, s)

            if action == "ideal":   # 理想文を手動編集
                body = self._json()
                with _lock:
                    s = load_session(sid)
                    if s.get("correction"):
                        s["correction"]["ideal"] = body.get("ideal", "").strip()
                        s["tts"] = None
                        save_session(s)
                return self._send(200, s)

            if action == "tts":
                body = self._json()
                s = load_session(sid)
                text = (body.get("text") or (s.get("correction") or {}).get("ideal") or "").strip()
                if not text:
                    raise ApiError("読み上げる文章がありません", 400)
                res = tts(sid, text, body.get("voice_id"), body.get("model_id"), float(body.get("stability", 0.5)))
                with _lock:
                    s = load_session(sid)
                    s["tts"] = res
                    save_session(s)
                return self._send(200, res)

            if action == "record":
                wav = self._body()
                seg = q.get("seg", ["all"])[0]
                mode = q.get("mode", ["overlap"])[0]
                with _lock:
                    s = load_session(sid)
                    n = len(s["recordings"]) + 1
                    fn = "rec_%03d.wav" % n
                    with open(os.path.join(d, fn), "wb") as f:
                        f.write(wav)
                    rec = {"n": n, "file": "/data/%s/%s" % (sid, fn), "seg": seg, "mode": mode,
                           "time": time.strftime("%H:%M:%S"), "evaluation": None}
                    s["recordings"].append(rec)
                    save_session(s)
                return self._send(200, rec)

            if action == "evaluate":
                body = self._json()
                n = int(body["n"])
                s = load_session(sid)
                rec = next((r for r in s["recordings"] if r["n"] == n), None)
                if not rec:
                    raise ApiError("録音が見つかりません", 404)
                ref = (body.get("reference") or "").strip()
                if not ref:
                    raise ApiError("手本テキストがありません", 400)
                with open(os.path.join(d, "rec_%03d.wav" % n), "rb") as f:
                    wav = f.read()
                ev = evaluate(wav, ref, rec.get("mode", "overlap"))
                with _lock:
                    s = load_session(sid)
                    for r in s["recordings"]:
                        if r["n"] == n:
                            r["evaluation"] = ev
                            r["reference"] = ref
                    save_session(s)
                return self._send(200, ev)

            return self._send(404, {"error": "unknown action"})
        except ApiError as e:
            return self._send(e.status if 400 <= e.status < 600 else 500, {"error": str(e)})
        except Exception as e:
            traceback.print_exc()
            return self._send(500, {"error": repr(e)})


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    url = "http://localhost:%d" % PORT
    print("=" * 56)
    print("  英語 写真説明 & シャドーイング  →  %s" % url)
    print("  Gemini: %s / ElevenLabs: %s / Unsplash: %s" % (
        "OK" if GEMINI_KEY else "未設定", "OK" if ELEVEN_KEY else "未設定", "OK" if UNSPLASH_KEY else "未設定(代替写真)"))
    print("  終了するには Ctrl+C")
    print("=" * 56)
    if "--no-browser" not in sys.argv:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")


if __name__ == "__main__":
    main()
