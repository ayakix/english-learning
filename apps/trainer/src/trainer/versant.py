"""Versant の復唱・即答で、言えた（○）・言えなかった（×）を記録する

以前は練習ログが残らず、ユーザーの申告を Claude が journal に書いていた。
1 文ずつ記録すれば、summary で間違えた ID まで分かり、振り返りの一覧も申告なしで作れる。

1 日・1 モード（復唱・即答・振り返り）で 1 つの session にまとめる。範囲を 2 つやった日も同じ session に足す。
session は最初に ○/× を付けたときに作る（タブを開いただけで空の記録ができないように）。
"""
import time

from fastapi import APIRouter
from pydantic import BaseModel

from . import drills, storage
from .http import ApiError

SKILL = "versant"
MODES = {"repeats": "復唱", "short-answers": "即答", "review": "振り返り"}

router = APIRouter(prefix="/api/versant")


def _items(mode: str) -> dict[str, dict]:
    """そのモードで付けられる例題を ID 引きで返す（振り返りは復唱と即答の両方）"""
    if mode not in MODES:
        raise ApiError("unknown mode: " + mode, 404)
    kinds = drills.REVIEW_KINDS if mode == "review" else (mode,)
    return {it["id"]: {**it, "kind": kind} for kind in kinds for it in drills.load(kind)["items"]}


def today_session(mode: str) -> dict | None:
    today = time.strftime("%Y-%m-%d")
    return next((s for s in storage.load_all(SKILL) if s["created"][:10] == today and s.get("mode") == mode), None)


def update_result(s: dict) -> None:
    marks = s["marks"].values()
    ok = sum(1 for m in marks if m["ok"])
    s["result"]["details"] = {"ok": ok, "total": len(marks)}
    # 振り返りは一度間違えた文のやり直しなので、点数に入れると実力より高く見える。記録だけ残す
    s["result"]["score"] = None if s["mode"] == "review" else round(ok / len(marks) * 100)


@router.get("/marks/{mode}")
def get_marks(mode: str):
    _items(mode)
    s = today_session(mode)
    return {"marks": {i: m["ok"] for i, m in s["marks"].items()} if s else {}}


class MarkBody(BaseModel):
    ok: bool


@router.put("/marks/{mode}/{item_id}")
def put_mark(mode: str, item_id: str, body: MarkBody):
    it = _items(mode).get(item_id)
    if not it:
        raise ApiError("例題が見つかりません", 404)
    with storage.lock:
        s = today_session(mode) or storage.new_session(SKILL, title=MODES[mode], mode=mode, marks={})
        # 復唱はレベルが上がると正答率が下がるので、後から理由が分かるようにレベルも残す
        s["marks"][item_id] = {"ok": body.ok, "kind": it["kind"], **({"level": it["level"]} if "level" in it else {})}
        update_result(s)
        storage.save(s)
    return {"marks": {i: m["ok"] for i, m in s["marks"].items()}}
