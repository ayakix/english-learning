"""練習ログ（session.json）の読み書き

保存先は practice_dir/<技能>/YYYY/MM/<id>/。月ごとに分けるのは journal と同じ並びにして、
後から日付で振り返りやすくするため。
session.json だけを git 管理し、写真・音声は同じディレクトリに置くが管理外にする。

どの技能の session.json も、共通で次の項目を持つ（進捗の集計に使う）：
  id, skill, created, title, result = {"score": 0-100 | None, "details": {...}}
"""
import json
import re
import threading
import time
from pathlib import Path

from .config import settings
from .http import ApiError

SKILLS = ("speaking", "listening", "writing", "reading", "lesson")

# 同じ session.json を複数のリクエストが同時に読み書きしても壊れないようにする
lock = threading.Lock()

ID_RE = re.compile(r"\d{8}-\d{6}")
FILE_RE = re.compile(r"[\w\-.]+")


def new_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def new_session(skill: str, **fields) -> dict:
    return {"id": new_id(), "skill": skill, "created": time.strftime("%Y-%m-%d %H:%M"),
            "title": "", "result": {"score": None, "details": {}}, **fields}


def _check_skill(skill: str) -> None:
    if skill not in SKILLS:
        raise ApiError("unknown skill: %s" % skill, 404)


def session_dir(skill: str, sid: str) -> Path:
    _check_skill(skill)
    if not ID_RE.fullmatch(sid or ""):
        raise ApiError("invalid session id", 400)
    return settings.practice_dir / skill / sid[:4] / sid[4:6] / sid


def file_path(skill: str, sid: str, name: str) -> Path:
    if not FILE_RE.fullmatch(name) or name.startswith("."):
        raise ApiError("invalid file name", 400)
    return session_dir(skill, sid) / name


def load(skill: str, sid: str) -> dict:
    p = session_dir(skill, sid) / "session.json"
    if not p.exists():
        raise ApiError("session not found", 404)
    return json.loads(p.read_text(encoding="utf-8"))


def save(s: dict) -> None:
    d = session_dir(s["skill"], s["id"])
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / "session.json.tmp"
    tmp.write_text(json.dumps(s, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(d / "session.json")


def all_ids(skill: str) -> list[str]:
    _check_skill(skill)
    root = settings.practice_dir / skill
    if not root.exists():
        return []
    ids = [p.parent.name for p in root.glob("*/*/*/session.json")]
    return sorted((i for i in ids if ID_RE.fullmatch(i)), reverse=True)


def load_all(skill: str) -> list[dict]:
    """新しい順。壊れたファイルは飛ばす（1 件のせいで一覧や集計が見られなくならないように）"""
    out = []
    for sid in all_ids(skill):
        try:
            out.append(load(skill, sid))
        except (ApiError, json.JSONDecodeError):
            continue
    return out


def list_summaries(skill: str) -> list[dict]:
    return [{"id": s["id"], "created": s.get("created"), "title": s.get("title", ""),
             "score": (s.get("result") or {}).get("score")} for s in load_all(skill)]
