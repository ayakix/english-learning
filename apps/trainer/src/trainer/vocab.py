"""身近なものの単語：英→日・日→英で意味が分かるか・言えるかを確かめ、○/× を記録する

即答で「意味は分かるのに英語が出てこない（yolk・crib）」「単語を知らない（neat）」とつまずいたので作った。
例題は Claude が content/drills/vocab/items.json に書く。音声は単語だけを ElevenLabs で作る
（綴りから読み方を覚え違えないように発音を確かめるため。例文まで作るほどではない）。
置き場所・音声の作り方・配信は drills.py の種類の 1 つ（vocab）として共通にしている。
"""
from fastapi import APIRouter
from pydantic import BaseModel

from . import drills, marks
from .http import ApiError

SKILL = "vocab"
# 向きごとに記録を分ける（日→英の方が難しいので、混ぜると正答率の意味がぼやける）
MODES = {"en-ja": "単語 英→日", "ja-en": "単語 日→英"}

router = APIRouter(prefix="/api/vocab")


def items_by_id() -> dict[str, dict]:
    return {it["id"]: it for it in drills.load(SKILL)["items"]}


def _check_mode(mode: str) -> None:
    if mode not in MODES:
        raise ApiError("unknown mode: " + mode, 404)


@router.get("")
def get_vocab():
    """単語を返す。音声がまだ無い単語も、意味の確認には使えるので除かず、audio_file を空にする"""
    data = drills.load(SKILL)
    return {"themes": data.get("themes", []),
            "items": [{**it, "audio_file": it["audio"]["main"].get("file") if drills.has_audio(SKILL, it) else None}
                      for it in data["items"]]}


@router.get("/marks/{mode}")
def get_marks(mode: str):
    _check_mode(mode)
    return marks.get(SKILL, mode)


class MarkBody(BaseModel):
    ok: bool


@router.put("/marks/{mode}/{item_id}")
def put_mark(mode: str, item_id: str, body: MarkBody):
    _check_mode(mode)
    if item_id not in items_by_id():
        raise ApiError("単語が見つかりません", 404)
    return marks.put(SKILL, mode, MODES[mode], item_id, body.ok)
