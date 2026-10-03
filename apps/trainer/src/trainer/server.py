"""FastAPI サーバー：技能ごとのルーターをまとめ、共通の API・練習ファイル・画面を配信する"""
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import elevenlabs, gemini, listening, photos, progress, reading, speaking, storage, voa, writing
from .config import WEB_DIST, settings
from .http import ApiError

app = FastAPI(title="English Trainer")
for module in (speaking, listening, writing, reading, voa):
    app.include_router(module.router)


@app.exception_handler(ApiError)
def _api_error(_: Request, e: ApiError):
    status = e.status if 400 <= e.status < 600 else 500
    return JSONResponse({"error": str(e)}, status_code=status)


@app.get("/api/config")
def get_config():
    return {"gemini": bool(settings.gemini_key), "elevenlabs": bool(settings.eleven_key),
            "unsplash": bool(settings.unsplash_key), "gemini_model": gemini.current_model(),
            "eleven_model": settings.eleven_model, "default_voice": settings.eleven_voice}


@app.get("/api/voices")
def get_voices():
    return elevenlabs.list_voices()


@app.get("/api/progress")
def get_progress():
    pts = progress.points()
    return {"points": pts, "weeks": progress.weekly(pts)}


@app.get("/api/{skill}/sessions")
def get_sessions(skill: str):
    return storage.list_summaries(skill)


@app.get("/files/{skill}/{sid}/{name}")
def get_file(skill: str, sid: str, name: str):
    p = storage.file_path(skill, sid, name)
    if not p.exists() and skill == "speaking" and name == "photo.jpg":
        # 写真は git 管理外なので、clone 直後は元の URL から取り直す
        url = (storage.load(skill, sid).get("photo") or {}).get("url")
        p.parent.mkdir(parents=True, exist_ok=True)
        if url:
            photos.download(url, p)
    if not p.exists() and skill == "voa" and name == voa.AUDIO:
        # 音声も git 管理外なので、VOA の元の URL か AI 教材のストックから取り直す
        voa.restore_audio(storage.load(skill, sid), p)
    if not p.exists():
        raise ApiError("not found", 404)
    return FileResponse(p, headers={"Cache-Control": "no-cache"})


# ビルド済みのフロントエンドを配信する（開発中は Vite の dev server を使う）
if WEB_DIST.exists():
    app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="web")
