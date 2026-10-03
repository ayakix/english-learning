"""練習ログ（session.json）の読み書き

保存先は practice_dir/YYYY/MM/<id>/。月ごとに分けるのは journal と同じ並びにして、
後から日付で振り返りやすくするため。
session.json だけを git 管理し、写真・音声は同じディレクトリに置くが管理外にする。
"""
import json
import re
import threading
import time
from pathlib import Path

from .config import settings
from .http import ApiError

# 同じ session.json を複数のリクエストが同時に読み書きしても壊れないようにする
lock = threading.Lock()

ID_RE = re.compile(r"\d{8}-\d{6}")
FILE_RE = re.compile(r"[\w\-.]+")


def new_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def session_dir(sid: str) -> Path:
    if not ID_RE.fullmatch(sid or ""):
        raise ApiError("invalid session id", 400)
    return settings.practice_dir / sid[:4] / sid[4:6] / sid


def file_path(sid: str, name: str) -> Path:
    if not FILE_RE.fullmatch(name) or name.startswith("."):
        raise ApiError("invalid file name", 400)
    return session_dir(sid) / name


def load(sid: str) -> dict:
    p = session_dir(sid) / "session.json"
    if not p.exists():
        raise ApiError("session not found", 404)
    return json.loads(p.read_text(encoding="utf-8"))


def save(s: dict) -> None:
    d = session_dir(s["id"])
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / "session.json.tmp"
    tmp.write_text(json.dumps(s, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(d / "session.json")


def all_ids() -> list[str]:
    root = settings.practice_dir
    if not root.exists():
        return []
    ids = [p.parent.name for p in root.glob("*/*/*/session.json")]
    return sorted((i for i in ids if ID_RE.fullmatch(i)), reverse=True)


def best_score(s: dict) -> int | None:
    scores = [r["evaluation"].get("overall") for r in s.get("recordings", []) if r.get("evaluation")]
    return max((v for v in scores if isinstance(v, (int, float))), default=None)


def list_summaries() -> list[dict]:
    out = []
    for sid in all_ids():
        try:
            s = load(sid)
        except (ApiError, json.JSONDecodeError):
            continue
        out.append({
            "id": sid,
            "created": s.get("created"),
            "has_ideal": bool(s.get("correction")),
            "recordings": len(s.get("recordings", [])),
            "best": best_score(s),
        })
    return out
