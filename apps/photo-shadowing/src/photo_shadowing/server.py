"""FastAPI サーバー

外部 API の呼び出しは時間がかかるため、エンドポイントは同期関数（FastAPI がスレッドプールで実行）にする。
録音の WAV を生で受け取るエンドポイントだけは Request から読む必要があるので async にし、
重い処理は run_in_threadpool に逃がしてイベントループを止めないようにする。
"""
import time

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from . import elevenlabs, gemini, photos, storage
from .config import WEB_DIST, settings
from .http import ApiError

app = FastAPI(title="Photo Shadowing")


@app.exception_handler(ApiError)
def _api_error(_: Request, e: ApiError):
    status = e.status if 400 <= e.status < 600 else 500
    return JSONResponse({"error": str(e)}, status_code=status)


def view(s: dict) -> dict:
    """フロントに返す形に整える

    clone 直後などで手本音声のファイルが無いときは、tts を無いものとして返して作り直しを促す。
    session.json 自体は書き換えない（タイムスタンプの情報を消さないため）。
    """
    tts = s.get("tts")
    if tts and not storage.file_path(s["id"], tts["file"]).exists():
        s = dict(s, tts=None)
    return s


# ------------------------------------------------------------------ config ---
@app.get("/api/config")
def get_config():
    return {"gemini": bool(settings.gemini_key), "elevenlabs": bool(settings.eleven_key),
            "unsplash": bool(settings.unsplash_key), "gemini_model": gemini.current_model(),
            "eleven_model": settings.eleven_model, "default_voice": settings.eleven_voice}


@app.get("/api/voices")
def get_voices():
    return elevenlabs.list_voices()


# ---------------------------------------------------------------- sessions ---
@app.get("/api/sessions")
def get_sessions():
    return storage.list_summaries()


@app.get("/api/sessions/{sid}")
def get_session(sid: str):
    return view(storage.load(sid))


class NewSession(BaseModel):
    query: str = ""


@app.post("/api/sessions")
def create_session(body: NewSession):
    sid = storage.new_id()
    d = storage.session_dir(sid)
    query = body.query.strip()
    photo = photos.pick(query)
    d.mkdir(parents=True, exist_ok=True)
    photos.download(photo["url"], d / "photo.jpg")
    s = {
        "id": sid,
        "created": time.strftime("%Y-%m-%d %H:%M"),
        "query": query,
        "photo": photo,
        "attempts": [],       # 自分の説明（複数回可）
        "correction": None,   # 最新の添削結果
        "tts": None,          # 手本音声
        "recordings": [],     # シャドーイング録音
    }
    storage.save(s)
    return s


@app.post("/api/sessions/{sid}/transcribe")
async def transcribe(sid: str, request: Request):
    wav = await request.body()
    d = storage.session_dir(sid)
    if not d.exists():
        raise ApiError("session not found", 404)
    n = len(list(d.glob("describe_*.wav"))) + 1
    (d / ("describe_%02d.wav" % n)).write_bytes(wav)
    return {"text": await run_in_threadpool(gemini.transcribe, wav)}


class CorrectBody(BaseModel):
    text: str
    level: str = "B2"
    sentences: int = 5


@app.post("/api/sessions/{sid}/correct")
def correct(sid: str, body: CorrectBody):
    text = body.text.strip()
    if not text:
        raise ApiError("説明文が空です", 400)
    photo = storage.file_path(sid, "photo.jpg").read_bytes()
    res = gemini.correct(photo, text, body.level, body.sentences)
    with storage.lock:
        s = storage.load(sid)
        s["attempts"].append({"time": time.strftime("%H:%M:%S"), "text": text, "score": res.get("score")})
        s["correction"] = dict(res, original=text, level=body.level)
        s["tts"] = None
        storage.save(s)
    return view(s)


class IdealBody(BaseModel):
    ideal: str


@app.put("/api/sessions/{sid}/ideal")
def update_ideal(sid: str, body: IdealBody):
    """理想文を手動編集"""
    with storage.lock:
        s = storage.load(sid)
        if not s.get("correction"):
            raise ApiError("先に添削してください", 400)
        s["correction"]["ideal"] = body.ideal.strip()
        s["tts"] = None
        storage.save(s)
    return view(s)


class TtsBody(BaseModel):
    voice_id: str | None = None
    stability: float = 0.5


@app.post("/api/sessions/{sid}/tts")
def make_tts(sid: str, body: TtsBody):
    s = storage.load(sid)
    text = ((s.get("correction") or {}).get("ideal") or "").strip()
    if not text:
        raise ApiError("読み上げる文章がありません", 400)
    tts = elevenlabs.synthesize(storage.session_dir(sid), text, body.voice_id, body.stability, s.get("tts"))
    with storage.lock:
        s = storage.load(sid)
        s["tts"] = tts
        storage.save(s)
    return tts


@app.post("/api/sessions/{sid}/recordings")
async def add_recording(sid: str, request: Request, seg: str = "all", mode: str = "overlap", reference: str = ""):
    wav = await request.body()
    with storage.lock:
        s = storage.load(sid)
        n = max((r["n"] for r in s["recordings"]), default=0) + 1
        name = "rec_%03d.wav" % n
        storage.file_path(sid, name).write_bytes(wav)
        rec = {"n": n, "file": name, "seg": seg, "mode": mode, "reference": reference,
               "time": time.strftime("%H:%M:%S"), "evaluation": None}
        s["recordings"].append(rec)
        storage.save(s)
    return rec


@app.post("/api/sessions/{sid}/recordings/{n}/evaluate")
def evaluate(sid: str, n: int):
    s = storage.load(sid)
    rec = next((r for r in s["recordings"] if r["n"] == n), None)
    if not rec:
        raise ApiError("録音が見つかりません", 404)
    if not rec.get("reference"):
        raise ApiError("手本テキストがありません", 400)
    wav = storage.file_path(sid, rec["file"]).read_bytes()
    ev = gemini.evaluate(wav, rec["reference"], rec.get("mode", "overlap"))
    with storage.lock:
        s = storage.load(sid)
        for r in s["recordings"]:
            if r["n"] == n:
                r["evaluation"] = ev
        storage.save(s)
    return ev


# ------------------------------------------------------------------- files ---
@app.get("/files/{sid}/{name}")
def get_file(sid: str, name: str):
    p = storage.file_path(sid, name)
    if not p.exists() and name == "photo.jpg":
        # 写真は git 管理外なので、clone 直後は元の URL から取り直す
        url = (storage.load(sid).get("photo") or {}).get("url")
        if url:
            photos.download(url, p)
    if not p.exists():
        raise ApiError("not found", 404)
    return FileResponse(p, headers={"Cache-Control": "no-cache"})


# ビルド済みのフロントエンドを配信する（開発中は Vite の dev server を使う）
if WEB_DIST.exists():
    app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="web")
