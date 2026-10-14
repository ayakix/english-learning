"""Versant の復唱・即答で、言えた（○）・言えなかった（×）を記録する

以前は練習ログが残らず、ユーザーの申告を Claude が journal に書いていた。
1 文ずつ記録すれば、summary で間違えた ID まで分かり、振り返りの一覧も申告なしで作れる。

1 日・1 モード（復唱・即答・振り返り）で 1 つの session にまとめる（記録の仕組みは marks.py）。
"""
from fastapi import APIRouter
from pydantic import BaseModel

from . import drills, marks
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


@router.get("/marks/{mode}")
def get_marks(mode: str):
    _items(mode)
    return marks.get(SKILL, mode)


class MarkBody(BaseModel):
    ok: bool


@router.put("/marks/{mode}/{item_id}")
def put_mark(mode: str, item_id: str, body: MarkBody):
    it = _items(mode).get(item_id)
    if not it:
        raise ApiError("例題が見つかりません", 404)
    # 復唱はレベルが上がると正答率が下がるので、後から理由が分かるようにレベルも残す
    level = {"level": it["level"]} if "level" in it else {}
    # 振り返りは一度間違えた文のやり直しなので、点数に入れると実力より高く見える。記録だけ残す
    return marks.put(SKILL, mode, MODES[mode], item_id, body.ok, scored=mode != "review", kind=it["kind"], **level)
